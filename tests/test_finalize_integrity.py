"""定稿链与 meta 完整性门禁（D1–D5，来自《快速统治》运行时审计）。

来源：`docs/RUNTIME_AUDIT_20260917.md`、`docs/BACKLOG_REGISTER.md §5.7`。
五条缺陷都是**实跑数据里发现的**，且**与构建版本无关**（当时跑的是 v3.1.0 发布版）。

| ID | 缺陷 | 本文件钉住的性质 |
|---|---|---|
| D1 | 主角名被"整份覆盖"抹掉 | `update_meta` 不得覆盖磁盘独有键；`_auto_generate` 不得再用 `write_meta` |
| D2 | 摘要存成思维链 | 思维链必须被识别并弃用；摘要调用必须关思考且预算高于阈值 |
| D3 | 思维链污染记忆且类型错标 | 记忆块类型必须是 `summary`，不是 `plot` |
| D4 | 正文截断冒充摘要 | `_save_chapter_summary` 必须不存在（死写入 + 假摘要） |
| D5 | 世界线落盘提示词示例 | 示例回声必须被过滤，日志不得报假成功 |

这些缺陷有个共同特征：**全程没有任何异常、日志还显示成功**。
所以测试必须断言"落盘/传入的内容"本身，而不是"有没有抛错"。
"""

import ast
import inspect
import json
import re
from pathlib import Path

import pytest

from app import chapter_ui as chapter_ui_module
from app import generation_ui as generation_ui_module
from app import novel_agent as na
from app.novel_agent import _COT_MARKERS, _SUMMARY_MAX_CHARS, _looks_like_chain_of_thought
from app.novel_store import NovelStore

_REPO_ROOT = Path(__file__).resolve().parent.parent

#: 事故现场的真实文本：`summaries/chapter_00001_summary.txt` 的前几行
REAL_COT_SAMPLE = (
    "第1章摘要\n\n我们需要回答用户：“请生成摘要（100-200字）：” 然后给了第1章内容。"
    "需要生成摘要，100-200字。必须用中文，简洁概括。应提取关键剧情：玄元界中州，九霄宗药谷药奴陆昭。"
    "Count: 玄元界中州(5? 玄1元2界3中4州5，逗号?) 九霄宗药谷药奴陆昭无灵脉(??)."
)

#: 合格摘要（`memory/global_summary.txt` 的真实内容，140 字符）
CLEAN_SUMMARY_SAMPLE = (
    "玄元界中州，九霄宗药谷药奴陆昭无灵脉，却因过目不忘的药性天赋被丹师忌惮，"
    "命人将他投入九转魔鼎汤“喂鼎”。濒死之际，他心口浮现上古魔种，"
    "恰逢九霄宗女帝苏倾颜重伤潜入池底，借魔煞疗伤。"
)


def _method_ast(module, cls_name: str, method_name: str) -> ast.AST:
    """取某个方法的 AST 节点。

    ❗ **不要**用 `ast.parse(textwrap.dedent(inspect.getsource(fn)))`：`dedent` 求的是
    "所有非空白行的公共缩进前缀"，而本项目的函数体里存在**列 0 起始的多行字符串**，
    公共前缀因此变成空串 ⇒ dedent 实际什么都没去掉 ⇒ `unexpected indent`
    （第一版就栽在这里）。直接解析整个模块文件最稳：文件本身语法合法，
    再按"类名 → 方法名"定位节点即可。
    """
    path = Path(inspect.getsourcefile(module))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                    return child
    raise AssertionError(f"在 {path.name} 的 {cls_name} 里找不到方法 {method_name}")


# ─────────────────────────── D1 ───────────────────────────


