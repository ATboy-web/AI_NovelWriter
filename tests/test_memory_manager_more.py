"""
记忆管理器更多测试
"""

import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


# ============================================================
# MemoryManager 更多测试
# ============================================================

class TestMemoryManagerMore:
    """MemoryManager更多测试"""
    
    def test_chapter_to_volume_edge_cases(self, tmp_path):
        """测试章节号转卷号边界情况"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        assert mm._chapter_to_volume(0) == 0
        assert mm._chapter_to_volume(1) == 1
        assert mm._chapter_to_volume(99) == 1
        assert mm._chapter_to_volume(100) == 1
        assert mm._chapter_to_volume(101) == 2
    
    def test_save_multiple_volume_summaries(self, tmp_path):
        """测试保存多个卷级摘要"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        for i in range(1, 11):
            mm.save_volume_summary(i, f"第{i}卷摘要")
        
        for i in range(1, 11):
            assert mm.get_volume_summary(i) == f"第{i}卷摘要"
    
    def test_save_multiple_arc_summaries(self, tmp_path):
        """测试保存多个弧线摘要"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        arcs = ["修炼弧", "感情弧", "冒险弧"]
        for arc in arcs:
            mm.save_arc_summary(arc, f"{arc}内容", [1, 2, 3])
        
        for arc in arcs:
            assert mm.get_arc_summary(arc) == f"{arc}内容"
    
    def test_save_multiple_chapter_summaries(self, tmp_path):
        """测试保存多个章节摘要"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        for i in range(1, 21):
            mm.save_chapter_summary(i, f"第{i}章摘要")
        
        for i in range(1, 21):
            assert mm.get_chapter_summary(i) == f"第{i}章摘要"
    
    def test_update_character_activity_multiple(self, tmp_path):
        """测试更新多个角色活跃度"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        characters = ["张三", "李四", "王五", "赵六"]
        for i, char in enumerate(characters):
            mm.update_character_activity(char, i * 10)
        
        for char in characters:
            assert char in mm._character_activity
    
    def test_retrieve_relevant_with_content(self, tmp_path):
        """测试有内容的检索"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        mm.save_chapter_summary(1, "张三修炼武功")
        mm.save_chapter_summary(2, "李四学习法术")
        
        result = mm.retrieve_relevant("修炼", top_k=5)
        assert isinstance(result, list)
    
    def test_health_check_empty(self, tmp_path):
        """测试空健康检查"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        report = mm.health_check()
        assert "total_chapters" in report
        assert report["total_chapters"] == 0


# ============================================================
# MemoryManager 边界条件更多测试
# ============================================================

class TestMemoryManagerEdgeCasesMore:
    """边界条件更多测试"""
    
    def test_very_long_summary(self, tmp_path):
        """测试非常长的摘要"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        long_summary = "x" * 10000
        mm.save_chapter_summary(1, long_summary)
        result = mm.get_chapter_summary(1)
        assert result == long_summary
    
    def test_special_characters_in_arc_name(self, tmp_path):
        """测试弧线名称中的特殊字符"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        mm.save_arc_summary("修炼-主线", "内容", [1, 2])
        assert mm.get_arc_summary("修炼-主线") == "内容"
    
    def test_unicode_in_character_name(self, tmp_path):
        """测试角色名称中的Unicode字符"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        mm.update_character_activity("张三🔥", 1)
        assert "张三🔥" in mm._character_activity


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
