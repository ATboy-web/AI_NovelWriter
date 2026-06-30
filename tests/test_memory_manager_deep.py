"""
memory_manager.py 深度测试 - 真正调用方法
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.memory_manager import MemoryManager


class TestMemoryManagerDeep:
    """MemoryManager 深度测试"""

    def test_init(self, tmp_path):
        mm = MemoryManager(tmp_path)
        assert mm is not None

    def test_chapter_to_volume(self, tmp_path):
        mm = MemoryManager(tmp_path)
        assert mm._chapter_to_volume(1) == 1
        assert mm._chapter_to_volume(100) == 1
        assert mm._chapter_to_volume(101) == 2

    def test_save_and_get_volume_summary(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.save_volume_summary(1, "第1卷摘要")
        assert mm.get_volume_summary(1) == "第1卷摘要"

    def test_get_nonexistent_volume_summary(self, tmp_path):
        mm = MemoryManager(tmp_path)
        assert mm.get_volume_summary(999) == ""

    def test_save_and_get_arc_summary(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.save_arc_summary("修炼弧", "修炼内容", [1, 2, 3])
        assert mm.get_arc_summary("修炼弧") == "修炼内容"

    def test_save_and_get_chapter_summary(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.save_chapter_summary(1, "第1章摘要")
        assert mm.get_chapter_summary(1) == "第1章摘要"

    def test_save_and_get_global_summary(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.save_global_summary("全局摘要")
        assert mm.get_global_summary() == "全局摘要"

    def test_update_character_activity(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.update_character_activity("张三", 1)
        mm.update_character_activity("张三", 5)
        assert mm._character_activity["张三"]["last_seen"] == 5

    def test_get_active_characters(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.update_character_activity("张三", 1)
        mm.update_character_activity("李四", 50)
        active = mm.get_active_characters(10, window=50)
        assert isinstance(active, list)

    def test_health_check(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.save_chapter_summary(1, "第1章摘要")
        mm.save_global_summary("全局摘要")
        report = mm.health_check()
        assert "total_chapters" in report
        assert "recommendations" in report

    def test_retrieve_relevant_empty(self, tmp_path):
        mm = MemoryManager(tmp_path)
        result = mm.retrieve_relevant("", top_k=5)
        assert result == []

    def test_retrieve_relevant_with_content(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.save_chapter_summary(1, "张三修炼武功")
        mm.save_chapter_summary(2, "李四学习法术")
        result = mm.retrieve_relevant("修炼", top_k=5)
        assert isinstance(result, list)

    def test_save_multiple_volumes(self, tmp_path):
        mm = MemoryManager(tmp_path)
        for i in range(1, 11):
            mm.save_volume_summary(i, f"第{i}卷摘要")
        for i in range(1, 11):
            assert mm.get_volume_summary(i) == f"第{i}卷摘要"

    def test_save_multiple_chapters(self, tmp_path):
        mm = MemoryManager(tmp_path)
        for i in range(1, 21):
            mm.save_chapter_summary(i, f"第{i}章摘要")
        for i in range(1, 21):
            assert mm.get_chapter_summary(i) == f"第{i}章摘要"

    def test_unicode_content(self, tmp_path):
        mm = MemoryManager(tmp_path)
        summary = "主角使用了🔥火焰技能，造成1000点伤害！"
        mm.save_chapter_summary(1, summary)
        assert mm.get_chapter_summary(1) == summary

    def test_special_characters(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.save_arc_summary("修炼-主线", "内容", [1, 2])
        assert mm.get_arc_summary("修炼-主线") == "内容"

    def test_long_summary(self, tmp_path):
        mm = MemoryManager(tmp_path)
        long_summary = "x" * 10000
        mm.save_chapter_summary(1, long_summary)
        assert mm.get_chapter_summary(1) == long_summary

    def test_chapter_5000(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.save_chapter_summary(5000, "第5000章摘要")
        assert mm.get_chapter_summary(5000) == "第5000章摘要"

    def test_volume_50(self, tmp_path):
        mm = MemoryManager(tmp_path)
        mm.save_volume_summary(50, "最终卷摘要")
        assert mm.get_volume_summary(50) == "最终卷摘要"

    def test_multiple_characters(self, tmp_path):
        mm = MemoryManager(tmp_path)
        characters = ["张三", "李四", "王五", "赵六"]
        for i, char in enumerate(characters):
            mm.update_character_activity(char, i * 10)
        for char in characters:
            assert char in mm._character_activity
