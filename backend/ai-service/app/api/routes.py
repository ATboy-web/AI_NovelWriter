"""
AI模型服务API路由
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

# 创建路由器
router = APIRouter()

# 依赖注入函数
def get_inference_engine():
    """获取推理引擎实例（延迟导入避免循环依赖）"""
    from ..main import inference_engine
    return inference_engine

class NovelType(str, Enum):
    # 基础类型
    SCIFI = "scifi"
    MYSTERY = "mystery"
    ROMANCE = "romance"
    FANTASY = "fantasy"
    URBAN = "urban"
    # 新增类型
    HISTORY = "history"
    MARTIAL_ARTS = "martial_arts"
    XIANXIA = "xianxia"
    HORROR = "horror"
    MILITARY = "military"
    GAME = "game"
    SPORTS = "sports"
    TIME_TRAVEL = "time_travel"
    SYSTEM_FLOW = "system_flow"
    APOCALYPSE = "apocalypse"

class ChapterRequest(BaseModel):
    """章节生成请求"""
    novel_type: NovelType = Field(..., description="小说类型")
    chapter_title: str = Field(..., description="章节标题")
    chapter_outline: str = Field(..., description="章节大纲")
    previous_content: Optional[str] = Field(None, description="前文内容")
    model_type: str = Field("local", description="模型类型")
    model_name: Optional[str] = Field(None, description="模型名称")
    max_tokens: int = Field(2000, description="最大token数")
    temperature: float = Field(0.8, description="生成温度")

class ChapterResponse(BaseModel):
    """章节生成响应"""
    success: bool
    content: str
    chapter_title: str
    novel_type: str
    model_used: str
    tokens_used: int
    generation_time: float
    word_count: int
    metadata: Dict[str, Any]

class NovelOutlineRequest(BaseModel):
    """小说大纲生成请求"""
    novel_type: NovelType = Field(..., description="小说类型")
    title: str = Field(..., description="小说标题")
    synopsis: str = Field(..., description="小说简介")
    chapter_count: int = Field(10, description="章节数量")
    model_type: str = Field("local", description="模型类型")
    model_name: Optional[str] = Field(None, description="模型名称")

class NovelOutlineResponse(BaseModel):
    """小说大纲生成响应"""
    success: bool
    title: str
    novel_type: str
    chapters: List[Dict[str, str]]
    total_chapters: int
    model_used: str
    tokens_used: int
    generation_time: float

class CharacterRequest(BaseModel):
    """人物生成请求"""
    novel_type: NovelType = Field(..., description="小说类型")
    character_name: str = Field(..., description="人物姓名")
    character_role: str = Field(..., description="人物角色")
    character_traits: List[str] = Field(..., description="人物特征")
    model_type: str = Field("local", description="模型类型")
    model_name: Optional[str] = Field(None, description="模型名称")

class CharacterResponse(BaseModel):
    """人物生成响应"""
    success: bool
    character_name: str
    character_profile: Dict[str, Any]
    model_used: str
    tokens_used: int
    generation_time: float

class StyleAnalysisRequest(BaseModel):
    """风格分析请求"""
    content: str = Field(..., description="待分析内容")
    analysis_type: str = Field("comprehensive", description="分析类型")
    model_type: str = Field("local", description="模型类型")
    model_name: Optional[str] = Field(None, description="模型名称")

class StyleAnalysisResponse(BaseModel):
    """风格分析响应"""
    success: bool
    analysis_results: Dict[str, Any]
    model_used: str
    tokens_used: int
    generation_time: float

@router.post("/generate/chapter", response_model=ChapterResponse, tags=["小说生成"])
async def generate_chapter(request: ChapterRequest, inference_engine=Depends(get_inference_engine)):
    """生成小说章节"""
    try:
        # 生成章节内容
        result = await inference_engine.generate_novel_chapter(
            novel_type=request.novel_type.value,
            chapter_title=request.chapter_title,
            chapter_outline=request.chapter_outline,
            previous_content=request.previous_content or "",
            model_type=request.model_type,
            model_name=request.model_name,
            max_tokens=request.max_tokens,
            temperature=request.temperature
        )
        
        # 计算字数
        word_count = len(result["content"])
        
        return ChapterResponse(
            success=True,
            content=result["content"],
            chapter_title=request.chapter_title,
            novel_type=request.novel_type.value,
            model_used=result["model_used"],
            tokens_used=result["tokens_used"],
            generation_time=result["generation_time"],
            word_count=word_count,
            metadata=result["metadata"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"章节生成失败: {str(e)}")

@router.post("/generate/outline", response_model=NovelOutlineResponse, tags=["小说生成"])
async def generate_outline(request: NovelOutlineRequest, inference_engine=Depends(get_inference_engine)):
    """生成小说大纲"""
    try:
        # 构建大纲生成提示词
        prompt = f"""请为以下小说生成详细大纲：