class TestD1MetaOverwriteDoesNotWipeFields:
    """`update_meta` 是"读-改-写"，`write_meta` 是整份覆盖 —— 用错就会抹掉别的写入。"""

    def test_update_meta_preserves_disk_only_keys(self, tmp_path):
        """这是 D1 的核心机制：磁盘上已有、内存快照里没有的键，不得被覆盖。

        事故里 `protagonist` 就是这样丢的 —— 内存 `meta` 是函数开头读的快照，
        而 protagonist 是中途用 `update_meta` 写进磁盘的。
        """
        store = NovelStore(tmp_path)
        store.write_meta({"title": "快速统治", "chapter_count": 1})
        store.update_meta({"protagonist": "陆昭"})

        # 模拟 `_auto_generate`：拿一份**不含 protagonist 的旧快照**去写章节数
        stale_snapshot = {"title": "快速统治", "chapter_count": 5, "total_chapters": 1}
        store.update_meta(stale_snapshot)

        final = store.read_meta()
        assert final.get("protagonist") == "陆昭", "磁盘独有键被旧快照覆盖抹掉了（D1 回退）"
        assert final["chapter_count"] == 5, "本次要更新的字段反而没生效"

    def test_write_meta_would_have_wiped_it(self, tmp_path):
        """反证：同样的场景用 `write_meta` 就会丢 —— 证明上一条不是空转。"""
        store = NovelStore(tmp_path)
        store.write_meta({"title": "快速统治", "chapter_count": 1})
        store.update_meta({"protagonist": "陆昭"})

        stale_snapshot = {"title": "快速统治", "chapter_count": 5, "total_chapters": 1}
        store.write_meta(stale_snapshot)

        assert "protagonist" not in store.read_meta(), (
            "整份覆盖竟然保留了这个键 —— 那么上一个测试就没有区分力，需重新设计"
        )

    def test_auto_generate_no_longer_full_overwrites_meta(self):
        """源码守卫：`_auto_generate` 里不得再出现整份覆盖的 `write_meta` **调用**。

        ⚠️ 必须用 AST 找**真实调用**，不能做字符串匹配 —— `_auto_generate` 里有
        "这里曾用 `write_meta(meta)`" 这样的说明性注释，字符串搜索会把注释判成违规
        （第一版就误报了自己）。这与"源码扫描型守卫必须剔除注释与 docstring"是同一条教训。
        """
        node = _method_ast(generation_ui_module, "GenerationMixin", "_auto_generate")
        offenders = [ast.unparse(call.func) for call in ast.walk(node) if isinstance(call, ast.Call)]
        offenders = [x for x in offenders if x.endswith(".write_meta")]
        assert not offenders, f"_auto_generate 又用整份覆盖写 meta 了（{offenders}）—— 会抹掉磁盘独有键（D1 回退）"

    def test_auto_generate_syncs_protagonist_into_memory_snapshot(self):
        """写完 protagonist 必须同步回内存副本，否则两个大纲生成读不到它。"""
        node = _method_ast(generation_ui_module, "GenerationMixin", "_auto_generate")
        assigned = {ast.unparse(t) for n in ast.walk(node) if isinstance(n, ast.Assign) for t in n.targets}
        assert "meta['protagonist']" in assigned, (
            f"protagonist 没有同步回内存 meta —— 整体/故事大纲会再次失去主角约束（D1 回退）。"
            f"实测赋值目标：{sorted(assigned)}"
        )

    def test_outline_generators_read_protagonist_from_their_meta_argument(self):
        """两个大纲生成函数的`protagonist`判据必须来自入参（它们拿不到磁盘）。

        这条是"约束在哪一环断掉"的定位断言：只要它们依赖入参，
        上游就必须保证入参里有 protagonist。
        """
        for fn in (
            generation_ui_module.GenerationMixin._generate_overall_outline,
            generation_ui_module.GenerationMixin._generate_story_outlines,
        ):
            src = inspect.getsource(fn)
            assert 'meta.get("protagonist"' in src, f"{fn.__name__} 不再从入参取主角"


# ─────────────────────────── D2 ───────────────────────────


