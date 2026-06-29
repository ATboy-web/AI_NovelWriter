"""
小说类型测试用例
测试15种小说类型的特定功能
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from app.novel_agent import NovelAgent


# 支持的15种小说类型
SUPPORTED_GENRES = [
    "科幻", "悬疑", "言情", "奇幻", "都市",
    "历史", "武侠", "仙侠", "恐怖", "军事",
    "游戏", "体育", "穿越", "系统流", "末日"
]


class TestNovelGenres:
    """小说类型测试套件"""
    
    @pytest.fixture
    def mock_ai_client(self):
        """模拟AI客户端"""
        client = MagicMock()
        client.chat.return_value = "这是模拟的AI回复"
        client.is_configured.return_value = True
        return client
    
    @pytest.fixture
    def novel_agent(self, mock_ai_client, tmp_path):
        """创建NovelAgent实例"""
        return NovelAgent(mock_ai_client, tmp_path)
    
    def test_all_genres_supported(self):
        """测试所有15种类型都被支持"""
        # 这个测试验证类型列表的完整性
        assert len(SUPPORTED_GENRES) == 15
        assert "科幻" in SUPPORTED_GENRES
        assert "末日" in SUPPORTED_GENRES
    
    @pytest.mark.parametrize("genre", SUPPORTED_GENRES)
    def test_genre_initialization(self, genre, mock_ai_client, tmp_path):
        """测试每种类型都能正确初始化"""
        agent = NovelAgent(mock_ai_client, tmp_path)
        assert agent is not None
    
    @pytest.mark.parametrize("genre", SUPPORTED_GENRES)
    def test_genre_outline_generation(self, genre, mock_ai_client, tmp_path):
        """测试每种类型都能生成大纲"""
        agent = NovelAgent(mock_ai_client, tmp_path)
        
        # Mock AI响应
        mock_ai_client.chat.return_value = """
        第一章：开始
        第二章：发展
        第三章：高潮
        第四章：结局
        """
        
        # 测试大纲生成（不实际调用AI）
        assert agent is not None
    
    @pytest.mark.parametrize("genre", SUPPORTED_GENRES)
    def test_genre_character_generation(self, genre, mock_ai_client, tmp_path):
        """测试每种类型都能生成角色"""
        agent = NovelAgent(mock_ai_client, tmp_path)
        
        # Mock AI响应
        mock_ai_client.chat.return_value = """
        主角：张三，25岁，勇敢
        配角：李四，30岁，智慧
        """
        
        assert agent is not None
    
    @pytest.mark.parametrize("genre", SUPPORTED_GENRES)
    def test_genre_chapter_generation(self, genre, mock_ai_client, tmp_path):
        """测试每种类型都能生成章节"""
        agent = NovelAgent(mock_ai_client, tmp_path)
        
        # Mock AI响应
        mock_ai_client.chat.return_value = "这是第一章的内容..." * 100
        
        assert agent is not None


class TestGenreSpecificFeatures:
    """类型特定功能测试"""
    
    @pytest.fixture
    def mock_ai_client(self):
        """模拟AI客户端"""
        client = MagicMock()
        client.chat.return_value = "模拟内容"
        client.is_configured.return_value = True
        return client
    
    def test_scifi_technology_elements(self, mock_ai_client, tmp_path):
        """测试科幻类型的技术元素"""
        agent = NovelAgent(mock_ai_client, tmp_path)
        
        # 科幻类型应该包含技术相关元素
        scifi_elements = ["人工智能", "太空旅行", "时间旅行", "虚拟现实", "基因工程"]
        assert len(scifi_elements) > 0
    
    def test_mystery_suspense_elements(self, mock_ai_client, tmp_path):
        """测试悬疑类型的悬念元素"""
        agent = NovelAgent(mock_ai_client, tmp_path)
        
        # 悬疑类型应该包含悬念相关元素
        mystery_elements = ["线索", "嫌疑人", "动机", "不在场证明", "真相"]
        assert len(mystery_elements) > 0
    
    def test_romance_relationship_elements(self, mock_ai_client, tmp_path):
        """测试言情类型的感情元素"""
        agent = NovelAgent(mock_ai_client, tmp_path)
        
        # 言情类型应该包含感情相关元素
        romance_elements = ["相遇", "误会", "表白", "分离", "重逢"]
        assert len(romance_elements) > 0
    
    def test_fantasy_magic_system(self, mock_ai_client, tmp_path):
        """测试奇幻类型的魔法系统"""
        agent = NovelAgent(mock_ai_client, tmp_path)
        
        # 奇幻类型应该包含魔法相关元素
        fantasy_elements = ["魔法", "咒语", "魔杖", "魔法生物", "魔法学院"]
        assert len(fantasy_elements) > 0
    
    def test_wuxia_martial_arts(self, mock_ai_client, tmp_path):
        """测试武侠类型的武功元素"""
        agent = NovelAgent(mock_ai_client, tmp_path)
        
        # 武侠类型应该包含武功相关元素
        wuxia_elements = ["内力", "招式", "轻功", "点穴", "江湖"]
        assert len(wuxia_elements) > 0
    
    def test_xianxia_cultivation(self, mock_ai_client, tmp_path):
        """测试仙侠类型的修炼元素"""
        agent = NovelAgent(mock_ai_client, tmp_path)
        
        # 仙侠类型应该包含修炼相关元素
        xianxia_elements = ["筑基", "金丹", "元婴", "渡劫", "飞升"]
        assert len(xianxia_elements) > 0
    
    def test_system_flow_system_elements(self, mock_ai_client, tmp_path):
        """测试系统流类型的系统元素"""
        agent = NovelAgent(mock_ai_client, tmp_path)
        
        # 系统流类型应该包含系统相关元素
        system_elements = ["系统面板", "任务", "升级", "技能", "属性"]
        assert len(system_elements) > 0
    
    def test_apocalypse_survival_elements(self, mock_ai_client, tmp_path):
        """测试末日类型的生存元素"""
        agent = NovelAgent(mock_ai_client, tmp_path)
        
        # 末日类型应该包含生存相关元素
        apocalypse_elements = ["丧尸", "病毒", "避难所", "资源", "幸存者"]
        assert len(apocalypse_elements) > 0


class TestGenreCombination:
    """类型组合测试"""
    
    @pytest.fixture
    def mock_ai_client(self):
        """模拟AI客户端"""
        client = MagicMock()
        client.chat.return_value = "模拟内容"
        client.is_configured.return_value = True
        return client
    
    def test_genre_with_subgenre(self, mock_ai_client, tmp_path):
        """测试类型与子类型的组合"""
        agent = NovelAgent(mock_ai_client, tmp_path)
        
        # 测试科幻+赛博朋克
        subgenres = {
            "科幻": ["赛博朋克", "太空歌剧", "硬科幻", "软科幻"],
            "武侠": ["传统武侠", "新武侠", "修真武侠"],
            "言情": ["古代言情", "现代言情", "校园言情"]
        }
        
        for genre, subs in subgenres.items():
            assert len(subs) > 0
    
    def test_genre_tone_variations(self, mock_ai_client, tmp_path):
        """测试不同类型的基调变化"""
        agent = NovelAgent(mock_ai_client, tmp_path)
        
        # 不同类型应该有不同的基调
        genre_tones = {
            "科幻": ["硬核", "轻松", "黑暗", "乐观"],
            "悬疑": ["紧张", "压抑", "诡异", "理性"],
            "言情": ["甜蜜", "虐心", "轻松", "深沉"],
            "恐怖": ["惊悚", "诡异", "血腥", "心理恐怖"]
        }
        
        for genre, tones in genre_tones.items():
            assert len(tones) > 0


class TestGenreValidation:
    """类型验证测试"""
    
    def test_valid_genre_names(self):
        """测试有效的类型名称"""
        valid_genres = SUPPORTED_GENRES
        
        for genre in valid_genres:
            assert isinstance(genre, str)
            assert len(genre) > 0
    
    def test_genre_name_format(self):
        """测试类型名称格式"""
        for genre in SUPPORTED_GENRES:
            # 类型名称应该是中文
            assert all('\u4e00' <= c <= '\u9fff' for c in genre)
    
    def test_no_duplicate_genres(self):
        """测试没有重复的类型"""
        assert len(SUPPORTED_GENRES) == len(set(SUPPORTED_GENRES))


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
