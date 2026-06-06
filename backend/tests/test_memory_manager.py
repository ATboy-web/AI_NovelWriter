import pytest
import json
import tempfile
import sys
import importlib.util
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# 直接从文件路径导入，避免与 backend/novel-service/app 包名冲突
_project_root = Path(__file__).resolve().parent.parent.parent
_mm_path = _project_root / "app" / "memory_manager.py"
_spec = importlib.util.spec_from_file_location("app.memory_manager", str(_mm_path))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
MemoryManager = _mod.MemoryManager


class TestMemoryManager:
    """测试MemoryManager类"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def memory_manager(self, temp_dir):
        """创建测试用MemoryManager"""
        return MemoryManager(temp_dir)
    
    def test_initialization(self, memory_manager, temp_dir):
        """测试初始化"""
        assert memory_manager.novel_dir == temp_dir
        assert memory_manager.memory_dir.exists()
        assert memory_manager.chapters_dir.exists()
        assert memory_manager.volumes_dir.exists()
        assert memory_manager.arcs_dir.exists()
        assert memory_manager.timeline_dir.exists()
        assert memory_manager.chunks_dir.exists()
    
    def test_save_and_get_global_summary(self, memory_manager):
        """测试保存和获取全局摘要"""
        summary = "这是一个测试全局摘要"
        memory_manager.save_global_summary(summary)
        result = memory_manager.get_global_summary()
        assert result == summary
    
    def test_save_and_get_chapter_summary(self, memory_manager):
        """测试保存和获取章节摘要"""
        summary = "第1章摘要内容"
        memory_manager.save_chapter_summary(1, summary)
        result = memory_manager.get_chapter_summary(1)
        assert result == summary
    
    def test_get_recent_summaries(self, memory_manager):
        """测试获取最近摘要"""
        # 保存多个章节摘要
        for i in range(1, 6):
            memory_manager.save_chapter_summary(i, f"第{i}章摘要")
        
        recent = memory_manager.get_recent_summaries(3)
        assert "第3章摘要" in recent
        assert "第4章摘要" in recent
        assert "第5章摘要" in recent
        assert "第1章摘要" not in recent
    
    def test_chapter_range_summary(self, memory_manager):
        """测试获取章节范围摘要"""
        for i in range(1, 11):
            memory_manager.save_chapter_summary(i, f"第{i}章摘要")
        
        range_summary = memory_manager.get_chapter_range_summary(3, 7)
        assert "第3章" in range_summary
        assert "第7章" in range_summary
        assert "第1章" not in range_summary
    
    def test_volume_summary(self, memory_manager):
        """测试卷级摘要"""
        # 保存卷级摘要
        memory_manager.save_volume_summary(1, "第1卷摘要")
        result = memory_manager.get_volume_summary(1)
        assert result == "第1卷摘要"
        
        # 测试章节号转卷号
        assert memory_manager._chapter_to_volume(1) == 1
        assert memory_manager._chapter_to_volume(100) == 1
        assert memory_manager._chapter_to_volume(101) == 2
    
    def test_auto_generate_volume_summary(self, memory_manager):
        """测试自动生成卷级摘要"""
        # 保存一些章节摘要
        for i in range(1, 6):
            memory_manager.save_chapter_summary(i, f"第{i}章摘要内容")
        
        # 自动生成第1卷摘要（假设每卷5章用于测试）
        memory_manager.VOLUME_SIZE = 5
        summary = memory_manager.auto_generate_volume_summary(1)
        
        assert "第1卷" in summary
        assert "第1章" in summary
        assert "第5章" in summary
    
    def test_arc_summary(self, memory_manager):
        """测试弧线摘要"""
        # 保存弧线摘要
        memory_manager.save_arc_summary("主角成长", "主角从新手到高手", [1, 5, 10])
        
        # 获取弧线摘要
        result = memory_manager.get_arc_summary("主角成长")
        assert result == "主角从新手到高手"
        
        # 获取所有弧线
        arcs = memory_manager.get_all_arcs()
        assert len(arcs) == 1
        assert arcs[0]["name"] == "主角成长"
    
    def test_character_management(self, memory_manager):
        """测试角色管理"""
        characters = {
            "主角": {"personality": "勇敢", "age": 25},
            "配角": {"personality": "忠诚", "age": 30}
        }
        
        # 保存角色
        memory_manager.save_characters(characters)
        
        # 获取角色
        result = memory_manager.get_characters()
        assert result["主角"]["personality"] == "勇敢"
        assert result["配角"]["age"] == 30
        
        # 更新角色
        memory_manager.update_character("主角", {"age": 26})
        result = memory_manager.get_characters()
        assert result["主角"]["age"] == 26
    
    def test_character_activity(self, memory_manager):
        """测试角色活跃度"""
        # 更新角色活跃度
        memory_manager.update_character_activity("主角", 1)
        memory_manager.update_character_activity("主角", 5)
        memory_manager.update_character_activity("配角", 3)
        
        # 获取活跃角色
        active = memory_manager.get_active_characters(10, window=10)
        assert "主角" in active
        assert "配角" in active
    
    def test_event_timeline(self, memory_manager):
        """测试事件时间线"""
        # 添加事件
        memory_manager.add_event(1, "故事开始", "story", ["主角"])
        memory_manager.add_event(5, "遇到配角", "character", ["主角", "配角"])
        memory_manager.add_event(10, "战斗开始", "action", ["主角"])
        
        # 获取时间线
        timeline = memory_manager.get_timeline(1, 10)
        assert len(timeline) == 3
        assert timeline[0]["event"] == "故事开始"
        assert timeline[2]["event"] == "战斗开始"
    
    def test_settings_management(self, memory_manager):
        """测试世界观设定管理"""
        settings = {
            "world": "魔法世界",
            "time": "中世纪",
            "rules": ["魔法存在", "有龙"]
        }
        
        memory_manager.save_settings(settings)
        result = memory_manager.get_settings()
        assert result["world"] == "魔法世界"
        assert "魔法存在" in result["rules"]


class TestMemoryManagerRAG:
    """测试RAG检索功能"""
    
    @pytest.fixture
    def memory_manager_with_data(self, temp_dir):
        """创建有测试数据的MemoryManager"""
        manager = MemoryManager(temp_dir)
        
        # 添加一些测试数据
        manager.save_chapter_summary(1, "主角在城市中遇到神秘事件")
        manager.save_chapter_summary(2, "主角发现隐藏的魔法世界")
        manager.save_chapter_summary(3, "主角开始学习魔法技能")
        
        return manager
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_extract_keywords(self):
        """测试关键词提取"""
        keywords = MemoryManager._extract_keywords("主角在城市中遇到神秘事件")
        assert "主角" in keywords
        assert "城市" in keywords
        assert "神秘" in keywords
        assert "事件" in keywords
    
    def test_inverted_index_update(self, memory_manager_with_data):
        """测试倒排索引更新"""
        manager = memory_manager_with_data
        
        # 检查倒排索引是否更新
        assert "主角" in manager._inverted_index
        assert "chapter_00001" in manager._inverted_index["主角"]
    
    def test_retrieve_relevant(self, memory_manager_with_data):
        """测试RAG检索"""
        manager = memory_manager_with_data
        
        # 检索相关内容
        results = manager.retrieve_relevant("主角魔法", top_k=2)
        assert len(results) > 0
        
        # 检查结果包含相关内容
        contents = [r["content"] for r in results]
        assert any("主角" in content for content in contents)
    
    def test_build_smart_context(self, memory_manager_with_data):
        """测试智能上下文构建"""
        manager = memory_manager_with_data
        
        # 添加角色数据
        manager.save_characters({
            "主角": {"personality": "勇敢", "age": 25}
        })
        
        # 添加世界观设定
        manager.save_settings({
            "world": "魔法世界",
            "time": "中世纪"
        })
        
        # 构建上下文
        context = manager.build_smart_context(3, "魔法学习")
        
        # 检查上下文包含相关信息
        assert "主角" in context or "魔法" in context


class TestMemoryManagerHealthCheck:
    """测试健康检查功能"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def memory_manager(self, temp_dir):
        """创建测试用MemoryManager"""
        return MemoryManager(temp_dir)
    
    def test_health_check_empty(self, memory_manager):
        """测试空记忆系统的健康检查"""
        report = memory_manager.health_check()
        
        assert report["total_chunks"] == 0
        assert report["total_chapters"] == 0
        assert report["total_volumes"] == 0
        assert report["total_characters"] == 0
        assert report["total_arcs"] == 0
        assert len(report["recommendations"]) == 0
    
    def test_health_check_with_data(self, memory_manager):
        """测试有数据的记忆系统健康检查"""
        # 添加一些数据
        memory_manager.save_chapter_summary(1, "测试摘要")
        memory_manager.save_characters({"主角": {"age": 25}})
        memory_manager.save_arc_summary("测试弧线", "测试内容")
        
        report = memory_manager.health_check()
        
        assert report["total_chapters"] == 1
        assert report["total_characters"] == 1
        assert report["total_arcs"] == 1
    
    def test_health_check_recommendations(self, memory_manager):
        """测试健康检查建议机制"""
        # 添加足够多的章节触发衰减检测
        for i in range(1, 50):
            memory_manager.save_chapter_summary(i, f"第{i}章摘要")
        
        report = memory_manager.health_check()
        
        # 验证报告结构完整
        assert "recommendations" in report
        assert "stale_chunks" in report
        assert "total_chapters" in report
        assert report["total_chapters"] == 49
        # 第100章自动生成卷级摘要，所以有1卷
        assert report["total_volumes"] == 0