class TestD2ChainOfThoughtDetection:
    """摘要类返回必须能识别出"这是推理过程"。"""

    def test_real_incident_text_is_detected(self):
        assert _looks_like_chain_of_thought(REAL_COT_SAMPLE), "事故现场的那段文本没被识别为思维链"

    def test_clean_summary_is_accepted(self):
        assert not _looks_like_chain_of_thought(CLEAN_SUMMARY_SAMPLE), "合格摘要被误判成思维链"

    def test_empty_is_not_cot(self):
        """空串不是"思维链" —— 它由调用方按"返回为空"另行处理。"""
        assert not _looks_like_chain_of_thought("")
        assert not _looks_like_chain_of_thought("   ")

    def test_overlong_is_rejected(self):
        """提示词要 100–200 字；超长即异常，与特征词无关。"""
        assert _looks_like_chain_of_thought("好" * (_SUMMARY_MAX_CHARS + 1))

    def test_boundary_length_is_accepted(self):
        assert not _looks_like_chain_of_thought("好" * _SUMMARY_MAX_CHARS)

    @pytest.mark.parametrize("marker", _COT_MARKERS)
    def test_every_marker_is_detected(self, marker):
        assert _looks_like_chain_of_thought(f"{marker}一些后续内容"), f"特征词 {marker!r} 未被识别"

    def test_marker_only_checked_at_head(self):
        """特征词只在开头扫 —— 正文里正当引用这些词不该被误伤。

        ⚠️ 构造文本时必须让总长**超过 300 字**，否则整个文本都在窗口内，
        这条断言就成了空转（第一版就写错了：218 字时标记必然落在窗口里）。
        """
        text = "陆昭缓缓开口：" + "好" * 400 + "我们需要回答用户的问题"
        assert len(text) > 300, "样本太短，标记会落进扫描窗口，断言无区分力"
        assert len(text) <= _SUMMARY_MAX_CHARS, "样本超长会被长度判据拦下，干扰本用例"
        assert not _looks_like_chain_of_thought(text)

    def test_marker_within_head_is_detected(self):
        """反证：同样的标记若落在开头，必须被识别 —— 证明上一条不是恒真。"""
        text = "我们需要回答用户的问题" + "好" * 400
        assert _looks_like_chain_of_thought(text)


class TestD2SummaryCallParameters:
    """摘要调用必须关思考、且预算高于思考阈值 —— 否则会踩"预算被思考吃光"的坑。"""

    def test_max_tokens_exceeds_thinking_threshold(self):
        from app.providers.reasoning import THINKING_MIN_TOKENS

        src = inspect.getsource(na.NovelAgent.finalize_chapter)
        # 抓摘要调用的 max_tokens 字面量
        values = [int(m) for m in re.findall(r"max_tokens=(\d+)", src)]
        assert values, "在 finalize_chapter 里找不到 max_tokens 字面量"
        assert all(v > THINKING_MIN_TOKENS for v in values), (
            f"有 max_tokens={min(values)} 未超过 THINKING_MIN_TOKENS={THINKING_MIN_TOKENS}"
            "（旧值 1000 恰好等于阈值，思考没被禁用但预算不够输出）"
        )

    def test_thinking_explicitly_disabled(self):
        src = inspect.getsource(na.NovelAgent.finalize_chapter)
        assert "thinking_enabled=False" in src, "摘要/关键词调用没有显式关闭思考（D2 回退）"


