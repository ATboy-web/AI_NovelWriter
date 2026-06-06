import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

# 将项目根目录加入路径（用于导入 app 包）
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

@pytest.fixture
def mock_ai_client():
    """Mock AI client for testing"""
    client = MagicMock()
    client.chat.return_value = '{"title": "测试标题", "content": "测试内容"}'
    client.is_configured.return_value = True
    return client

@pytest.fixture
def sample_novel_config():
    """Sample novel configuration"""
    return {
        "title": "测试小说",
        "type": "scifi",
        "author": "测试作者"
    }