import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import sys
from pathlib import Path

# 将 novel-service 目录加入路径（目录名含连字符，无法直接 import）
_novel_service_dir = str(Path(__file__).resolve().parent.parent / "novel-service")
if _novel_service_dir not in sys.path:
    sys.path.insert(0, _novel_service_dir)

# 确保从正确的 app 包导入（novel-service/app 而非根目录/app）
try:
    from app.generators.novel_generator import (
        NovelType, NovelGenerator, GenericNovelGenerator, NovelGeneratorFactory,
        SciFiNovelGenerator, MysteryNovelGenerator, RomanceNovelGenerator
    )
except ImportError:
    # 如果导入失败，尝试使用完整路径
    import importlib.util
    _gen_file = Path(_novel_service_dir) / "app" / "generators" / "novel_generator.py"
    _spec = importlib.util.spec_from_file_location("novel_generator", str(_gen_file))
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    NovelType = _mod.NovelType
    NovelGenerator = _mod.NovelGenerator
    GenericNovelGenerator = _mod.GenericNovelGenerator
    NovelGeneratorFactory = _mod.NovelGeneratorFactory
    SciFiNovelGenerator = _mod.SciFiNovelGenerator
    MysteryNovelGenerator = _mod.MysteryNovelGenerator
    RomanceNovelGenerator = _mod.RomanceNovelGenerator


class TestNovelType:
    """测试NovelType枚举"""
    
    def test_novel_type_values(self):
        """测试小说类型值"""
        assert NovelType.SCIFI == "scifi"
        assert NovelType.MYSTERY == "mystery"
        assert NovelType.ROMANCE == "romance"
        assert NovelType.FANTASY == "fantasy"
        assert NovelType.URBAN == "urban"
    
    def test_novel_type_count(self):
        """测试小说类型数量"""
        assert len(NovelType) == 15  # 15种小说类型


class TestNovelGenerator:
    """测试NovelGenerator基类"""
    
    def test_generator_initialization(self):
        """测试生成器初始化"""
        generator = GenericNovelGenerator(
            NovelType.SCIFI, "科幻",
            ["未来科技", "太空探索"],
            "硬科幻风格"
        )
        assert generator.novel_type == NovelType.SCIFI
        assert generator.genre_name == "科幻"
        assert generator.features == ["未来科技", "太空探索"]
        assert generator.style_desc == "硬科幻风格"
    
    def test_generator_metadata(self):
        """测试生成器元数据"""
        generator = GenericNovelGenerator(
            NovelType.MYSTERY, "悬疑推理",
            ["犯罪谜题", "逻辑推理"],
            "注重逻辑推理"
        )
        assert generator.metadata["genre"] == "悬疑推理"
        assert "犯罪谜题" in generator.metadata["features"]