小说类型：{request.novel_type.value}
小说标题：{request.title}
小说简介：{request.synopsis}
章节数量：{request.chapter_count}

请生成包含{request.chapter_count}个章节的大纲，每个章节包含：
1. 章节标题
2. 章节摘要（100-200字）
3. 主要情节
4. 关键人物

请以JSON格式输出大纲，格式如下：
{{
    "chapters": [
        {{
            "title": "章节标题",
            "summary": "章节摘要",
            "plot": "主要情节",
            "characters": ["关键人物1", "关键人物2"]
        }}
    ]
}}"""
        
        # 生成大纲
        start_time = datetime.now()
        result = await inference_engine.generate_with_fallback(
            prompt=prompt,
            preferred_model=request.model_type,
            model_name=request.model_name,
            max_tokens=3000,
            temperature=0.7
        )
        generation_time = (datetime.now() - start_time).total_seconds()
        
        # 解析JSON响应
        try:
            import json
            # 尝试提取JSON部分
            content = result["content"]
            # 查找JSON开始和结束位置
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            
            if json_start != -1 and json_end != -1:
                json_str = content[json_start:json_end]
                outline_data = json.loads(json_str)
                chapters = outline_data.get("chapters", [])
            else:
                # 如果无法解析JSON，创建默认结构
                chapters = [
                    {
                        "title": f"第{i+1}章",
                        "summary": f"章节{i+1}内容",
                        "plot": "待补充",
                        "characters": []
                    }
                    for i in range(request.chapter_count)
                ]
        except json.JSONDecodeError:
            # JSON解析失败，创建默认结构
            chapters = [
                {
                    "title": f"第{i+1}章",
                    "summary": f"章节{i+1}内容",
                    "plot": "待补充",
                    "characters": []
                }
                for i in range(request.chapter_count)
            ]
        
        return NovelOutlineResponse(
            success=True,
            title=request.title,
            novel_type=request.novel_type.value,
            chapters=chapters,
            total_chapters=len(chapters),
            model_used=result["model_used"],
            tokens_used=result["tokens_used"],
            generation_time=generation_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"大纲生成失败: {str(e)}")

@router.post("/generate/character", response_model=CharacterResponse, tags=["人物生成"])
async def generate_character(request: CharacterRequest, inference_engine=Depends(get_inference_engine)):
    """生成人物设定"""
    try:
        # 构建人物生成提示词
        traits_str = "、".join(request.character_traits)
        prompt = f"""请为以下人物生成详细设定：

人物姓名：{request.character_name}
人物角色：{request.character_role}
人物特征：{traits_str}
小说类型：{request.novel_type.value}

请生成人物详细设定，包括：
1. 基本信息（年龄、性别、外貌等）
2. 性格特点
3. 背景故事
4. 人物关系
5. 成长轨迹
6. 特殊能力或技能

请以JSON格式输出，格式如下：
{{
    "basic_info": {{
        "age": 25,
        "gender": "男",
        "appearance": "外貌描述"
    }},
    "personality": ["性格特点1", "性格特点2"],
    "background": "背景故事",
    "relationships": ["人物关系1", "人物关系2"],
    "growth": "成长轨迹",
    "skills": ["技能1", "技能2"]
}}"""
        
        # 生成人物设定
        start_time = datetime.now()
        result = await inference_engine.generate_with_fallback(
            prompt=prompt,
            preferred_model=request.model_type,
            model_name=request.model_name,
            max_tokens=2000,
            temperature=0.7
        )
        generation_time = (datetime.now() - start_time).total_seconds()
        
        # 解析JSON响应
        try:
            import json
            content = result["content"]
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            
            if json_start != -1 and json_end != -1:
                json_str = content[json_start:json_end]
                character_data = json.loads(json_str)
            else:
                character_data = {
                    "basic_info": {"age": 25, "gender": "未知", "appearance": "待补充"},
                    "personality": request.character_traits,
                    "background": "待补充",
                    "relationships": [],
                    "growth": "待补充",
                    "skills": []
                }
        except json.JSONDecodeError:
            character_data = {
                "basic_info": {"age": 25, "gender": "未知", "appearance": "待补充"},
                "personality": request.character_traits,
                "background": "待补充",
                "relationships": [],
                "growth": "待补充",
                "skills": []
            }
        
        return CharacterResponse(
            success=True,
            character_name=request.character_name,
            character_profile=character_data,
            model_used=result["model_used"],
            tokens_used=result["tokens_used"],
            generation_time=generation_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"人物生成失败: {str(e)}")

@router.post("/analyze/style", response_model=StyleAnalysisResponse, tags=["文本分析"])
async def analyze_style(request: StyleAnalysisRequest, inference_engine=Depends(get_inference_engine)):
    """分析文本风格"""
    try:
        # 构建风格分析提示词
        prompt = f"""请分析以下文本的写作风格：