class TestD2FinalizeStoresSafeSummary:
    """端到端：AI 返回思维链时，落盘的摘要绝不能是它。"""

    def _agent(self, replies, tmp_dir):
        """造一个最小 agent：`ai.chat` 按调用顺序返回 `replies`。"""
        agent = na.NovelAgent.__new__(na.NovelAgent)
        agent.QUALITY_THRESHOLD = 75
        agent.last_chapter_quality = None
        calls = []

        class _AI:
            def chat(self, messages, system="", **kwargs):
                calls.append({"system": system, **kwargs})
                return replies[min(len(calls) - 1, len(replies) - 1)]

        agent.ai = _AI()
        agent._calls = calls
        agent.saved = {}

        class _Mem:
            def save_chapter_summary(self, n, s):
                agent.saved["chapter"] = s

            def get_global_summary(self):
                return "旧全局摘要"

            def save_global_summary(self, s):
                agent.saved["global"] = s

            def update_index(self, n, kws):
                agent.saved["index"] = kws

            def add_chunk(self, t, content, importance=5, tags=None):
                agent.saved["chunk"] = {"type": t, "content": content}

            def add_event(self, *a, **k):
                pass

            def get_characters(self):
                return {}

            # ❗ `novel_dir` 不能留成 `None`：调用方会 `str(...)` 它，
            # `str(None) == "None"` 是**真值**，于是 `writing_skills` 的
            # `if novel_dir:` 通过，并在**当前工作目录**下真的建出 `None/writing_skills/`
            # （第一版就制造了这个污染目录，已清理）。指向临时目录才是干净做法。
            novel_dir = tmp_dir

        agent.memory = _Mem()
        agent.log = lambda *a, **k: None
        agent._update_character_progression = lambda *a, **k: None
        return agent

    def test_cot_reply_is_not_stored_as_summary(self, tmp_path):
        agent = self._agent([REAL_COT_SAMPLE], tmp_path)
        agent.finalize_chapter(1, "正文" * 500)
        stored = agent.saved.get("chapter", "")
        assert stored != REAL_COT_SAMPLE, "思维链被原样存成了摘要（D2 回退）"
        assert not _looks_like_chain_of_thought(stored)
        # 降级值应当是正文截断（200 字），而不是空
        assert stored, "弃用思维链后没有留下任何摘要"

    def test_clean_reply_is_stored(self, tmp_path):
        agent = self._agent([CLEAN_SUMMARY_SAMPLE], tmp_path)
        agent.finalize_chapter(1, "正文" * 500)
        assert agent.saved.get("chapter") == CLEAN_SUMMARY_SAMPLE

    def test_summary_always_saved_even_when_reply_empty(self, tmp_path):
        """旧实现只在 `if result:` 分支里保存 ⇒ 返回空时**一条摘要都不写**。"""
        agent = self._agent([""], tmp_path)
        agent.finalize_chapter(1, "正文" * 500)
        assert agent.saved.get("chapter"), "AI 返回空时没有降级保存摘要（旧实现的缺口）"

    def test_global_summary_keeps_old_when_reply_is_cot(self, tmp_path):
        """全局摘要会被注入每一章上下文，写进推理过程的代价比章节摘要更大。"""
        agent = self._agent([CLEAN_SUMMARY_SAMPLE, REAL_COT_SAMPLE, "关键词1,关键词2"], tmp_path)
        agent.finalize_chapter(1, "正文" * 500)
        assert agent.saved.get("global") != REAL_COT_SAMPLE

    def test_thinking_disabled_is_passed_to_every_finalize_call(self, tmp_path):
        agent = self._agent([CLEAN_SUMMARY_SAMPLE, CLEAN_SUMMARY_SAMPLE, "a,b"], tmp_path)
        agent.finalize_chapter(1, "正文" * 500)
        assert agent._calls, "没有记录到任何调用"
        assert all(c.get("thinking_enabled") is False for c in agent._calls), (
            f"有 finalize 调用没关思考：{[c.get('thinking_enabled') for c in agent._calls]}"
        )


# ─────────────────────────── 附带发现 ───────────────────────────