class TestGenericNovelGenerator:
    """测试GenericNovelGenerator"""
    
    @pytest.fixture
    def generator(self):
        """创建测试用生成器"""
        return GenericNovelGenerator(
            NovelType.SCIFI, "科幻",
            ["未来科技", "太空探索", "人工智能"],
            "硬科幻风格",
            ai_service_url="http://test:8001"
        )
    
    @pytest.mark.asyncio
    async def test_generate_outline_success(self, generator):
        """测试成功生成大纲"""
        mock_response = {
            "success": True,
            "title": "测试小说",
            "synopsis": "测试简介",
            "chapters": [{"title": "第1章", "summary": "测试摘要"}],
            "characters": [{"name": "主角", "role": "主角"}]
        }
        
        with patch.object(generator, '_call_ai_service', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response
            result = await generator.generate_outline("测试小说", "测试简介", 5)
            
            assert result["title"] == "测试小说"
            mock_call.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_outline_fallback(self, generator):
        """测试大纲生成失败时的降级处理"""
        with patch.object(generator, '_call_ai_service', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("API调用失败")
            result = await generator.generate_outline("测试小说", "测试简介", 5)
            
            assert "title" in result
            assert "chapters" in result
            assert len(result["chapters"]) == 5
    
    @pytest.mark.asyncio
    async def test_generate_chapter_success(self, generator):
        """测试成功生成章节"""
        mock_response = {
            "success": True,
            "content": "这是测试章节内容"
        }
        
        with patch.object(generator, '_call_ai_service', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response
            result = await generator.generate_chapter(0, "测试大纲")
            
            assert result == "这是测试章节内容"
    
    @pytest.mark.asyncio
    async def test_generate_chapter_fallback(self, generator):
        """测试章节生成失败时的降级处理"""
        with patch.object(generator, '_call_ai_service', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = Exception("API调用失败")
            result = await generator.generate_chapter(0, "测试大纲")
            
            assert "第1章" in result
            assert "测试大纲" in result
    
    @pytest.mark.asyncio
    async def test_generate_character_success(self, generator):
        """测试成功生成人物"""
        mock_response = {
            "success": True,
            "character_profile": {
                "basic_info": {"age": 25, "gender": "男"},
                "personality": ["勇敢", "聪明"]
            }
        }
        
        with patch.object(generator, '_call_ai_service', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response
            result = await generator.generate_character("主角", "主角", ["勇敢"])
            
            assert result["basic_info"]["age"] == 25
            assert "勇敢" in result["personality"]
    
    @pytest.mark.asyncio
    async def test_analyze_style_success(self, generator):
        """测试成功分析风格"""
        mock_response = {
            "success": True,
            "analysis_results": {
                "language_style": "科幻风格",
                "narrative_perspective": "第三人称"
            }
        }
        
        with patch.object(generator, '_call_ai_service', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response
            result = await generator.analyze_style("测试内容")
            
            assert result["language_style"] == "科幻风格"


class TestNovelGeneratorFactory:
    """测试NovelGeneratorFactory"""
    
    def test_create_scifi_generator(self):
        """测试创建科幻生成器"""
        generator = NovelGeneratorFactory.create_generator(NovelType.SCIFI)
        assert isinstance(generator, SciFiNovelGenerator)
        assert generator.novel_type == NovelType.SCIFI
    
    def test_create_mystery_generator(self):
        """测试创建悬疑生成器"""
        generator = NovelGeneratorFactory.create_generator(NovelType.MYSTERY)
        assert isinstance(generator, MysteryNovelGenerator)
        assert generator.novel_type == NovelType.MYSTERY
    
    def test_create_romance_generator(self):
        """测试创建言情生成器"""
        generator = NovelGeneratorFactory.create_generator(NovelType.ROMANCE)
        assert isinstance(generator, RomanceNovelGenerator)
        assert generator.novel_type == NovelType.ROMANCE
    
    def test_create_unsupported_type(self):
        """测试创建不支持的类型"""
        with pytest.raises(ValueError) as exc_info:
            NovelGeneratorFactory.create_generator("unsupported_type")
        assert "不支持的小说类型" in str(exc_info.value)
    
    def test_get_supported_types(self):
        """测试获取支持的类型列表"""
        types = NovelGeneratorFactory.get_supported_types()
        assert len(types) == 15
        assert any(t["type"] == "scifi" for t in types)
        assert any(t["type"] == "mystery" for t in types)


class TestSpecificGenerators:
    """测试具体生成器类型"""
    
    def test_scifi_generator_metadata(self):
        """测试科幻生成器元数据"""
        generator = SciFiNovelGenerator()
        assert generator.novel_type == NovelType.SCIFI
        assert "未来科技" in generator.features
        assert "硬科幻" in generator.style_desc
    
    def test_mystery_generator_metadata(self):
        """测试悬疑生成器元数据"""
        generator = MysteryNovelGenerator()
        assert generator.novel_type == NovelType.MYSTERY
        assert "犯罪谜题" in generator.features
        assert "逻辑推理" in generator.style_desc
    
    def test_romance_generator_metadata(self):
        """测试言情生成器元数据"""
        generator = RomanceNovelGenerator()
        assert generator.novel_type == NovelType.ROMANCE
        assert "情感细腻" in generator.features
        assert "情感描写" in generator.style_desc


@pytest.mark.asyncio
class TestGeneratorIntegration:
    """集成测试"""
    
    async def test_generate_full_novel_flow(self):
        """测试完整小说生成流程"""
        generator = GenericNovelGenerator(
            NovelType.SCIFI, "科幻",
            ["未来科技"], "硬科幻风格"
        )
        
        # 模拟AI服务调用
        with patch.object(generator, '_call_ai_service', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = [
                # 大纲响应
                {
                    "success": True,
                    "title": "测试小说",
                    "synopsis": "测试简介",
                    "chapters": [
                        {"title": "第1章", "summary": "章节1"},
                        {"title": "第2章", "summary": "章节2"}
                    ],
                    "characters": [
                        {"name": "主角", "role": "主角", "traits": ["勇敢"]}
                    ]
                },
                # 人物响应
                {
                    "success": True,
                    "character_profile": {
                        "basic_info": {"age": 25},
                        "personality": ["勇敢"]
                    }
                },
                # 章节1响应
                {
                    "success": True,
                    "content": "章节1内容"
                },
                # 章节2响应
                {
                    "success": True,
                    "content": "章节2内容"
                }
            ]
            
            result = await generator.generate_full_novel("测试小说", "测试简介", 2)
            
            assert result["success"] is True
            assert result["title"] == "测试小说"
            assert len(result["chapters"]) == 2
            assert len(result["characters"]) == 1
            assert result["statistics"]["total_chapters"] == 2