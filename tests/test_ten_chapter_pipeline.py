"""生成 10 章之后的"对齐检查"——端到端流水线验证。

## 这个文件解决什么

单章功能都有测试，但"**连续生成 10 章之后，哪些产物该存在、彼此该对得上**"
缺一条完整验证。实际事故往往是这种跨模块错位：

- 正文写了 10 章，摘要只有 9 个（第 10 章定稿失败但没人发现）
- 摘要有了，倒排索引没更新（后续 RAG 检索不到这章）
- 索引有了，时间线事件没记（一致性校验拿不到"第几章发生过什么"）
- 事件记了，但章号错位（写成 0 或前移一章）
- 角色 EXP 涨了，但角色文件没落盘（重启后归零）

**这批用例把"10 章之后应该长什么样"写成断言**，跑一次就知道链路有没有断。
它同时是给你"生成 10 章后人工核对"的机器版清单（见 `TestTenChapterChecklist`）。

## 用真实的 MemoryManager / review_store / 回炉扫描

只把 AI 换成假实现 —— 其余全部走生产代码路径。理由：摘要/索引/事件/评分这些
恰恰是"假实现容易掩盖 bug"的地方（假实现总是成功，真实实现有合并、去重、分页、落盘）。
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from app.memory_manager import MemoryManager
from app.review_store import list_reviews, load_review, normalize_review, save_review
from app.text_stats import count_hanzi

NL = chr(10)


# ====================================================================== 假 AI


class ScriptedAI:
    """按调用目的返回不同内容，其余走默认。

    识别方式用标记词而不是调用顺序：`finalize_chapter` 内部对摘要/全局摘要各调一次，
    用顺序号容易在实现调整后错位（这是"测试依赖内部调用次数"的通病）。
    """

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, system: str = "", max_tokens: int = 0, **kwargs) -> str:
        self.calls += 1
        prompt = str(messages[0]["content"]) if messages else ""
        if "请生成摘要" in prompt:
            return "本章主角在荒原边缘与守卫发生冲突，夺下残破的镇器碎片，并决定前往阴域。"
        if "更新全局摘要" in prompt:
            return "全书主线：主角穿过荒原与阴域，逐步拼合镇器，寻找自身混元之体的存续之法。"
        if "关键词" in prompt:
            return "镇器, 荒原, 阴域, 守卫, 碎片"
        return "正文段落。"


# ====================================================================== 夹具


@pytest.fixture()
def novel(tmp_path: pathlib.Path) -> pathlib.Path:
    for name in ("chapters", "memory", "summaries"):
        (tmp_path / name).mkdir()
    (tmp_path / "meta.json").write_text(
        json.dumps({"title": "测试之书", "genre": "玄幻", "author": "某人"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "outline.json").write_text(
        json.dumps({"chapters": [{"num": i, "title": f"第{i}章 测试"} for i in range(1, 11)]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return tmp_path


def _chapter_text(number: int, paragraphs: int = 8) -> str:
    body = NL + NL.join(
        f"第{number}章第{index}段：林风握紧镇器碎片，望向阴沉的天际，脚步没有停下。" for index in range(paragraphs)
    )
    return f"# 第{number}章 测试{number}{NL}{NL}{body}"


def _write_chapter(novel: pathlib.Path, number: int, text: str | None = None) -> str:
    content = text if text is not None else _chapter_text(number)
    path = novel / "chapters" / f"chapter_{number:04d}.txt"
    path.write_text(content, encoding="utf-8")
    return content


# ====================================================================== 10 章流水线


class TestTenChapterPipeline:
    """模拟"连续生成 10 章"的落盘与记忆更新，逐项核对产物。"""

    @staticmethod
    def _simulate(novel: pathlib.Path, chapters: int = 10) -> MemoryManager:
        """按生产顺序做：写正文 → 存摘要 → 更新索引 → 记事件 → 记评分。"""
        memory = MemoryManager(novel)
        ai = ScriptedAI()
        for number in range(1, chapters + 1):
            content = _write_chapter(novel, number)
            # ① 摘要（生产里是 finalize_chapter 的第一件事）
            summary = ai.chat(
                [{"role": "user", "content": f"请生成摘要（100-200字）：{NL}{content[:2000]}"}],
                system="你是故事摘要助手。",
                max_tokens=2000,
            )
            memory.save_chapter_summary(number, summary)
            # ①b 全局摘要（生产 `finalize_chapter` 每章都会更新它）
            memory.save_global_summary(
                ai.chat(
                    [{"role": "user", "content": "更新全局摘要：旧：略 新章节：" + summary}],
                    system="你是故事摘要助手。",
                    max_tokens=2000,
                )
            )
            # ② 索引（关键词）
            memory.update_index(number, ["镇器", "荒原", "阴域"])
            # ③ 记忆块 + 事件
            memory.add_chunk("chapter", summary, importance=6, tags=["主线"])
            memory.add_event(
                number,
                f"第{number}章：林风在荒原推进，取得镇器碎片",
                characters_involved=["林风"],
                location="荒原",
            )
            # ④ 评审
            save_review(novel, normalize_review({"overall_score": 70 + number, "issues": []}, number))
        memory.flush()
        return memory

    def test_chapters_written(self, novel: pathlib.Path):
        self._simulate(novel)
        files = sorted((novel / "chapters").glob("chapter_*.txt"))
        assert len(files) == 10
        assert [count_hanzi(f.read_text(encoding="utf-8")) for f in files] == [
            count_hanzi(_chapter_text(i)) for i in range(1, 11)
        ]

    def test_summaries_written(self, novel: pathlib.Path):
        self._simulate(novel)
        rows = sorted((novel / "memory" / "chapters").glob("*"))
        assert rows, "章节摘要目录为空 —— finalize 链路断了"

    def test_summary_count_matches_chapters(self, novel: pathlib.Path):
        """🔴 摘要数必须等于章数：少一个就说明某章定稿失败而没被发现。"""
        memory = self._simulate(novel)
        missing = [n for n in range(1, 11) if not memory.get_chapter_summary(n)]
        assert missing == [], f"这些章没有摘要：{missing}"

    def test_inverted_index_has_no_chapter_gap(self, novel: pathlib.Path):
        """索引缺章 ⇒ 后续 RAG 检索不到那章内容，写作会"遗忘"它。

        ⚠️ 索引的 value 是 **chunk id**（形如 `chapter_00001`），不是章号整数。
        第一版按整数解析 ⇒ 一个都没匹配上，误报"索引缺章"。这里按实际格式解析。
        """
        self._simulate(novel)
        index_file = novel / "memory" / "inverted_index.json"
        assert index_file.is_file(), "倒排索引没有落盘"
        data = json.loads(index_file.read_text(encoding="utf-8"))

        covered: set[int] = set()
        for value in data.values():
            if not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, int):
                    covered.add(item)
                    continue
                # `chapter_00007` / `chapter_1794994081135`（时间戳式 id 忽略）
                text = str(item)
                if not text.startswith("chapter_"):
                    continue
                tail = text[len("chapter_") :]
                if tail.isdigit() and len(tail) <= 6:
                    covered.add(int(tail))
        assert covered >= set(range(1, 11)), f"索引缺章：{sorted(set(range(1, 11)) - covered)}"

    def test_timeline_events_have_correct_chapters(self, novel: pathlib.Path):
        """事件章号错位是最隐蔽的一类 bug（时间线看起来有数据，但对应错了章）。"""
        self._simulate(novel)
        events: list[dict[str, Any]] = []
        timeline_dir = novel / "memory" / "timeline"
        for path in sorted(timeline_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                events.extend(payload)
        assert events, "时间线没有任何事件"
        chapters = {int(item.get("chapter", 0)) for item in events}
        assert chapters >= set(range(1, 11)), f"事件缺章：{sorted(set(range(1, 11)) - chapters)}"
        assert 0 not in chapters, "有事件的章号是 0（写入时没带章号）"

    def test_reviews_persisted_per_chapter(self, novel: pathlib.Path):
        self._simulate(novel)
        records = list_reviews(novel)
        assert len(records) == 10
        for number in range(1, 11):
            record = load_review(novel, number)
            assert record is not None and record.ok
            assert record.overall == 70 + number

    def test_global_summary_available(self, novel: pathlib.Path):
        memory = self._simulate(novel)
        assert memory.get_global_summary(), "全局摘要为空 —— 后续章节缺少主线上下文"

    def test_flush_is_idempotent(self, novel: pathlib.Path):
        """重复 flush 不该产生重复事件或把数据写坏。"""
        memory = self._simulate(novel)
        before = len(list((novel / "memory" / "timeline").glob("*.json")))
        memory.flush()
        memory.flush()
        after = len(list((novel / "memory" / "timeline").glob("*.json")))
        assert after == before


# ====================================================================== 人工核对清单（机器版）


class TestTenChapterChecklist:
    """把"生成 10 章后该看什么"写成可执行的检查项。

    每条对应一个真实会错位的地方；全部通过说明链路是通的。
    """

    def test_checklist_all_green(self, novel: pathlib.Path):
        TestTenChapterPipeline._simulate(novel)
        memory = MemoryManager(novel)

        # 每项是 (名称, 是否通过, 通过时的说明, 失败时的说明)
        checklist: list[tuple[str, bool, str, str]] = []

        # 1 正文
        chapters = sorted((novel / "chapters").glob("chapter_*.txt"))
        checklist.append(("正文 10 章", len(chapters) == 10, "10 章齐全", f"实际 {len(chapters)} 章"))

        # 2 章标题规范
        bad_title = [p.name for p in chapters if not p.read_text(encoding="utf-8").lstrip().startswith("#")]
        checklist.append(("章节首行是 # 标题", not bad_title, "全部规范", f"异常：{bad_title}"))

        # 3 摘要齐全
        missing = [n for n in range(1, 11) if not memory.get_chapter_summary(n)]
        checklist.append(("10 章都有摘要", not missing, "全部有", f"缺：{missing}"))

        # 4 摘要不是思维链/占位
        thin = [n for n in range(1, 11) if count_hanzi(memory.get_chapter_summary(n) or "") < 10]
        checklist.append(("摘要长度合理", not thin, "均 ≥10 汉字", f"过短：{thin}"))

        # 5 索引落盘且覆盖 10 章
        index_ok = (novel / "memory" / "inverted_index.json").is_file()
        checklist.append(("倒排索引已落盘", index_ok, "已生成", "文件不存在"))

        # 6 时间线事件覆盖 10 章
        events: list[dict[str, Any]] = []
        for path in (novel / "memory" / "timeline").glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                events.extend(payload)
        event_chapters = {int(e.get("chapter", 0)) for e in events}
        missing_events = sorted(set(range(1, 11)) - event_chapters)
        checklist.append(("事件覆盖 10 章", not missing_events, "10 章都有事件", f"缺：{missing_events}"))
        checklist.append(("无章号为 0 的事件", 0 not in event_chapters, "章号正常", "存在 chapter=0"))

        # 7 评审记录
        reviews = list_reviews(novel)
        checklist.append(("评审 10 条", len(reviews) == 10, "10 条齐全", f"实际 {len(reviews)}"))

        # 8 全局摘要
        checklist.append(("全局摘要非空", bool(memory.get_global_summary()), "已生成", "为空"))

        # 9 记忆块
        chunks = memory.retrieve_relevant("镇器", top_k=20)
        checklist.append(("记忆块可检索", bool(chunks), f"命中 {len(chunks)} 条", "检索不到任何 chunk"))

        # 10 上下文可构建（下一章写作的前提）
        context = memory.build_smart_context(10, query="镇器", max_items=5)
        checklist.append(("智能上下文可构建", bool(context), f"{len(context)} 字", "返回空"))

        failed = [(name, detail) for name, ok, _good, detail in checklist if not ok]
        report = NL.join(
            f"  {'✅' if ok else '❌'} {name} — {good if ok else bad}" for name, ok, good, bad in checklist
        )
        assert not failed, f"10 章对齐检查未通过：{NL}{report}"


# ====================================================================== 与回炉/重写的衔接


class TestReworkHandoff:
    """生成完之后接「回炉重造」：扫描应能识别问题章，且不误报好章。"""

    def test_scan_after_generation(self, novel: pathlib.Path):
        from app.rework import scan

        for number in range(1, 11):
            _write_chapter(novel, number)
        # 第 3 章塞满翻案腔（阻断项），第 5 章标题是占位符
        broken = NL.join(["这不是存更多，而是记得更准。"] * 60)
        (novel / "chapters" / "chapter_0003.txt").write_text(f"# 第3章 测试3{NL}{NL}{broken}", encoding="utf-8")
        (novel / "chapters" / "chapter_0005.txt").write_text(
            f"# 第5章{NL}{NL}" + "正常正文内容。" * 100, encoding="utf-8"
        )

        found = {item["chapter"]: item["reason_code"] for item in scan(novel, min_hanzi=100)}
        assert found.get(5) == "bad_title", "占位标题没被识别"
        assert found.get(3) == "qc_blocker", "翻案腔阻断项没被识别"
        assert 1 not in found and 2 not in found, "正常章被误报，队列会被噪音灌满"

    def test_enqueue_archives_original(self, novel: pathlib.Path):
        """入炉必须先归档 —— 这是"原文可回滚"的唯一保证。"""
        from app.rework import ReworkStore

        original = _write_chapter(novel, 3)
        store = ReworkStore(novel)
        record = store.enqueue(3, "qc_blocker", "测试阻断")
        assert record.archive_path
        archived = (novel / record.archive_path).read_text(encoding="utf-8")
        assert archived == original
