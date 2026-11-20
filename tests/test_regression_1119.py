"""2026-11-19 事故的回归守卫（《配种的强大之处》3 章生成失败）。

## 这次到底发生了什么

日志里三类症状，各自对应一个独立缺陷：

| 症状 | 根因 | 归属 |
|---|---|---|
| `DeepSeek思考模式耗尽 token (reasoning_len=5948/6086)` | `thinking_enabled=False` **只是"不发开启参数"**，而 DeepSeek 在省略该字段时**默认开启思考** | 上一版声称已修，实际未修 |
| 两章评审全部 `overall=None` | 同上：4000 token 预算被思考吃光，`content` 不是 JSON | 同上 |
| 第 3 章整章失败 | 评审异常**穿透**到生成主流程（上一版把评审改成 `allow_reasoning_fallback=False` 却没加异常兜底） | 上一版引入的回归 |
| `[角色成长] JSON解析失败` | 该调用没关思考，3000 token 被吃光 | 上一版漏改的一批 |
| 角色卡 `backstory` 为空、没有 goal/relationship | 提示词要求 `background`，数据类只读 `backstory`；另三个键数据类压根没有 | 长期存在，从未被发现 |

本文件钉住"容易回退"的几处。
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app.character_system import CharacterProfile

REPO = pathlib.Path(__file__).resolve().parent.parent


# ====================================================================== 思考必须显式关闭


class TestThinkingAlwaysExplicit:
    """`novel_agent` 里**每一个** `ai.chat()` 都必须显式传 `thinking_enabled`。

    为什么是全量而不是"只查正文类"：上一版按"产出物是否是正文"筛，
    结果漏掉了 8 处（其中 `_update_character_progression` 实测失败）。
    思考预算与正文共用同一个 `max_tokens`，**预算小的结构化调用反而先被吃光**。
    """

    @staticmethod
    def _calls() -> list[tuple[int, str, set[str]]]:
        source = (REPO / "app" / "novel_agent.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        funcs = [
            (n.lineno, n.end_lineno, n.name)
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        rows = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Attribute) and node.func.attr == "chat"):
                continue
            owner = next((f for f in funcs if f[0] <= node.lineno <= f[1]), None)
            rows.append((node.lineno, owner[2] if owner else "?", {kw.arg for kw in node.keywords}))
        return rows

    def test_no_chat_call_relies_on_server_default(self):
        missing = [f"行 {line} ({func})" for line, func, kwargs in self._calls() if "thinking_enabled" not in kwargs]
        assert not missing, "以下调用没传 thinking_enabled，会掉进 DeepSeek 的「默认开启思考」：\n  " + "\n  ".join(
            missing
        )

    def test_call_count_is_sane(self):
        """反断言：扫描本身要有效，不能因为函数改名而扫到 0 个。"""
        assert len(self._calls()) >= 15, "扫描到的 chat 调用过少，守卫可能已失效"


class TestProviderDisableIsExplicit:
    """关闭思考必须落到请求体的**具体字段**上，而不是"不发"。"""

    @staticmethod
    def _body(provider: str, thinking: bool, max_tokens: int = 4000) -> dict:
        from app.providers.base import ChatRequest
        from app.providers.registry import DEFAULT_SPECS, ProviderRegistry

        registry = ProviderRegistry(DEFAULT_SPECS)
        spec = registry.resolve(provider)
        request = ChatRequest(
            model=spec.default_model,
            messages=[{"role": "user", "content": "x"}],
            system="",
            max_tokens=max_tokens,
            temperature=0.8,
            thinking_enabled=thinking,
            reasoning_effort="max",
            stream=False,
        )
        return registry.adapter(provider).build_request(request).json_body

    @pytest.mark.parametrize("provider", ["deepseek", "glm", "kimi"])
    def test_thinking_type_providers_send_disabled(self, provider):
        body = self._body(provider, thinking=False)
        assert body.get("thinking") == {"type": "disabled"}, provider
        assert "reasoning_effort" not in body, f"{provider} 关闭时不应再带 reasoning_effort"

    def test_qwen_sends_enable_thinking_false(self):
        body = self._body("qwen", thinking=False)
        assert body.get("enable_thinking") is False
        assert "thinking_budget" not in body

    def test_enabled_still_works(self):
        """回归：关闭的修复不能把"开启"弄坏。"""
        body = self._body("deepseek", thinking=True)
        assert body["thinking"] == {"type": "enabled"}
        assert body["reasoning_effort"] == "max"

    def test_small_budget_forces_disable(self):
        """v2 保护：max_tokens 太小时必须**显式**关掉，而不是"不发字段"。"""
        body = self._body("deepseek", thinking=True, max_tokens=500)
        assert body["thinking"] == {"type": "disabled"}


# ====================================================================== 评审故障必须降级


class TestReviewFailureDoesNotKillChapter:
    """评审是**质量门**，不是出稿的前置条件。

    上一版把评审的 `allow_reasoning_fallback` 改成 False（对：不拿工作笔记当成品），
    却没给调用点加异常兜底 ⇒ 一次"审校没跑成"把**已写好的整章**丢掉。
    日志铁证：第 3 章 `Exception: DeepSeek思考模式耗尽 token`，正文其实已生成。
    """

    @staticmethod
    def _agent(monkeypatch, review_raises: bool):
        from app import novel_agent as na

        agent = na.NovelAgent.__new__(na.NovelAgent)
        import threading

        agent._log_lock = threading.Lock()
        agent._conversation_log = []
        agent._revision_memory = []
        agent.tools = type("T", (), {"call": staticmethod(lambda *a, **k: None)})()
        agent.memory = type("M", (), {"get_settings": staticmethod(lambda: {})})()
        agent.last_chapter_quality = None
        agent._plot_designer_analyze = lambda cn, t, o: {"type": "writing"}
        agent._build_context = lambda cn, pc, writing_phase=None: "ctx"
        agent._world_builder_build = lambda cn, pa: ""
        agent._writer_generate = lambda cn, t, o, wc, context="", prev_ending="": "正文" * 100
        agent._call_anti_slop_check = lambda content: []
        agent._record_conversation = lambda *a, **k: None
        agent._emit_chapter_timing = lambda *a, **k: None
        agent.log = lambda *a, **k: None

        def _review(cn, content, previous_feedback=""):
            if review_raises:
                raise RuntimeError("DeepSeek思考模式耗尽 token，未产出正文 (reasoning_len=6086)")
            return {"overall_score": 90, "issues": [], "suggestions": []}

        agent._reviewer_evaluate = _review
        agent._writer_revise = lambda cn, c, r, o, context="", prev_ending="": c + "改"
        return agent

    def test_chapter_survives_review_exception(self, monkeypatch):
        agent = self._agent(monkeypatch, review_raises=True)
        content = agent.generate_with_collaboration(3, "第三章", "大纲" * 10, word_count=500)
        assert content, "评审抛异常后正文被丢弃了"
        assert "正文" in content

    def test_quality_score_is_none_not_fake(self, monkeypatch):
        """评审失败时评分必须是 None（未知），不能伪造一个及格分。"""
        agent = self._agent(monkeypatch, review_raises=True)
        agent.generate_with_collaboration(1, "第一章", "大纲" * 10, word_count=500)
        assert agent.last_chapter_quality is None

    def test_normal_review_still_scores(self, monkeypatch):
        """回归：兜底不能把正常评审也吞掉。"""
        agent = self._agent(monkeypatch, review_raises=False)
        agent.generate_with_collaboration(1, "第一章", "大纲" * 10, word_count=500)
        assert agent.last_chapter_quality == 90


# ====================================================================== 角色字段不得静默丢弃


class TestCharacterFieldMapping:
    """AI 输出 `background`，数据类字段叫 `backstory` —— 键名对不上就会**每次生成都丢**。"""

    @staticmethod
    def _profile(**data) -> CharacterProfile:
        char = CharacterProfile(data.get("name", "某人"))
        char._load_from_dict(data)
        return char

    def test_background_maps_to_backstory(self):
        char = self._profile(name="秦种玉", background="秦家匠户之后，十岁抵债入宗。")
        assert char.backstory == "秦家匠户之后，十岁抵债入宗。"

    def test_backstory_still_wins_when_both_present(self):
        char = self._profile(name="x", backstory="正式名", background="旧名")
        assert char.backstory == "正式名", "两个键同时存在时应优先 backstory"

    def test_goal_and_relationship_are_kept(self):
        char = self._profile(name="x", goal="查清抄家令", relationship_to_main="审问者与被审者")
        assert char.goal == "查清抄家令"
        assert char.relationship_to_main == "审问者与被审者"

    def test_skill_suggestions_are_kept(self):
        char = self._profile(name="x", skill_suggestions=["忘情诀", "牵丝锁脉"])
        assert char.skill_suggestions == ["忘情诀", "牵丝锁脉"]

    def test_skill_suggestions_tolerates_garbage(self):
        char = self._profile(name="x", skill_suggestions="不是列表")
        assert char.skill_suggestions == []

    def test_roundtrip_survives_save_and_load(self):
        """落盘再读回，新字段不能丢 —— 否则等于只修了内存。"""
        char = self._profile(
            name="x", background="背景", goal="目标", relationship_to_main="关系", skill_suggestions=["A"]
        )
        restored = CharacterProfile("x")
        restored._load_from_dict(char.to_dict())
        assert restored.backstory == "背景"
        assert restored.goal == "目标"
        assert restored.relationship_to_main == "关系"
        assert restored.skill_suggestions == ["A"]

    def test_old_file_without_new_keys_still_loads(self):
        """旧角色文件（只有 backstory）必须照常加载。"""
        char = self._profile(name="旧角色", backstory="老背景")
        assert char.backstory == "老背景"
        assert char.goal == ""
        assert char.skill_suggestions == []


# ====================================================================== concept 不得被提示词污染


class TestConceptNotPolluted:
    """18+/擦边提示词只用于本次生成，**不得写回 meta**。

    旧实现 `meta["concept"] = 概念 + 提示词`，而 `_auto_generate` 结尾会
    `update_meta(meta)` 落盘 ⇒ 用户的概念被挤占，且**每跑一次再追加一次**。
    """

    @staticmethod
    def _auto_generate_source() -> str:
        """取 `_auto_generate` 的函数体，并**剔除注释与文档块**。

        ❗ 必须剔注释：修复处的说明文字里就写着 `meta["concept"] = ...` 作为反面示例，
        不剔的话守卫会被自己的文档骗过（这个坑本项目踩过多次）。
        """
        import re

        source = (REPO / "app" / "generation_ui.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_auto_generate":
                body = source.splitlines()[node.lineno - 1 : node.end_lineno]
                kept = [line for line in body if not line.strip().startswith("#")]
                code = "\n".join(kept)
                return re.sub(r'"""[\s\S]*?"""', "", code)
        raise AssertionError("找不到 _auto_generate")

    def test_meta_concept_is_never_assigned(self):
        body = self._auto_generate_source()
        assert 'meta["concept"] =' not in body, "又在往 meta['concept'] 写东西了：提示词会被落盘并逐次堆叠"

    def test_content_hint_goes_to_local_variable(self):
        body = self._auto_generate_source()
        assert 'concept = f"{base_concept}' in body or "base_concept" in body, "提示词应拼到局部变量 concept 上"


# ====================================================================== 默认不思考


class TestThinkingDefaultsToOff:
    """**不传 `thinking_enabled` ⇒ 不思考。**

    改这条之前：`chat()` 默认跟随配置，而配置出厂是 `True`（设置页"深度思考"），
    于是全仓 57 处调用里 **38 处**都在思考 —— 这不是"想得更深"，是"写不出来"：
    思考与正文共用同一个 `max_tokens`，预算被吃光后 `content` 为空。
    """

    @staticmethod
    def _resolve(explicit, master):
        from app.ai_client import resolve_thinking_enabled

        return resolve_thinking_enabled(explicit, master)

    @pytest.mark.parametrize("master", [True, False])
    def test_unset_means_off(self, master):
        assert self._resolve(None, master) is False

    def test_explicit_false_stays_off(self):
        assert self._resolve(False, True) is False

    def test_explicit_true_works_when_master_on(self):
        """回归：关闭的修复不能把"显式要求思考"弄坏。"""
        assert self._resolve(True, True) is True

    def test_master_switch_can_veto(self):
        """设置里的总开关仍能一票否决。"""
        assert self._resolve(True, False) is False

    def test_chat_no_longer_defaults_to_config(self):
        """源码守卫：`chat()` 里不得再出现"默认继承配置"的写法。"""
        import re

        source = (REPO / "app" / "ai_client.py").read_text(encoding="utf-8")
        code = re.sub(r'"""[\s\S]*?"""', "", source)
        code = "\n".join(line for line in code.splitlines() if not line.strip().startswith("#"))
        assert 'kwargs.get("thinking_enabled", self._as_bool' not in code, (
            "又回到了「默认继承配置」——配置默认 True，等于全仓都在思考"
        )
        assert "resolve_thinking_enabled(" in code
