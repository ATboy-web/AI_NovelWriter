"""端到端：**创建作品 → 生成大纲 → 写作 → 保存 → 重启恢复 → 一致性校验**。

## 为什么这条用例重要

`tests/test_restart_recovery.py` 从"已经建好、已经写完的作品"起步，
验证的是**后半段**（重启后摘要/索引/评分还在）。但整条链路的前半段
——"建作品 → Agent 产出大纲 → Agent 产出正文 → 落盘"——从来没有被串起来测过。

这段链路的真实风险在于：**"生成"与"保存"分属两个模块**。
`NovelAgent.generate_chapter()` 只返回字符串、**不落盘**；落盘原本写在
`chapter_ui._save_chapter`（Tk 面板方法）里。于是：

- 面板里改一行路径，Agent 写得再好也不会进作品目录；
- 面板与生成面板各写一份保存逻辑，就是历史上"同一章两份摘要"的成因；
- 而这两处都因为依赖 Tk、依赖真实 AI，**无法被 CI 覆盖**。

2026-11-25 把落盘抽成 `application.SaveChapter` 之后，这条链路终于可以在
纯 Python 环境里完整跑一遍。本文件就是那条链路。

## AI 是怎么 mock 的

用 `MagicMock` 让 `ai.chat()` 依次返回大纲 JSON 与正文。
不 mock 生成算法本身 —— `generate_outline` / `generate_with_style` 都是**真跑**的，
只有最外层的网络调用被替换。

正文刻意用 `generate_with_style`（单次调用）而不是 `generate_chapter`（5Agent 协作）：
后者内置重复检测与重试 `sleep`，在 CI 里既慢又不稳定，
而它的编排逻辑已有 `test_agent_orchestrator_*` 专门覆盖。本文件的职责是
**数据链路**，不是编排质量。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

from app.application import SaveChapter
from app.memory_manager import MemoryManager
from app.novel_agent import NovelAgent
from app.novel_store import NovelStore

#  是 scripts/ 下的脚本（不在包内），要注 path 才能导入
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

import check_data_consistency as cdc  # noqa: E402

# ──────────────────────────────────────────────────────────── 工具


def _make_ai(*responses: str) -> MagicMock:
    """造一个按顺序返回固定文本的 AI 客户端。"""
    ai = MagicMock()
    ai.metrics = MagicMock()
    ai.chat.side_effect = list(responses) + [responses[-1]] * 20 if responses else [""]
    return ai


def _outline_json(count: int) -> str:
    return json.dumps(
        [
            {"chapter": i, "title": f"第{i}章 试炼", "summary": f"第{i}章梗概：林风继续前行。"}
            for i in range(1, count + 1)
        ],
        ensure_ascii=False,
    )


def _create_novel(root: Path, title: str = "重启之岛") -> Path:
    """步骤 1：新建一部作品（等价于面板「新建作品」做的事）。"""
    novel_dir = root / title
    novel_dir.mkdir(parents=True, exist_ok=True)
    store = NovelStore(novel_dir)
    store.write_meta(
        {
            "title": title,
            "genre": "玄幻",
            "total_chapters": 3,
            "chapter_count": 3,
            "created_at": "2026-11-25T00:00:00",
        }
    )
    store.write_outline([])
    return novel_dir


class _Session:
    """一次"打开作品"的完整上下文（重启 = 新建一个 Session）。"""

    def __init__(self, novel_dir: Path, ai: MagicMock | None = None):
        self.novel_dir = Path(novel_dir)
        self.ai = ai or _make_ai("")
        self.store = NovelStore(self.novel_dir)
        self.memory = MemoryManager(self.novel_dir)
        self.agent = NovelAgent(self.ai, self.memory)

    def meta(self) -> dict:
        return self.store.read_meta()

    def outline(self) -> list:
        return self.store.read_outline()

    def chapter_text(self, num: int) -> str:
        path = self.novel_dir / "chapters" / f"chapter_{num:04d}.txt"
        return path.read_text(encoding="utf-8") if path.exists() else ""


# ──────────────────────────────────────────────────────────── 主流程


class TestFullLifecycle:
    def test_create_outline_write_save_restart(self, tmp_path):
        """一条链路走完五个步骤，每一步的产物都必须是「磁盘上真的存在」。"""
        # ---- 1. 创建作品 ----
        novel_dir = _create_novel(tmp_path)
        session = _Session(novel_dir)
        assert session.meta()["title"] == "重启之岛"
        assert session.outline() == []

        # ---- 2. 生成大纲（真跑 Agent，只 mock 网络） ----
        ai = _make_ai(_outline_json(3))
        session = _Session(novel_dir, ai)
        outline = session.agent.generate_outline("玄幻", "重启之岛", chapter_count=3)
        assert len(outline) == 3, f"大纲生成数量不对：{outline}"
        session.store.write_outline(outline)
        assert len(session.outline()) == 3, "写进 outline.json 后读不回来"

        # ---- 3. 生成正文（真跑 Agent 的单次调用路径） ----
        body = session.agent.generate_with_style("写第1章", {"tone": "冷峻"}, word_count=200)
        assert body.strip(), "正文为空（mock 没生效？）"

        # ---- 4. 保存（走 application 用例，与面板同一条路径） ----
        result = SaveChapter().execute(novel_dir, 1, body)
        assert result.ok, result.reason
        assert result.path.exists()
        assert result.words > 0

        # ---- 5. 保存摘要（摘要的唯一权威） ----
        session.memory.save_chapter_summary(1, "第1章：林风发现岛上的异常潮汐。")

        # ---- 6. 重启：全新实例，只靠磁盘 ----
        reborn = _Session(novel_dir, _make_ai(""))

        assert reborn.meta()["title"] == "重启之岛", "重启后元数据丢失"
        assert len(reborn.outline()) == 3, "重启后大纲丢失"
        assert reborn.outline()[0]["title"] == "第1章 试炼", "大纲内容被改写"
        assert "冷峻" in reborn.chapter_text(1) or reborn.chapter_text(1), "重启后正文丢失"

        summary_files = list((novel_dir / "summaries").glob("*.txt")) if (novel_dir / "summaries").is_dir() else []
        assert summary_files, "重启后找不到章节摘要文件"

    def test_outline_survives_json_roundtrip_with_chinese(self, tmp_path):
        """大纲里有中文/标点时不能被写成转义序列（面板上会显示 \\uXXXX）。"""
        novel_dir = _create_novel(tmp_path)
        session = _Session(novel_dir)
        session.store.write_outline([{"chapter": 1, "title": "黑风岭·夜", "summary": "「引号」与——破折号"}])

        raw = (novel_dir / "outline.json").read_text(encoding="utf-8")
        assert "黑风岭" in raw, "中文被转义了（ensure_ascii 没关）"
        assert session.outline()[0]["title"] == "黑风岭·夜"

    def test_second_chapter_does_not_clobber_first(self, tmp_path):
        """连写两章：第 2 章落盘不能覆盖第 1 章（文件名模板相同的典型事故）。"""
        novel_dir = _create_novel(tmp_path)
        SaveChapter().execute(novel_dir, 1, "第一章正文")
        SaveChapter().execute(novel_dir, 2, "第二章正文")

        s = _Session(novel_dir)
        assert s.chapter_text(1) == "第一章正文"
        assert s.chapter_text(2) == "第二章正文"

    def test_resaving_same_chapter_overwrites_atomically(self, tmp_path):
        """重写同一章应覆盖而不是追加 —— 也验证原子写不会留下 .tmp 残片。"""
        novel_dir = _create_novel(tmp_path)
        SaveChapter().execute(novel_dir, 1, "第一版")
        SaveChapter().execute(novel_dir, 1, "第二版")

        s = _Session(novel_dir)
        assert s.chapter_text(1) == "第二版", "重写后内容不对（可能变成追加了）"
        leftovers = list((novel_dir / "chapters").glob("*.tmp*"))
        assert leftovers == [], f"原子写留下了临时文件：{leftovers}"


# ──────────────────────────────────────────────────────────── 失败路径


class TestLifecycleFailureModes:
    def test_empty_content_is_rejected_not_written(self, tmp_path):
        """空内容绝不落盘：写空文件等于把这一章的正文删了。"""
        novel_dir = _create_novel(tmp_path)
        result = SaveChapter().execute(novel_dir, 1, "   \n  ")

        assert result.ok is False
        assert "没有可保存的内容" in result.reason
        assert not (novel_dir / "chapters" / "chapter_0001.txt").exists(), "空内容竟然创建了文件"

    def test_missing_novel_dir_is_rejected(self, tmp_path):
        result = SaveChapter().execute("", 1, "正文")
        assert result.ok is False and "打开小说" in result.reason

    def test_invalid_chapter_number_rejected(self, tmp_path):
        novel_dir = _create_novel(tmp_path)
        assert SaveChapter().execute(novel_dir, 0, "正文").ok is False
        assert SaveChapter().execute(novel_dir, -3, "正文").ok is False

    def test_generation_failure_does_not_corrupt_existing_chapter(self, tmp_path):
        """生成失败（返回空）时，已有章节的内容必须原样保留。"""
        novel_dir = _create_novel(tmp_path)
        SaveChapter().execute(novel_dir, 1, "原有的第一章")

        ai = _make_ai("")  # 模型返回空
        session = _Session(novel_dir, ai)
        body = session.agent.generate_with_style("写第1章", {}, word_count=100)

        result = SaveChapter().execute(novel_dir, 1, body)
        assert result.ok is False, "空生成结果不该被保存"
        assert _Session(novel_dir).chapter_text(1) == "原有的第一章", "原文被空内容覆盖了"


# ──────────────────────────────────────────────────────────── 一致性校验


class TestConsistencyAfterLifecycle:
    def test_data_consistency_has_no_errors(self, tmp_path):
        """跑一遍作者自己的只读一致性检查器 —— 这是「Agent 与世界线状态一致性」
        在最朴素的形态：主流程走完后，章节数、摘要、索引三者互相自洽。"""
        novel_dir = _create_novel(tmp_path)
        session = _Session(novel_dir, _make_ai(_outline_json(2)))
        session.store.write_outline(session.agent.generate_outline("玄幻", "重启之岛", chapter_count=2))
        SaveChapter().execute(novel_dir, 1, "第一章正文" * 20)
        session.memory.save_chapter_summary(1, "第1章：开篇。")
        SaveChapter().execute(novel_dir, 2, "第二章正文" * 20)
        session.memory.save_chapter_summary(2, "第2章：承接。")

        report = cdc.check_novel(novel_dir)
        errors = [i for i in report.issues if getattr(i, "severity", "info") == "error"]
        assert not errors, "主流程走完后数据不自洽：\n" + "\n".join(str(e) for e in errors)

    def test_missing_chapter_is_detected(self, tmp_path):
        """反向断言：故意缺一章，检查器**必须**报出来（否则上面那条是空转）。"""
        novel_dir = _create_novel(tmp_path)
        SaveChapter().execute(novel_dir, 1, "第一章")
        SaveChapter().execute(novel_dir, 3, "第三章")  # 故意跳过第 2 章

        report = cdc.check_novel(novel_dir)
        text = " ".join(str(i) for i in report.issues)
        assert "2" in text, f"缺章没被报出来：{text}"


class TestSaveEventPayload:
    """`chapter.saved` 的载荷契约。

    这一个事件同时驱动四件事：时间线抽事件、用量面板记 token、
    角色面板刷新"出现章"、记忆可视化刷新。载荷少一个键，那四个消费者
    里就有一个静默失效 —— 而面板不会报错，只是"数据不动了"。
    """

    def test_payload_has_the_three_required_keys(self, tmp_path):
        novel_dir = _create_novel(tmp_path)
        result = SaveChapter().execute(novel_dir, 2, "正文内容")

        payload = result.event_payload(str(novel_dir))
        assert payload == {
            "novel_dir": str(novel_dir),
            "chapter": 2,
            "words": 4,
        }

    def test_payload_survives_empty_novel_dir(self):
        """`novel_dir` 传空时给空串而不是 None —— 消费者会直接拼字符串。"""
        result = SaveChapter().execute("/tmp/none", 1, "x")
        payload = result.event_payload("")
        assert payload["novel_dir"] == ""
        assert isinstance(payload["words"], int)
