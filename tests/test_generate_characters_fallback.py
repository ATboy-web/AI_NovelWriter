"""`GenerateCharacters` 的**三层回退**回归。

## 为什么这组值得单写

模型返回的角色 JSON 经常"七成对"：外层被截断、`goal` 写成数组、
或者干脆在 JSON 前后加一段解释。三层回退按保真度递降：

1. `parse_json_response` —— 标准解析
2. `parse_characters_payload` —— 字符串感知清洗 + 结构性修复 + 逐个提取
3. 逐行抓 `"名字": {` —— **最后手段**，产"待展开"骨架而不是放弃

第 3 层此前**一条用例都没有**（覆盖率 76.7%），而它恰恰是"模型返回垃圾时
唯一还能救回来"的机制。用户能接受"角色是骨架、自己改"，不能接受"生成的
5 个角色全丢了"。

## 为什么用替身隔离各层

第 2 层（`parse_characters_payload`）已经很能打：连 `这是角色列表："林风": {`
这种垃圾都能救回两个名字。所以想验第 3 层，必须**显式让前两层失败** ——
否则"第 3 层没跑到"会被误读成"第 3 层不需要"。
"""

from __future__ import annotations

import json

import pytest

from app.application.generate_characters import GenerateCharacters
from app.memory_manager import CharacterDataGuardError


class CharMemory:
    """够用的记忆替身：角色读写 + 元数据 + 作品目录。"""

    def __init__(self, novel_dir, *, characters=None, meta=None, settings=None, corrupt=False):
        self.novel_dir = novel_dir
        self._chars = dict(characters or {})
        self._meta = dict(meta or {})
        self._settings = settings or {}
        #: `True` 表示磁盘档案损坏且无备份 —— 用例据此验证"拒绝写入"
        self._characters_corrupt = corrupt

    def get_meta(self, key, default=""):
        return self._meta.get(key, default)

    def get_settings(self):
        return self._settings

    def get_characters(self) -> dict:
        return dict(self._chars)

    def mutate_characters(self, mutator):
        self._chars = mutator(self._chars)
        return self._chars


class ScriptedAI:
    """按调用次数返回预置响应（便于验证重试）。"""

    def __init__(self, *replies, exc: Exception | None = None):
        self._replies = list(replies)
        self._exc = exc
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        if self._exc is not None:
            raise self._exc
        index = min(len(self.calls) - 1, len(self._replies) - 1)
        return self._replies[index]


def _chars_json(names: list[str]) -> str:
    """造一个"能过标准解析"的角色响应，长度足够（>50 字）。"""
    payload = {
        name: {
            "gender": "男",
            "age": 20,
            "category": "配角",
            "faction": "中立",
            "personality": "性格鲜明，有弱点也有执念，说话带口音。",
            "background": "出身贫寒，靠一身本事走到今天，心里压着一件旧事。",
            "appearance": "瘦高，左眉有疤",
            "weapon": {"name": "短刀", "quality": "精良", "desc": "刀身有缺口"},
            "skill_suggestions": ["潜行", "急救"],
            "attributes": {"力量": 60, "敏捷": 70, "体质": 55, "智力": 65, "精神": 50, "魅力": 45, "幸运": 40},
            "relationship_to_main": "旧识",
            "goal": "查清当年那场火的真相",
        }
        for name in names
    }
    return json.dumps(payload, ensure_ascii=False)


@pytest.fixture
def make_case(tmp_path, monkeypatch):
    """造 (execute 可用的实例, mem)。默认把 `time.sleep` 打掉，免得重试用例真等 3 秒。"""
    import app.application.generate_characters as mod

    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)

    def _make(ai, *, characters=None, meta=None, corrupt=False):
        mem = CharMemory(tmp_path, characters=characters, meta=meta, corrupt=corrupt)
        return GenerateCharacters(ai, mem, log=lambda _m: None), mem

    return _make


class TestCharacterCountScale:
    """不传 `count` 时按篇幅推算 —— 短篇 3 人、中篇 5 人、长篇 8 人。"""

    @pytest.mark.parametrize(("chapter_count", "expected"), [(20, 3), (21, 5), (50, 5), (51, 8), (200, 8)])
    def test_count_follows_chapter_scale(self, make_case, chapter_count, expected):
        ai = ScriptedAI(_chars_json(["甲"]))
        agent, _mem = make_case(ai, meta={"chapter_count": chapter_count})

        agent.execute("玄幻", "测试书")

        system = ai.calls[0]["kwargs"]["system"]
        assert f"创建{expected}个角色" in system

    def test_explicit_count_wins(self, make_case):
        ai = ScriptedAI(_chars_json(["甲"]))
        agent, _mem = make_case(ai, meta={"chapter_count": 200})

        agent.execute("玄幻", "测试书", count=2)

        assert "创建2个角色" in ai.calls[0]["kwargs"]["system"]