class TestNoStrayNoneDirectory:
    """审计期间顺手发现的缺陷：`str(None)` 会在当前目录建出 `None/`。

    `novel_agent.finalize_chapter` 里原来写的是
    `novel_dir = str(self.memory.novel_dir) if self.memory else None`。
    `self.memory` 存在但 `novel_dir` 为 None 时，`str(None)` 得到**真值字符串 `"None"`**，
    而 `writing_skills` 的判据是 `if novel_dir:` ⇒ 通过 ⇒ 在**当前工作目录**
    真的建出 `None/writing_skills/{knowledge_graph,time_memory}.json`。
    （写测试时实测复现，仓库里出现过这个目录。）

    教训与 D1 同源：**判据要落在"值"上，而不是"对象是否存在"**。
    """

    def test_none_novel_dir_does_not_create_stray_directory(self, tmp_path, monkeypatch):
        agent = na.NovelAgent.__new__(na.NovelAgent)
        agent.QUALITY_THRESHOLD = 75
        agent.last_chapter_quality = None

        class _AI:
            def chat(self, *a, **k):
                return "合格摘要"

        class _Mem:
            novel_dir = None  # ← 关键：值本身是 None

            def save_chapter_summary(self, n, s):
                pass

            def get_global_summary(self):
                return ""

            def save_global_summary(self, s):
                pass

            def update_index(self, n, k):
                pass

            def add_chunk(self, *a, **k):
                pass

            def add_event(self, *a, **k):
                pass

            def get_characters(self):
                return {}

        agent.ai = _AI()
        agent.memory = _Mem()
        agent.log = lambda *a, **k: None
        agent._update_character_progression = lambda *a, **k: None

        monkeypatch.chdir(tmp_path)
        agent.finalize_chapter(1, "正文" * 300)

        stray = tmp_path / "None"
        assert not stray.exists(), (
            f'`novel_dir=None` 时在当前目录建出了 {stray} —— 调用方又用 `str(...)` 把它变成了真值字符串 `"None"`'
        )


# ─────────────────────────── D3 ───────────────────────────


class TestD3ChunkTypeIsAccurate:
    """记忆块类型必须与内容相符。"""

    def test_summary_chunk_is_typed_summary_not_plot(self):
        src = inspect.getsource(na.NovelAgent.finalize_chapter)
        assert 'add_chunk("summary"' in src, "记忆块没有用 `summary` 类型（D3 回退）"
        assert 'add_chunk("plot"' not in src, "记忆块又标成了 `plot`，但内容其实是摘要（D3 回退）"

    def test_no_other_caller_depends_on_plot_type(self):
        """改类型前确认过：全仓对 `"plot"` 的引用只有这一处，没有检索方过滤它。

        这条守卫防的是"以后有人加了按 plot 过滤的检索"，那会让本次改名变危险。
        """
        offenders = []
        for path in (_REPO_ROOT / "app").rglob("*.py"):
            src = path.read_text(encoding="utf-8")
            for m in re.finditer(r'"plot"', src):
                # 允许出现"记忆块类型"的说明性注释，但不允许作为检索条件
                line = src[src.rfind("\n", 0, m.start()) : src.find("\n", m.end())]
                if 'add_chunk("plot"' in line or '== "plot"' in line or '.get("type")' in line:
                    offenders.append(f"{path.relative_to(_REPO_ROOT)}: {line.strip()}")
        assert not offenders, f"出现了新的 `plot` 类型引用，请重新评估改名风险：{offenders}"


# ─────────────────────────── D4 ───────────────────────────


class TestD4NoFabricatedSummary:
    """不得再用正文截断冒充摘要。"""

    def test_truncation_writer_is_gone(self):
        assert not hasattr(chapter_ui_module.ChapterUIMixin, "_save_chapter_summary"), (
            "`_save_chapter_summary`（content[:500] 冒充摘要）又回来了（D4 回退）"
        )

    def test_display_chapter_does_not_spawn_summary_writer(self):
        src = inspect.getsource(chapter_ui_module.ChapterUIMixin._display_chapter)
        assert "_save_chapter_summary" not in src, "浏览章节时又在写假摘要（D4 回退）"

    def test_no_four_digit_summary_writer_remains(self):
        """`04d` 的摘要只写不读 —— 它同时是 D4 的假摘要与命名不一致的来源。"""
        offenders = []
        for path in (_REPO_ROOT / "app").rglob("*.py"):
            src = path.read_text(encoding="utf-8")
            if re.search(r"chapter_\{[^}]*:04d\}_summary\.txt", src):
                rel = path.relative_to(_REPO_ROOT).as_posix()
                # 分支世界线（`timeline_ui`）写的是 branch_dir 下的独立目录，另论
                if not rel.endswith("timeline_ui.py"):
                    offenders.append(rel)
        assert not offenders, f"主线上又出现了 4 位补零的摘要写入点：{offenders}"

    def test_summary_reader_uses_five_digits(self):
        """唯一读取方必须与权威写入方（`memory_manager.py:378`，05d）一致。"""
        src = inspect.getsource(generation_ui_module.GenerationMixin)
        assert "chapter_{n:05d}_summary.txt" in src, "章节回顾读的位数与写入方不一致了"


