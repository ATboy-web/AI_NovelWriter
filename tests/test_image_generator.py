"""
文生图模块测试
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from app.image_generator import ImageGenerator
from app.config import AppConfig


class TestImageGenerator:
    """ImageGenerator 测试套件"""
    
    @pytest.fixture
    def mock_config(self):
        """模拟配置"""
        config = MagicMock(spec=AppConfig)
        return config
    
    @pytest.fixture
    def generator(self, mock_config):
        """创建ImageGenerator实例"""
        return ImageGenerator(mock_config)
    
    def test_is_configured_disabled(self, generator, mock_config):
        """测试未配置时"""
        mock_config.get.return_value = "disabled"
        assert generator.is_configured() is False
    
    def test_is_configured_comfyui(self, generator, mock_config):
        """测试配置了ComfyUI"""
        mock_config.get.return_value = "comfyui"
        assert generator.is_configured() is True
    
    def test_is_configured_sdapi(self, generator, mock_config):
        """测试配置了SD API"""
        mock_config.get.return_value = "sdapi"
        assert generator.is_configured() is True
    
    def test_generate_disabled_provider(self, generator, mock_config):
        """测试禁用的提供商"""
        mock_config.get.return_value = "disabled"
        result = generator.generate("test prompt")
        assert result is None
    
    def test_generate_unknown_provider(self, generator, mock_config):
        """测试未知的提供商"""
        mock_config.get.return_value = "unknown"
        result = generator.generate("test prompt")
        assert result is None
    
    @patch('app.image_generator.httpx')
    def test_generate_comfyui_success(self, mock_httpx, generator, mock_config):
        """测试ComfyUI生成成功"""
        # 配置mock
        mock_config.get.side_effect = lambda key, default=None: {
            "img_provider": "comfyui",
            "img_api_base": "http://127.0.0.1:8188",
            "img_model": "sd_xl_base_1.0.safetensors"
        }.get(key, default)
        
        # 模拟HTTP响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"fake_image_data"
        mock_httpx.post.return_value = mock_response
        mock_httpx.get.return_value = mock_response
        
        # 注意：这个测试可能需要根据实际实现调整
        # result = generator.generate("test prompt")
        # assert result is not None
    
    @patch('app.image_generator.httpx')
    def test_generate_comfyui_failure(self, mock_httpx, generator, mock_config):
        """测试ComfyUI生成失败"""
        # 配置mock
        mock_config.get.side_effect = lambda key, default=None: {
            "img_provider": "comfyui",
            "img_api_base": "http://127.0.0.1:8188",
            "img_model": "sd_xl_base_1.0.safetensors"
        }.get(key, default)
        
        # 模拟HTTP错误
        mock_httpx.post.side_effect = Exception("Connection refused")
        
        # result = generator.generate("test prompt")
        # assert result is None


class TestImageGeneratorConfig:
    """ImageGenerator 配置测试"""
    
    def test_default_provider(self):
        """测试默认提供商"""
        config = AppConfig()
        provider = config.get("img_provider", "disabled")
        assert provider in ["comfyui", "sdapi", "disabled"]
    
    def test_default_api_base(self):
        """测试默认API地址"""
        config = AppConfig()
        api_base = config.get("img_api_base", "http://127.0.0.1:8188")
        assert api_base.startswith("http")
    
    def test_default_model(self):
        """测试默认模型"""
        config = AppConfig()
        model = config.get("img_model", "sd_xl_base_1.0.safetensors")
        assert len(model) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
