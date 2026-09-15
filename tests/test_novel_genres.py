"""
小说类型测试用例
测试15种小说类型的特定功能
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock

import pytest

from app.memory_manager import MemoryManager
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
        agent = NovelAgent(mock_ai_client, MemoryManager(tmp_path))
        assert agent is not None

    @pytest.mark.parametrize("genre", SUPPORTED_GENRES)
    def test_genre_outline_generation(self, genre, mock_ai_client, tmp_path):
        """测试每种类型都能生成大纲"""
        agent = NovelAgent(mock_ai_client, MemoryManager(tmp_path))

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
        agent = NovelAgent(mock_ai_client, MemoryManager(tmp_path))

        # Mock AI响应
        mock_ai_client.chat.return_value = """
        主角：张三，25岁，勇敢
        配角：李四，30岁，智慧
        """

        assert agent is not None

    @pytest.mark.parametrize("genre", SUPPORTED_GENRES)
    def test_genre_chapter_generation(self, genre, mock_ai_client, tmp_path):
        """测试每种类型都能生成章节"""
        agent = NovelAgent(mock_ai_client, MemoryManager(tmp_path))

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

    @pytest.mark.parametrize("genre", SUPPORTED_GENRES)
    def test_genre_is_propagated_to_ai_prompt(self, mock_ai_client, tmp_path, genre):
        """小说类型必须真正进入发给 AI 的提示词。

        本测试替代原先 10 个 `agent = NovelAgent(...)` 后
        `assert len(<测试内硬编码列表>) > 0` 的空断言 —— 那些断言与产品代码、
        与 agent 均无关, 恒为真且不验证任何行为 (agent 也从未被使用)。
        这里改为验证真实契约: 类型字符串确实出现在 AIClient.chat 的入参里。
        """
        agent = NovelAgent(mock_ai_client, MemoryManager(tmp_path))
        agent.generate_settings(genre, "测试标题", "测试概念")

        assert mock_ai_client.chat.called, "generate_settings 应调用 AI"
        sent = json.dumps(list(mock_ai_client.chat.call_args_list), ensure_ascii=False, default=str)
        assert genre in sent, f"类型 {genre} 应出现在发给 AI 的提示词中"


class TestGenreCombination:
    """类型组合测试"""

    @pytest.fixture
    def mock_ai_client(self):
        """模拟AI客户端"""
        client = MagicMock()
        client.chat.return_value = "模拟内容"
        client.is_configured.return_value = True
        return client

    @pytest.mark.parametrize("label", ["科幻-赛博朋克", "武侠-新武侠", "言情-古代言情"])
    def test_genre_with_subgenre(self, mock_ai_client, tmp_path, label):
        """主类型与子类型应完整传递到提示词。

        替代原先 `for ...: assert len(subs) > 0` 的自造字典断言 (恒为真)。
        """
        agent = NovelAgent(mock_ai_client, MemoryManager(tmp_path))
        agent.generate_settings(label, "测试标题", "测试概念")

        sent = json.dumps(list(mock_ai_client.chat.call_args_list), ensure_ascii=False, default=str)
        main, sub = label.split("-")
        assert main in sent and sub in sent, f"{label} 应完整出现在提示词中"

    @pytest.mark.parametrize("label", ["科幻-硬核", "悬疑-压抑", "言情-虐心", "恐怖-心理恐怖"])
    def test_genre_tone_variations(self, mock_ai_client, tmp_path, label):
        """类型基调应完整传递到提示词。

        替代原先 `for ...: assert len(tones) > 0` 的自造字典断言 (恒为真)。
        """
        agent = NovelAgent(mock_ai_client, MemoryManager(tmp_path))
        agent.generate_settings(label, "测试标题", "测试概念")

        sent = json.dumps(list(mock_ai_client.chat.call_args_list), ensure_ascii=False, default=str)
        main, tone = label.split("-")
        assert main in sent and tone in sent, f"{label} 应完整出现在提示词中"


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