class TestRetryPolicy:
    def test_short_response_is_retried(self, make_case):
        """空/过短响应会重试 —— 模型偶发返回空是已知现象。"""
        ai = ScriptedAI("", _chars_json(["林风"]))
        agent, mem = make_case(ai)

        result = agent.execute("玄幻", "测试书", count=1)

        assert len(ai.calls) == 2, "短响应没有重试"
        assert "林风" in result

    @pytest.mark.parametrize("message", ["401 Unauthorized", "Authorization failed", "API Key 无效"])
    def test_auth_errors_are_not_retried(self, make_case, message):
        """认证错误重试只会白烧三次配额，必须立刻抛。"""
        ai = ScriptedAI(exc=RuntimeError(message))
        agent, _mem = make_case(ai)

        with pytest.raises(RuntimeError):
            agent.execute("玄幻", "测试书", count=1)

        assert len(ai.calls) == 1, f"认证错误被重试了 {len(ai.calls)} 次"

    def test_transient_error_retried_then_raised(self, make_case):
        ai = ScriptedAI(exc=RuntimeError("连接超时"))
        agent, _mem = make_case(ai)

        with pytest.raises(RuntimeError):
            agent.execute("玄幻", "测试书", count=1)

        assert len(ai.calls) == 3, "临时错误应重试满 3 次再抛"


class TestThreeLayerFallback:
    def test_layer2_salvages_from_dirty_text(self, make_case):
        """第 2 层：JSON 外有解释文字时，仍能从中抠出角色。"""
        dirty = '好的，我设计如下：\n"林风": {"personality": "沉默"}\n以上。'
        agent, mem = make_case(ScriptedAI(dirty))

        result = agent.execute("玄幻", "测试书", count=1)

        assert "林风" in result

    def test_layer3_creates_skeletons_when_parsers_fail(self, make_case, monkeypatch):
        """第 3 层：前两层都失败时，逐行抓名字造"待展开"骨架。

        这是"宁可给骨架也不要全丢"的兜底 —— 用户能在面板里看到并手改。
        """
        import app.application.generate_characters as mod

        monkeypatch.setattr(mod, "parse_json_response", lambda *_a, **_k: None)
        monkeypatch.setattr(mod, "parse_characters_payload", lambda *_a, **_k: {})

        garbage = '"林风": {\n"苏晚": {\n"陈九": {\n'
        agent, mem = make_case(ScriptedAI(garbage))

        result = agent.execute("玄幻", "测试书", count=3)

        assert set(result) == {"林风", "苏晚", "陈九"}
        for info in result.values():
            assert info["personality"] == "待展开", "骨架标记丢了，用户看不出这是待补的"
            assert info["category"] == "关键人物"

    def test_layer3_skips_field_names(self, make_case, monkeypatch):
        """`"gender": {` 这类字段名不能被当成角色名。"""
        import app.application.generate_characters as mod

        monkeypatch.setattr(mod, "parse_json_response", lambda *_a, **_k: None)
        monkeypatch.setattr(mod, "parse_characters_payload", lambda *_a, **_k: {})

        garbage = '"gender": {\n"林风": {\n'
        agent, _mem = make_case(ScriptedAI(garbage))

        result = agent.execute("玄幻", "测试书", count=2)

        assert "gender" not in result
        assert "林风" in result

    def test_partial_result_reaches_requested_count(self, make_case):
        """截断响应里能救出几个就救几个，不能"有几个算几个"就收工。

        ⚠️ 这里**只断言数量与"值都是 dict"**：截断后的结构性修复会给出
        `{"苏晚": {"陈九": {}}}` 这类半成品 —— 字段缺失是已知且可接受的
        （用户能在面板里补），但"少一个角色"或"值不是 dict"会让下游崩。
        """
        partial = '{"林风": {"personality": "沉默"}}\n"苏晚": {\n"陈九": {\n'
        agent, _mem = make_case(ScriptedAI(partial))

        result = agent.execute("玄幻", "测试书", count=3)

        assert len(result) == 3, f"只拿到 {len(result)} 个：{list(result)}"
        assert result["林风"]["personality"] == "沉默", "已解析出的真实字段被覆盖了"
        assert all(isinstance(v, dict) for v in result.values()), "出现了非 dict 的角色值"

    def test_supplement_branch_adds_skeleton_roles(self, make_case, monkeypatch):
        """专验"补数量"分支：只解析到 1 个时，其余按「配角」骨架补齐。

        用替身锁死第 2 层的输出，确保第 3 层分支真的被执行 ——
        否则真实解析器太能干，这条分支永远跑不到（覆盖率只有 76.7% 的原因）。
        """
        import app.application.generate_characters as mod

        monkeypatch.setattr(mod, "parse_json_response", lambda *_a, **_k: {"林风": {"personality": "沉默"}})
        monkeypatch.setattr(mod, "parse_characters_payload", lambda *_a, **_k: {})

        response = '{"林风": {"personality": "沉默"}}\n"苏晚": {\n"陈九": {\n'
        agent, _mem = make_case(ScriptedAI(response))

        result = agent.execute("玄幻", "测试书", count=3)

        assert len(result) == 3
        # 补充的用「配角」而不是「关键人物」—— 只补数量，不擅自提升地位
        assert result["苏晚"]["category"] == "配角"
        assert result["陈九"]["category"] == "配角"
        assert result["林风"]["personality"] == "沉默", "补数量不该覆盖已有角色"

    def test_unparseable_and_nameless_returns_empty(self, make_case):
        """彻底救不回来时返回空字典（调用方据此保留原有角色），而不是抛异常。"""
        agent, _mem = make_case(ScriptedAI("完全无关的一段说明文字，没有任何角色结构。" * 3))

        assert agent.execute("玄幻", "测试书", count=3) == {}


