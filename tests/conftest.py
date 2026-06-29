"""
Pytest配置文件 - 共享fixtures和测试工具
"""

import sys
import tempfile
import shutil
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """创建临时目录，测试后自动清理"""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def mock_ai_client():
    """模拟AI客户端"""
    client = MagicMock()
    client.chat.return_value = "这是模拟的AI回复"
    client.is_configured.return_value = True
    return client


@pytest.fixture
def sample_novel_data():
    """示例小说数据"""
    return {
        "title": "测试小说",
        "genre": "科幻",
        "concept": "一个关于AI的故事",
        "protagonist": "张三",
        "total_chapters": 10,
        "word_count_per_chapter": 3000
    }


@pytest.fixture
def sample_chapter():
    """示例章节数据"""
    return {
        "chapter_num": 1,
        "title": "第一章：觉醒",
        "content": "张三睁开眼睛，发现自己躺在一个陌生的房间里。" * 10,
        "summary": "张三在一个陌生房间醒来"
    }


@pytest.fixture
def sample_characters():
    """示例角色数据"""
    return {
        "张三": {
            "name": "张三",
            "role": "主角",
            "age": 25,
            "personality": "勇敢、聪明",
            "background": "普通大学生"
        },
        "李四": {
            "name": "李四",
            "role": "配角",
            "age": 30,
            "personality": "稳重、可靠",
            "background": "资深研究员"
        }
    }


@pytest.fixture
def sample_world_settings():
    """示例世界观设定"""
    return """
    故事背景：2045年，人工智能已经深度融入人类社会。
    主要地点：新北京科技城
    技术水平：量子计算普及，AGI初步实现
    社会结构：人机共存社会
    """


# 测试标记
def pytest_configure(config):
    """注册自定义标记"""
    config.addinivalue_line("markers", "slow: 标记为慢速测试")
    config.addinivalue_line("markers", "integration: 集成测试")
    config.addinivalue_line("markers", "unit: 单元测试")


# 测试收集钩子
def pytest_collection_modifyitems(config, items):
    """根据标记自动跳过测试"""
    import platform
    
    # 在Windows上跳过某些Linux特定测试
    if platform.system() == "Windows":
        skip_windows = pytest.mark.skip(reason="Windows上不支持此测试")
        for item in items:
            if "linux_only" in item.keywords:
                item.add_marker(skip_windows)
