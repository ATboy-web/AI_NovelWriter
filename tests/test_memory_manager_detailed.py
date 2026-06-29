"""
记忆管理器详细测试 - 覆盖更多功能
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
# MemoryManager 详细测试
# ============================================================

class TestMemoryManagerDetailed:
    """MemoryManager详细测试"""
    
    def test_import(self):
        """测试导入"""
        from app.memory_manager import MemoryManager
        assert MemoryManager is not None
    
    def test_class_exists(self):
        """测试类存在"""
        from app.memory_manager import MemoryManager
        assert hasattr(MemoryManager, '__init__')
    
    def test_has_volume_methods(self):
        """测试卷级摘要方法"""
        from app.memory_manager import MemoryManager
        assert hasattr(MemoryManager, 'save_volume_summary')
        assert hasattr(MemoryManager, 'get_volume_summary')
    
    def test_has_arc_methods(self):
        """测试弧线摘要方法"""
        from app.memory_manager import MemoryManager
        assert hasattr(MemoryManager, 'save_arc_summary')
        assert hasattr(MemoryManager, 'get_arc_summary')
    
    def test_has_chapter_methods(self):
        """测试章节摘要方法"""
        from app.memory_manager import MemoryManager
        assert hasattr(MemoryManager, 'save_chapter_summary')
        assert hasattr(MemoryManager, 'get_chapter_summary')
    
    def test_has_global_methods(self):
        """测试全局摘要方法"""
        from app.memory_manager import MemoryManager
        assert hasattr(MemoryManager, 'save_global_summary')
        assert hasattr(MemoryManager, 'get_global_summary')
    
    def test_has_character_methods(self):
        """测试角色方法"""
        from app.memory_manager import MemoryManager
        assert hasattr(MemoryManager, 'update_character_activity')
        assert hasattr(MemoryManager, 'get_active_characters')
    
    def test_has_retrieval_methods(self):
        """测试检索方法"""
        from app.memory_manager import MemoryManager
        assert hasattr(MemoryManager, 'retrieve_relevant')
    
    def test_has_health_check(self):
        """测试健康检查"""
        from app.memory_manager import MemoryManager
        assert hasattr(MemoryManager, 'health_check')
    
    def test_init_with_temp_dir(self, tmp_path):
        """测试临时目录初始化"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        assert mm is not None
    
    def test_chapter_to_volume(self, tmp_path):
        """测试章节号转卷号"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        assert mm._chapter_to_volume(1) == 1
        assert mm._chapter_to_volume(100) == 1
        assert mm._chapter_to_volume(101) == 2
    
    def test_save_and_get_volume_summary(self, tmp_path):
        """测试保存和获取卷级摘要"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        mm.save_volume_summary(1, "第1卷摘要")
        result = mm.get_volume_summary(1)
        assert result == "第1卷摘要"
    
    def test_get_nonexistent_volume_summary(self, tmp_path):
        """测试获取不存在的卷级摘要"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        result = mm.get_volume_summary(999)
        assert result == ""
    
    def test_save_and_get_arc_summary(self, tmp_path):
        """测试保存和获取弧线摘要"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        mm.save_arc_summary("修炼弧", "修炼内容", [1, 2, 3])
        result = mm.get_arc_summary("修炼弧")
        assert result == "修炼内容"
    
    def test_save_and_get_chapter_summary(self, tmp_path):
        """测试保存和获取章节摘要"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        mm.save_chapter_summary(1, "第1章摘要")
        result = mm.get_chapter_summary(1)
        assert result == "第1章摘要"
    
    def test_save_and_get_global_summary(self, tmp_path):
        """测试保存和获取全局摘要"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        mm.save_global_summary("全局摘要")
        result = mm.get_global_summary()
        assert result == "全局摘要"
    
    def test_update_character_activity(self, tmp_path):
        """测试更新角色活跃度"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        mm.update_character_activity("张三", 1)
        mm.update_character_activity("张三", 5)
        
        activity = mm._character_activity
        assert "张三" in activity
        assert activity["张三"]["last_seen"] == 5
    
    def test_get_active_characters(self, tmp_path):
        """测试获取活跃角色"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        mm.update_character_activity("张三", 1)
        mm.update_character_activity("李四", 50)
        
        active = mm.get_active_characters(10, window=50)
        assert isinstance(active, list)
    
    def test_health_check(self, tmp_path):
        """测试健康检查"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        mm.save_chapter_summary(1, "第1章摘要")
        mm.save_global_summary("全局摘要")
        
        report = mm.health_check()
        assert "total_chapters" in report
        assert "recommendations" in report
    
    def test_retrieve_relevant_empty(self, tmp_path):
        """测试空查询检索"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        result = mm.retrieve_relevant("", top_k=5)
        assert result == []


# ============================================================
# MemoryManager 边界条件测试
# ============================================================

class TestMemoryManagerEdgeCases:
    """边界条件测试"""
    
    def test_chapter_5000(self, tmp_path):
        """测试第5000章"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        mm.save_chapter_summary(5000, "第5000章摘要")
        result = mm.get_chapter_summary(5000)
        assert result == "第5000章摘要"
    
    def test_volume_50(self, tmp_path):
        """测试第50卷"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        mm.save_volume_summary(50, "最终卷摘要")
        result = mm.get_volume_summary(50)
        assert result == "最终卷摘要"
    
    def test_special_characters_in_summary(self, tmp_path):
        """测试特殊字符"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        summary = "张三说：\"你好！\" & 李四说：'再见！'"
        mm.save_chapter_summary(1, summary)
        result = mm.get_chapter_summary(1)
        assert result == summary
    
    def test_unicode_summary(self, tmp_path):
        """测试Unicode字符"""
        from app.memory_manager import MemoryManager
        mm = MemoryManager(tmp_path)
        summary = "主角使用了🔥火焰技能，造成1000点伤害！"
        mm.save_chapter_summary(1, summary)
        result = mm.get_chapter_summary(1)
        assert result == summary


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