文本内容：
{request.content[:2000]}  # 限制长度

请从以下方面进行分析：
1. 语言风格（正式/口语化、简洁/华丽等）
2. 叙事视角（第一人称/第三人称等）
3. 情感基调（积极/消极/中性等）
4. 文学手法（比喻、拟人、排比等）
5. 句式特点（长句/短句、简单/复杂等）
6. 词汇特点（常用词汇、专业术语等）
7. 整体评价

请以JSON格式输出分析结果："""
        
        # 生成分析结果
        start_time = datetime.now()
        result = await inference_engine.generate_with_fallback(
            prompt=prompt,
            preferred_model=request.model_type,
            model_name=request.model_name,
            max_tokens=1500,
            temperature=0.3
        )
        generation_time = (datetime.now() - start_time).total_seconds()
        
        # 解析JSON响应
        try:
            import json
            content = result["content"]
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            
            if json_start != -1 and json_end != -1:
                json_str = content[json_start:json_end]
                analysis_data = json.loads(json_str)
            else:
                analysis_data = {
                    "language_style": "待分析",
                    "narrative_perspective": "待分析",
                    "emotional_tone": "待分析",
                    "literary_devices": [],
                    "sentence_features": "待分析",
                    "vocabulary_features": "待分析",
                    "overall_evaluation": "待分析"
                }
        except json.JSONDecodeError:
            analysis_data = {
                "language_style": "待分析",
                "narrative_perspective": "待分析",
                "emotional_tone": "待分析",
                "literary_devices": [],
                "sentence_features": "待分析",
                "vocabulary_features": "待分析",
                "overall_evaluation": "待分析"
            }
        
        return StyleAnalysisResponse(
            success=True,
            analysis_results=analysis_data,
            model_used=result["model_used"],
            tokens_used=result["tokens_used"],
            generation_time=generation_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"风格分析失败: {str(e)}")

@router.get("/novel-types", tags=["小说类型"])
async def get_novel_types():
    """获取支持的小说类型"""
    return {
        "success": True,
        "novel_types": [
            {
                "type": "scifi",
                "name": "科幻小说",
                "description": "具有前瞻性的科技设定和世界观",
                "features": ["未来科技", "太空探索", "人工智能", "时间旅行"]
            },
            {
                "type": "mystery",
                "name": "悬疑推理",
                "description": "逻辑严密、情节曲折的推理故事",
                "features": ["犯罪谜题", "逻辑推理", "悬疑氛围", "意外结局"]
            },
            {
                "type": "romance",
                "name": "言情小说",
                "description": "情感细腻、人物关系复杂的情感故事",
                "features": ["爱情故事", "情感纠葛", "人物成长", "温馨治愈"]
            },
            {
                "type": "fantasy",
                "name": "奇幻小说",
                "description": "丰富的魔法和世界观设定的奇幻故事",
                "features": ["魔法系统", "异世界", "史诗冒险", "神话传说"]
            },
            {
                "type": "urban",
                "name": "都市小说",
                "description": "贴近现实、人物鲜明的都市故事",
                "features": ["现实生活", "职场故事", "社会现象", "人生百态"]
            }
        ]
    }

@router.get("/health", tags=["健康检查"])
async def health_check(inference_engine=Depends(get_inference_engine)):
    """健康检查端点"""
    try:
        health_status = await inference_engine.health_check()
        return health_status
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@router.get("/statistics", tags=["统计信息"])
async def get_statistics(inference_engine=Depends(get_inference_engine)):
    """获取服务统计信息"""
    try:
        stats = await inference_engine.get_statistics()
        return {
            "success": True,
            "statistics": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")