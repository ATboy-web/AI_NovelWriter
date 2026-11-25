"""重启恢复测试：**关掉再打开，数据还在不在**。

## 为什么这是最该补的一环

架构评审的原话：「小说主流程端到端测试：创建项目 → 生成大纲 → 写作 → 保存 → **重启恢复**」。
前四步已有覆盖（`test_ten_chapter_pipeline` 验证 10 章之后的产物对齐），
但**重启**这一段没有 —— 而它恰恰是用户最常遇到、也最容易静默丢数据的地方：

- 摘要写进了内存缓存、没落盘 ⇒ 重启后消失
- 倒排索引只在内存里更新 ⇒ 重启后检索不到旧章节
- 检查点没被识别 ⇒ 上次中断的生成任务无人接管
- 配置文件半写 ⇒ 重启直接崩在加载阶段

## 怎么模拟"重启"

不启动 Tk、不重启进程，而是**丢弃所有内存对象、重新构造**：
`MemoryManager(novel_dir)` 的全部状态都从磁盘加载，因此"新建一个实例"
在语义上等价于"重启后的首次加载"。这比启动整个 GUI 更稳、更快、也更专注。

`AppConfig` 会写 `Path.home()`，所以那一组用例显式注入临时 home，
避免污染真实用户配置（这也是本仓踩过的坑）。
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.config import AppConfig
from app.memory_manager import MemoryManager
from app.persistence_ui import PersistenceMixin

NL = chr(10)


# ====================================================================== 夹具


@pytest.fixture()
def novel(tmp_path: pathlib.Path) -> pathlib.Path:
    """一部刚建好的作品（只有 meta/outline，没有任何章节产物）。"""
    for name in ("chapters", "memory", "summaries"):
        (tmp_path / name).mkdir()
    (tmp_path / "meta.json").write_text(
        json.dumps({"title": "重启之书", "genre": "玄幻"}, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "outline.json").write_text(
        json.dumps({"chapters": [{"num": i, "title": f"第{i}章"} for i in range(1, 6)]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return tmp_path


def _write_chapter(novel: pathlib.Path, number: int) -> str:
    body = NL.join(f"第{number}章第{i}段：林风握紧镇器碎片，望向天际。" for i in range(4))
    text = f"# 第{number}章{NL}{NL}{body}"
    (novel / "chapters" / f"chapter_{number:04d}.txt").write_text(text, encoding="utf-8")
    return text


class _Session:
    """一次"运行期"：持有 MemoryManager，on close 时丢弃引用（模拟关窗）。"""

    def __init__(self, novel: pathlib.Path):
        self.novel = novel
        self.memory = MemoryManager(novel)

    def write_chapters(self, numbers):
        for n in numbers:
            _write_chapter(self.novel, n)
            self.memory.save_chapter_summary(n, f"第{n}章：林风获得镇器碎片，前往黑风岭。")
        return self

    def close(self):
        """模拟**正常关窗**：生产里由 atexit 触发 。

        索引与评分是批量落盘的（索引每 50 次写、评分按阈值），
        不 flush 就丢是**已知权衡**，不是 bug —— 但正常退出必须落全。
        """
        self.memory.flush()
        return self


# ====================================================================== 用例


class TestDataSurvivesRestart:
    def test_chapter_summaries_survive(self, novel):
        _Session(novel).write_chapters([1, 2, 3])

        # —— 重启：全新实例，只可能从磁盘读 ——
        memory = MemoryManager(novel)
        for n in (1, 2, 3):
            assert memory.get_chapter_summary(n) == f"第{n}章：林风获得镇器碎片，前往黑风岭。"

    def test_summary_files_on_disk_match(self, novel):
        _Session(novel).write_chapters([1, 2])
        assert (novel / "memory" / "chapters" / "chapter_00001.txt").exists()
        assert (novel / "summaries" / "chapter_00001_summary.txt").exists()
        assert "第1章摘要" in (novel / "summaries" / "chapter_00001_summary.txt").read_text(encoding="utf-8")

    def test_inverted_index_survives(self, novel):
        """RAG 用的倒排索引（inverted_index.json）跨重启仍可召回旧章节。

        ⚠️ 注意本仓有**两套索引**，用途不同、写入时机也不同：
        -  ——  维护，
          （真正的 RAG 入口）在读，生产里每章生成都会写；
        -  —— 只有  显式调  才写，
           在读（该接口目前只有测试在用）。
        这里验证前者，因为它才是用户可感知的那条链路。
        """
        _Session(novel).write_chapters([1, 2, 3]).close()

        memory = MemoryManager(novel)
        hits = memory.retrieve_relevant("镇器", top_k=5)
        assert hits, "重启后 RAG 召回为空：倒排索引没有落盘"
        assert any("chapter" in str(h).lower() or isinstance(h, dict) for h in hits)

    def test_keyword_index_available_after_agent_path(self, novel):
        """依赖 novel_agent 显式写入的 index.json。

        这条用例走的是生产里的真实顺序（save_chapter_summary → update_index），
        用来钉住重启后按关键词查历史章节仍然可用。
        """
        session = _Session(novel)
        session.write_chapters([1, 2])
        session.memory.update_index(1, ["镇器", "黑风岭"])
        session.memory.update_index(2, ["镇器"])
        session.close()

        memory = MemoryManager(novel)
        assert memory.search_by_keyword("镇器") == [1, 2]
        assert memory.search_by_keyword("不存在") == []

    def test_scores_survive(self, novel):
        _Session(novel).write_chapters([1]).close()
        memory = MemoryManager(novel)
        # 评分由 save_chapter_summary 间接写入，flush 后应完整落盘
        assert memory._scores, "重启后记忆评分为空"

    def test_global_summary_survives(self, novel):
        session = _Session(novel)
        session.memory.save_global_summary("全书梗概：少年持碎片上山。")

        assert MemoryManager(novel).get_global_summary() == "全书梗概：少年持碎片上山。"

    def test_volume_summary_survives(self, novel):
        session = _Session(novel)
        session.memory.save_volume_summary(1, "第一卷：初入江湖。")

        assert MemoryManager(novel).get_volume_summary(1) == "第一卷：初入江湖。"


class TestContinueAfterRestart:
    def test_next_chapter_number_is_not_reused(self, novel):
        """重启后继续写，不得覆盖已有章节、也不得重号。"""
        _Session(novel).write_chapters([1, 2, 3])

        session_b = _Session(novel)
        existing = sorted(p.name for p in (novel / "chapters").glob("chapter_*.txt"))
        assert existing == ["chapter_0001.txt", "chapter_0002.txt", "chapter_0003.txt"]

        session_b.write_chapters([4])
        after = sorted(p.name for p in (novel / "chapters").glob("chapter_*.txt"))
        assert after[-1] == "chapter_0004.txt"
        assert len(after) == 4
        # 前 3 章内容未被覆盖
        assert "第1章" in (novel / "chapters" / "chapter_0001.txt").read_text(encoding="utf-8")

    def test_outline_still_readable(self, novel):
        _Session(novel).write_chapters([1])
        outline = json.loads((novel / "outline.json").read_text(encoding="utf-8"))
        assert len(outline["chapters"]) == 5


class _Host(PersistenceMixin):
    """检查点宿主：只提供 Mixin 需要的三个属性。"""

    def __init__(self, novel_dir):
        self.current_novel_dir = novel_dir
        self.outline = [{"t": 1}]
        self.logs: list[str] = []

    def _log(self, message):
        self.logs.append(message)


class TestCheckpointAcrossRestart:
    def test_unfinished_generation_is_detected(self, novel):
        """上次生成到一半被关掉 —— 重启后必须能提示"有未完成任务"。"""
        host_a = _Host(novel)
        host_a._save_checkpoint(7, "generating")

        # 重启：新宿主读同一个目录
        host_b = _Host(novel)
        host_b._check_recovery()

        assert any("未完成的生成任务" in m and "7" in m for m in host_b.logs)

    def test_finished_generation_clears_checkpoint(self, novel):
        host_a = _Host(novel)
        host_a._save_checkpoint(7, "generating")
        host_a._save_checkpoint(7, "completed")

        host_b = _Host(novel)
        host_b._check_recovery()

        assert not (novel / "checkpoint.json").exists()

    def test_corrupt_checkpoint_does_not_block_startup(self, novel):
        """检查点损坏只应丢"断电恢复能力"，不能阻止启动。"""
        (novel / "checkpoint.json").write_text("{broken", encoding="utf-8")
        host = _Host(novel)
        host._check_recovery()  # 不抛即通过
        assert any("不可读" in m for m in host.logs)


class TestCorruptionTolerance:
    def test_corrupt_inverted_index_does_not_crash(self, novel):
        _Session(novel).write_chapters([1, 2])
        (novel / "memory" / "inverted_index.json").write_text("{broken", encoding="utf-8")

        memory = MemoryManager(novel)  # 不抛
        assert memory.search_by_keyword("镇器") == [] or isinstance(memory.search_by_keyword("镇器"), list)

    def test_corrupt_index_is_not_overwritten_by_empty(self, novel):
        """M5 语义：索引损坏后，禁止用空索引覆盖原文件（否则数据永久丢失）。"""
        _Session(novel).write_chapters([1, 2])
        index_file = novel / "memory" / "inverted_index.json"
        index_file.write_text("{broken", encoding="utf-8")
        before = index_file.read_text(encoding="utf-8")

        memory = MemoryManager(novel)
        memory.save_chapter_summary(3, "第3章：继续赶路。")

        after = index_file.read_text(encoding="utf-8")
        assert after == before or "镇器" in after, "损坏的索引被空内容覆盖了，历史检索数据丢失"

    def test_missing_memory_dir_is_recreated(self, tmp_path):
        """用户手工删了 memory/ —— 重启应自愈，而不是崩。"""
        (tmp_path / "meta.json").write_text("{}", encoding="utf-8")
        memory = MemoryManager(tmp_path)
        assert (tmp_path / "memory").is_dir()
        assert memory.get_chapter_summary(1) == ""


class TestConfigAcrossRestart:
    def test_api_settings_persist(self, tmp_path, monkeypatch):
        """配置写盘后，新实例（= 重启）必须读得回来。"""
        monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))

        config_a = AppConfig()
        config_a.set("api_provider", "deepseek")
        config_a.set("model", "deepseek-chat")
        config_a.save()

        config_b = AppConfig()
        assert config_b.get("api_provider") == "deepseek"
        assert config_b.get("model") == "deepseek-chat"

    def test_profile_switch_persists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))

        config = AppConfig()
        config.create_profile("备用", activate=True)
        config.save()

        assert AppConfig().active_profile == "备用"  # 是 property，不是方法

    def test_corrupt_config_falls_back_to_defaults(self, tmp_path, monkeypatch):
        """配置文件被写坏时，启动应回落默认值而不是崩。"""
        monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
        cfg_dir = tmp_path / ".ai_novel_writer"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.json").write_text("{broken json", encoding="utf-8")

        config = AppConfig()  # 不抛
        assert config.get("api_provider")  # 有默认值