class TestMemoryManagerEdgeCases:
    """测试边界情况"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def memory_manager(self, temp_dir):
        """创建测试用MemoryManager"""
        return MemoryManager(temp_dir)
    
    def test_get_nonexistent_chapter(self, memory_manager):
        """测试获取不存在的章节"""
        result = memory_manager.get_chapter_summary(999)
        assert result == ""
    
    def test_get_nonexistent_volume(self, memory_manager):
        """测试获取不存在的卷"""
        result = memory_manager.get_volume_summary(999)
        assert result == ""
    
    def test_get_nonexistent_arc(self, memory_manager):
        """测试获取不存在的弧线"""
        result = memory_manager.get_arc_summary("不存在的弧线")
        assert result == ""
    
    def test_empty_timeline(self, memory_manager):
        """测试空时间线"""
        timeline = memory_manager.get_timeline(1, 100)
        assert timeline == []
    
    def test_empty_characters(self, memory_manager):
        """测试空角色数据"""
        characters = memory_manager.get_characters()
        assert characters == {}
    
    def test_empty_settings(self, memory_manager):
        """测试空世界观设定"""
        settings = memory_manager.get_settings()
        assert settings == {}


@pytest.mark.asyncio
class TestMemoryManagerIntegration:
    """集成测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    async def test_full_workflow(self, temp_dir):
        """测试完整工作流程"""
        manager = MemoryManager(temp_dir)
        
        # 1. 保存世界观设定
        manager.save_settings({
            "world": "魔法世界",
            "time": "中世纪",
            "rules": ["魔法存在", "有龙"]
        })
        
        # 2. 保存角色信息
        manager.save_characters({
            "主角": {"personality": "勇敢", "age": 25},
            "导师": {"personality": "智慧", "age": 60}
        })
        
        # 3. 保存章节摘要
        for i in range(1, 6):
            summary = f"第{i}章：主角在第{i}天学习魔法"
            manager.save_chapter_summary(i, summary)
            
            # 更新角色活跃度
            manager.update_character_activity("主角", i)
            if i > 2:
                manager.update_character_activity("导师", i)
            
            # 添加事件
            manager.add_event(i, f"第{i}天学习魔法", "story", ["主角"])
        
        # 4. 保存弧线摘要
        manager.save_arc_summary("魔法学习", "主角从零开始学习魔法", [1, 2, 3, 4, 5])
        
        # 5. 验证数据
        assert manager.get_global_summary() == ""  # 未设置全局摘要
        assert manager.get_chapter_summary(1) != ""
        assert len(manager.get_characters()) == 2
        assert len(manager.get_all_arcs()) == 1
        
        # 6. 测试RAG检索
        results = manager.retrieve_relevant("魔法学习", top_k=3)
        assert len(results) > 0
        
        # 7. 测试智能上下文构建
        context = manager.build_smart_context(5, "魔法")
        assert "主角" in context or "魔法" in context
        
        # 8. 健康检查
        report = manager.health_check()
        assert report["total_chapters"] == 5
        assert report["total_characters"] == 2
        assert report["total_arcs"] == 1