# ─────────────────────────── D5 ───────────────────────────


class TestD5WorldlineExampleEchoFiltered:
    """世界线不得把提示词示例当成决策落盘。"""

    #: 事故现场落盘的内容
    LEGACY_EXAMPLE = {
        "desc": "当时的情况",
        "chosen": "主角选择了什么",
        "alternative": "可能的另一种选择",
    }

    def _run(self, tmp_path, decisions):
        agent = generation_ui_module.GenerationMixin.__new__(generation_ui_module.GenerationMixin)
        agent.current_novel_dir = tmp_path
        agent._log = lambda *a, **k: logs.append(a[0] if a else "")
        logs = []
        agent._parse_json_response = lambda resp, default, is_list=False: {"decisions": decisions}

        class _AI:
            def chat(self, *a, **k):
                return json.dumps({"decisions": decisions}, ensure_ascii=False)

        agent.ai_client = _AI()
        agent._auto_detect_decisions(1, "正文" * 300)
        timeline = json.loads((tmp_path / "timelines" / "main.json").read_text(encoding="utf-8"))
        return timeline, logs

    def test_legacy_example_echo_is_not_recorded(self, tmp_path):
        timeline, logs = self._run(tmp_path, [self.LEGACY_EXAMPLE])
        assert timeline["branches"] == [], "提示词示例被当成决策落盘了（D5 回退）"
        assert timeline["events"] == []

    def test_log_does_not_claim_false_success(self, tmp_path):
        """旧实现打印 `len(decisions)`，全部是示例时仍显示"记录1个决策点"。"""
        _, logs = self._run(tmp_path, [self.LEGACY_EXAMPLE])
        joined = "\n".join(logs)
        assert "记录1个决策点" not in joined, f"日志仍在报假成功：{joined}"
        assert "已跳过" in joined or "未记录" in joined, f"日志没有说明示例被跳过：{joined}"

    def test_real_decision_is_recorded(self, tmp_path):
        real = {
            "desc": "陆昭在药谷池底发现上古魔种",
            "chosen": "主动吞噬魔种",
            "alternative": "呼救引来外门弟子",
        }
        timeline, logs = self._run(tmp_path, [real])
        assert len(timeline["branches"]) == 1, "真实决策被误过滤了"
        assert timeline["branches"][0]["chosen"] == "主动吞噬魔种"
        assert "记录1个决策点" in "\n".join(logs)

    def test_mixed_batch_keeps_only_the_real_one(self, tmp_path):
        real = {"desc": "陆昭被投入魔鼎汤", "chosen": "隐忍等待时机", "alternative": "当场反抗"}
        timeline, _ = self._run(tmp_path, [self.LEGACY_EXAMPLE, real])
        assert len(timeline["branches"]) == 1
        assert timeline["branches"][0]["chosen"] == "隐忍等待时机"

    def test_new_example_style_is_also_filtered(self, tmp_path):
        """新提示词的示例带「示例·勿照抄」标记，照抄后也必须被拦。"""
        echo = {
            "desc": "【示例·勿照抄】此条仅示范 JSON 结构，请替换为本章真实情况",
            "chosen": "【示例·勿照抄】主角实际做出的选择",
            "alternative": "【示例·勿照抄】未被选中的另一条路",
        }
        timeline, _ = self._run(tmp_path, [echo])
        assert timeline["branches"] == [], "带【示例·勿照抄】标记的内容没被过滤"

    def test_prompt_forbids_copying_the_example(self):
        """提示词本身要明确禁止照抄 —— 过滤是兜底，不是唯一防线。"""
        src = inspect.getsource(generation_ui_module.GenerationMixin._auto_detect_decisions)
        assert "勿照抄" in src, "提示词里的示例没有「勿照抄」标记，模型又可能原样返回"
        assert "禁止" in src, "提示词没有显式禁止原样输出示例"