class TestPersistence:
    def test_one_file_per_character(self, make_case, tmp_path):
        agent, _mem = make_case(ScriptedAI(_chars_json(["林风", "苏晚"])))

        agent.execute("玄幻", "测试书", count=2)

        files = sorted(p.name for p in (tmp_path / "characters").glob("*.json"))
        assert files == ["林风.json", "苏晚.json"]

    def test_dangerous_name_is_sanitized(self, make_case, tmp_path):
        """角色名里的路径分隔符不能让文件写到目录外。"""
        agent, _mem = make_case(ScriptedAI(_chars_json(["../逃逸"])))

        agent.execute("玄幻", "测试书", count=1)

        written = list((tmp_path / "characters").glob("*.json"))
        assert len(written) == 1
        assert written[0].parent == tmp_path / "characters", "文件被写到 characters/ 之外"

    def test_existing_characters_are_preserved(self, make_case):
        """🔴 写回是**并集**：只生成 1 个新角色，不能把书里已有的 2 个清掉。"""
        existing = {
            "老角色甲": {"personality": "旧", "category": "主角"},
            "老角色乙": {"personality": "旧", "category": "配角"},
        }
        agent, mem = make_case(ScriptedAI(_chars_json(["林风"])), characters=existing)

        agent.execute("玄幻", "测试书", count=1)

        chars = mem.get_characters()
        assert {"老角色甲", "老角色乙", "林风"} <= set(chars)

    def test_same_name_fields_merge_with_new_priority(self, make_case):
        existing = {"林风": {"personality": "旧性格", "background": "旧背景", "hidden": "保留我"}}
        agent, mem = make_case(ScriptedAI(_chars_json(["林风"])), characters=existing)

        agent.execute("玄幻", "测试书", count=1)

        merged = mem.get_characters()["林风"]
        assert merged["personality"] != "旧性格", "同名字段应以新数据为准"
        assert merged["hidden"] == "保留我", "未出现在新数据里的字段被丢了"

    def test_corrupt_archive_raises_instead_of_overwriting(self, make_case):
        """🔴 档案损坏时 `get_characters()` 会降级返回 {}，
        并集会退化成"整体覆盖"⇒ 清空全部既有角色。必须拒绝写入。"""
        agent, mem = make_case(ScriptedAI(_chars_json(["林风"])), corrupt=True)

        with pytest.raises(CharacterDataGuardError):
            agent.execute("玄幻", "测试书", count=1)

        assert mem.get_characters() == {}, "损坏档案被写入了"
