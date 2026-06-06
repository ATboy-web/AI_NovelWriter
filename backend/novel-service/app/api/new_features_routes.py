"""
新功能API路由
集成向量检索、一致性审校、定稿系统、对话推演、故事流推演、风格转换、事物描写库、角色桥段库
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# 创建路由器
router = APIRouter()

# ==================== 向量检索 API ====================

class VectorSearchRequest(BaseModel):
    """向量搜索请求"""
    novel_id: str = Field(..., description="小说ID")
    query: str = Field(..., description="搜索查询")
    n_results: int = Field(5, description="返回结果数量")

class VectorSearchResponse(BaseModel):
    """向量搜索响应"""
    success: bool
    results: List[Dict[str, Any]]
    query: str

@router.post("/vector/search", response_model=VectorSearchResponse, tags=["向量检索"])
async def search_vector(request: VectorSearchRequest):
    """搜索向量数据库"""
    try:
        from ..vector_store import search_novel_content
        
        results = search_novel_content(
            novel_id=request.novel_id,
            query=request.query,
            n_results=request.n_results
        )
        
        return VectorSearchResponse(
            success=True,
            results=results,
            query=request.query
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"向量搜索失败: {str(e)}")

class VectorAddRequest(BaseModel):
    """向量添加请求"""
    novel_id: str = Field(..., description="小说ID")
    chapter_number: int = Field(..., description="章节号")
    chapter_title: str = Field(..., description="章节标题")
    chapter_content: str = Field(..., description="章节内容")

@router.post("/vector/add", tags=["向量检索"])
async def add_to_vector(request: VectorAddRequest):
    """添加内容到向量数据库"""
    try:
        from ..vector_store import add_chapter_to_vector_store
        
        result = add_chapter_to_vector_store(
            novel_id=request.novel_id,
            chapter_number=request.chapter_number,
            chapter_title=request.chapter_title,
            chapter_content=request.chapter_content
        )
        
        return {"success": result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加到向量数据库失败: {str(e)}")

# ==================== 一致性审校 API ====================

class ConsistencyCheckRequest(BaseModel):
    """一致性检查请求"""
    chapter_number: int = Field(..., description="章节号")
    chapter_title: str = Field(..., description="章节标题")
    chapter_content: str = Field(..., description="章节内容")
    character_profiles: Optional[Dict[str, Dict[str, Any]]] = Field(None, description="角色档案")
    previous_chapters: Optional[List[Dict[str, Any]]] = Field(None, description="前文章节")
    settings: Optional[Dict[str, Any]] = Field(None, description="设定")

class ConsistencyCheckResponse(BaseModel):
    """一致性检查响应"""
    success: bool
    chapter_number: int
    chapter_title: str
    total_conflicts: int
    score: int
    conflicts: List[Dict[str, Any]]

@router.post("/consistency/check", response_model=ConsistencyCheckResponse, tags=["一致性审校"])
async def check_consistency(request: ConsistencyCheckRequest):
    """检查章节一致性"""
    try:
        from ..consistency_checker import check_chapter_consistency
        
        result = await check_chapter_consistency(
            chapter_number=request.chapter_number,
            chapter_title=request.chapter_title,
            chapter_content=request.chapter_content,
            character_profiles=request.character_profiles,
            previous_chapters=request.previous_chapters,
            settings=request.settings
        )
        
        if result.get("success"):
            return ConsistencyCheckResponse(
                success=True,
                chapter_number=result["chapter_number"],
                chapter_title=result["chapter_title"],
                total_conflicts=result["total_conflicts"],
                score=result["score"],
                conflicts=result["conflicts"]
            )
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "一致性检查失败"))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"一致性检查失败: {str(e)}")

# ==================== 定稿系统 API ====================

class FinalizeChapterRequest(BaseModel):
    """定稿章节请求"""
    chapter_number: int = Field(..., description="章节号")
    chapter_title: str = Field(..., description="章节标题")
    chapter_content: str = Field(..., description="章节内容")
    chapter_outline: str = Field(..., description="章节大纲")
    novel_id: str = Field("default", description="小说ID")
    title: str = Field("", description="小说标题")
    synopsis: str = Field("", description="小说简介")
    novel_type: str = Field("", description="小说类型")
    character_profiles: Optional[Dict[str, Dict[str, Any]]] = Field(None, description="角色档案")
    settings: Optional[Dict[str, Any]] = Field(None, description="设定")

class FinalizeChapterResponse(BaseModel):
    """定稿章节响应"""
    success: bool
    chapter_number: int
    chapter_title: str
    status: str
    chapter_summary: str
    character_updates: Dict[str, Any]
    global_summary_updated: bool
    vector_store_updated: bool

@router.post("/finalization/finalize", response_model=FinalizeChapterResponse, tags=["定稿系统"])
async def finalize_chapter(request: FinalizeChapterRequest):
    """定稿章节"""
    try:
        from ..finalization import finalize_chapter
        
        result = await finalize_chapter(
            chapter_number=request.chapter_number,
            chapter_title=request.chapter_title,
            chapter_content=request.chapter_content,
            chapter_outline=request.chapter_outline,
            novel_id=request.novel_id,
            title=request.title,
            synopsis=request.synopsis,
            novel_type=request.novel_type,
            character_profiles=request.character_profiles,
            settings=request.settings
        )
        
        if result.get("success"):
            return FinalizeChapterResponse(
                success=True,
                chapter_number=result["chapter_number"],
                chapter_title=result["chapter_title"],
                status=result["status"],
                chapter_summary=result["chapter_summary"],
                character_updates=result["character_updates"],
                global_summary_updated=result["global_summary_updated"],
                vector_store_updated=result["vector_store_updated"]
            )
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "定稿失败"))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"定稿失败: {str(e)}")

@router.get("/finalization/summary/{novel_id}", tags=["定稿系统"])
async def get_novel_summary(novel_id: str):
    """获取小说全局摘要"""
    try:
        from ..finalization import get_finalization_manager
        
        manager = get_finalization_manager()
        
        return {
            "success": True,
            "novel_id": novel_id,
            "global_summary": manager.get_global_summary(),
            "chapter_summaries": manager.get_chapter_summaries(),
            "character_states": manager.get_all_character_states(),
            "novel_data": manager.get_novel_data()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取摘要失败: {str(e)}")

# ==================== 对话推演 API ====================

class DialogueRequest(BaseModel):
    """对话生成请求"""
    characters: List[str] = Field(..., description="参与角色")
    scenario: str = Field(..., description="场景描述")
    dialogue_type: str = Field("conversation", description="对话类型")
    style: str = Field("casual", description="对话风格")
    rounds: int = Field(5, description="对话轮数")
    context: Optional[str] = Field(None, description="上下文")
    emotional_tone: Optional[str] = Field(None, description="情感基调")
    character_profiles: Optional[Dict[str, Dict[str, Any]]] = Field(None, description="角色档案")

class DialogueResponse(BaseModel):
    """对话生成响应"""
    success: bool
    characters: List[str]
    scenario: str
    dialogue_type: str
    style: str
    dialogue: List[Dict[str, Any]]
    summary: str

@router.post("/dialogue/generate", response_model=DialogueResponse, tags=["对话推演"])
async def generate_dialogue_api(request: DialogueRequest):
    """生成对话"""
    try:
        from ..dialogue import generate_dialogue
        
        result = await generate_dialogue(
            characters=request.characters,
            scenario=request.scenario,
            dialogue_type=request.dialogue_type,
            style=request.style,
            rounds=request.rounds,
            context=request.context,
            emotional_tone=request.emotional_tone,
            character_profiles=request.character_profiles
        )
        
        if result.get("success"):
            return DialogueResponse(
                success=True,
                characters=result["characters"],
                scenario=result["scenario"],
                dialogue_type=result["dialogue_type"],
                style=result["style"],
                dialogue=result["dialogue"],
                summary=result.get("summary", "")
            )
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "对话生成失败"))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对话生成失败: {str(e)}")

class ContinueDialogueRequest(BaseModel):
    """继续对话请求"""
    dialogue_history: List[Dict[str, Any]] = Field(..., description="对话历史")
    next_character: str = Field(..., description="下一个发言角色")
    response_hint: Optional[str] = Field(None, description="回应提示")
    character_profiles: Optional[Dict[str, Dict[str, Any]]] = Field(None, description="角色档案")

@router.post("/dialogue/continue", tags=["对话推演"])
async def continue_dialogue_api(request: ContinueDialogueRequest):
    """继续对话"""
    try:
        from ..dialogue import continue_dialogue
        
        result = await continue_dialogue(
            dialogue_history=request.dialogue_history,
            next_character=request.next_character,
            response_hint=request.response_hint,
            character_profiles=request.character_profiles
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"继续对话失败: {str(e)}")

# ==================== 故事流推演 API ====================

class StoryFlowRequest(BaseModel):
    """故事流推演请求"""
    flow_type: str = Field(..., description="推演类型")
    start_point: str = Field(..., description="起始点")
    end_point: Optional[str] = Field(None, description="终点")
    num_events: int = Field(5, description="事件数量")
    complexity: str = Field("medium", description="复杂度")
    setting: Optional[Dict[str, Any]] = Field(None, description="世界观设定")
    characters: Optional[Dict[str, Dict[str, Any]]] = Field(None, description="角色信息")
    themes: Optional[List[str]] = Field(None, description="主题")

class StoryFlowResponse(BaseModel):
    """故事流推演响应"""
    success: bool
    flow_type: str
    start_point: str
    end_point: Optional[str]
    events: List[Dict[str, Any]]
    summary: str

@router.post("/story-flow/generate", response_model=StoryFlowResponse, tags=["故事流推演"])
async def generate_story_flow_api(request: StoryFlowRequest):
    """生成故事流"""
    try:
        from ..story_flow import generate_story_flow
        
        result = await generate_story_flow(
            flow_type=request.flow_type,
            start_point=request.start_point,
            end_point=request.end_point,
            num_events=request.num_events,
            complexity=request.complexity,
            setting=request.setting,
            characters=request.characters,
            themes=request.themes
        )
        
        if result.get("success"):
            return StoryFlowResponse(
                success=True,
                flow_type=result["flow_type"],
                start_point=result["start_point"],
                end_point=result.get("end_point"),
                events=result["events"],
                summary=result.get("summary", "")
            )
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "故事流推演失败"))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"故事流推演失败: {str(e)}")

class BranchingScenariosRequest(BaseModel):
    """分支场景请求"""
    current_situation: str = Field(..., description="当前情境")
    num_branches: int = Field(3, description="分支数量")
    events_per_branch: int = Field(4, description="每分支事件数")
    setting: Optional[Dict[str, Any]] = Field(None, description="世界观设定")
    characters: Optional[Dict[str, Dict[str, Any]]] = Field(None, description="角色信息")

@router.post("/story-flow/branching", tags=["故事流推演"])
async def generate_branching_scenarios_api(request: BranchingScenariosRequest):
    """生成分支场景"""
    try:
        from ..story_flow import generate_branching_scenarios
        
        result = await generate_branching_scenarios(
            current_situation=request.current_situation,
            num_branches=request.num_branches,
            events_per_branch=request.events_per_branch,
            setting=request.setting,
            characters=request.characters
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分支场景生成失败: {str(e)}")

class ConflictEscalationRequest(BaseModel):
    """冲突升级请求"""
    initial_conflict: str = Field(..., description="初始冲突")
    characters_involved: List[str] = Field(..., description="涉及角色")
    escalation_steps: int = Field(4, description="升级步骤数")
    characters: Optional[Dict[str, Dict[str, Any]]] = Field(None, description="角色信息")

@router.post("/story-flow/conflict-escalation", tags=["故事流推演"])
async def generate_conflict_escalation_api(request: ConflictEscalationRequest):
    """生成冲突升级"""
    try:
        from ..story_flow import generate_conflict_escalation
        
        result = await generate_conflict_escalation(
            initial_conflict=request.initial_conflict,
            characters_involved=request.characters_involved,
            escalation_steps=request.escalation_steps,
            characters=request.characters
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"冲突升级生成失败: {str(e)}")

# ==================== 风格转换 API ====================

class StyleTransferRequest(BaseModel):
    """风格转换请求"""
    source_text: str = Field(..., description="源文本")
    target_style: str = Field(..., description="目标风格")
    mode: str = Field("imitate", description="转换模式")
    preserve_plot: bool = Field(True, description="保持情节")
    length_adjustment: Optional[str] = Field(None, description="长度调整")

class StyleTransferResponse(BaseModel):
    """风格转换响应"""
    success: bool
    original_text: str
    transferred_text: str
    target_style: str
    mode: str

@router.post("/style-transfer/transfer", response_model=StyleTransferResponse, tags=["风格转换"])
async def transfer_style_api(request: StyleTransferRequest):
    """转换文本风格"""
    try:
        from ..style_transfer import transfer_style
        
        result = await transfer_style(
            source_text=request.source_text,
            target_style=request.target_style,
            mode=request.mode,
            preserve_plot=request.preserve_plot,
            length_adjustment=request.length_adjustment
        )
        
        if result.get("success"):
            return StyleTransferResponse(
                success=True,
                original_text=result["original_text"],
                transferred_text=result["transferred_text"],
                target_style=result["target_style"],
                mode=result["mode"]
            )
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "风格转换失败"))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"风格转换失败: {str(e)}")

class ImitateAuthorRequest(BaseModel):
    """模仿作家请求"""
    text: str = Field(..., description="源文本")
    author_name: str = Field(..., description="作家名称")
    sample_works: Optional[List[str]] = Field(None, description="参考作品")

@router.post("/style-transfer/imitate-author", tags=["风格转换"])
async def imitate_author_style_api(request: ImitateAuthorRequest):
    """模仿作家风格"""
    try:
        from ..style_transfer import imitate_author_style
        
        result = await imitate_author_style(
            text=request.text,
            author_name=request.author_name,
            sample_works=request.sample_works
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"风格模仿失败: {str(e)}")

@router.get("/style-transfer/templates", tags=["风格转换"])
async def get_style_templates():
    """获取风格模板"""
    try:
        from ..style_transfer import get_style_transfer_manager
        
        manager = get_style_transfer_manager()
        
        return {
            "success": True,
            "templates": manager.get_style_templates()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取风格模板失败: {str(e)}")

# ==================== 事物描写库 API ====================

class DescriptionRequest(BaseModel):
    """描写生成请求"""
    subject: str = Field(..., description="描写对象")
    category: str = Field("nature", description="描写类别")
    style: str = Field("detailed", description="描写风格")
    context: Optional[str] = Field(None, description="上下文")
    length: str = Field("medium", description="长度")

class DescriptionResponse(BaseModel):
    """描写生成响应"""
    success: bool
    subject: str
    category: str
    style: str
    description: str

@router.post("/description/generate", response_model=DescriptionResponse, tags=["事物描写库"])
async def generate_description_api(request: DescriptionRequest):
    """生成事物描写"""
    try:
        from ..description_library import generate_description
        
        result = await generate_description(
            subject=request.subject,
            category=request.category,
            style=request.style,
            context=request.context,
            length=request.length
        )
        
        if result.get("success"):
            return DescriptionResponse(
                success=True,
                subject=result["subject"],
                category=result["category"],
                style=result["style"],
                description=result["description"]
            )
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "描写生成失败"))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"描写生成失败: {str(e)}")

class SceneDescriptionRequest(BaseModel):
    """场景描写请求"""
    scene_type: str = Field(..., description="场景类型")
    elements: List[str] = Field(..., description="场景元素")
    mood: Optional[str] = Field(None, description="氛围")
    time_of_day: Optional[str] = Field(None, description="时间")
    weather: Optional[str] = Field(None, description="天气")

@router.post("/description/scene", tags=["事物描写库"])
async def generate_scene_description_api(request: SceneDescriptionRequest):
    """生成场景描写"""
    try:
        from ..description_library import generate_scene_description
        
        result = await generate_scene_description(
            scene_type=request.scene_type,
            elements=request.elements,
            mood=request.mood,
            time_of_day=request.time_of_day,
            weather=request.weather
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"场景描写生成失败: {str(e)}")

@router.get("/description/search", tags=["事物描写库"])
async def search_descriptions_api(query: str, category: Optional[str] = None):
    """搜索描写"""
    try:
        from ..description_library import search_descriptions
        
        results = search_descriptions(
            query=query,
            category=category
        )
        
        return {
            "success": True,
            "query": query,
            "results": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索描写失败: {str(e)}")

@router.get("/description/categories", tags=["事物描写库"])
async def get_description_categories():
    """获取描写类别"""
    try:
        from ..description_library import get_description_manager
        
        manager = get_description_manager()
        
        return {
            "success": True,
            "categories": manager.get_categories()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取描写类别失败: {str(e)}")

# ==================== 角色桥段库 API ====================

class BridgeRequest(BaseModel):
    """桥段生成请求"""
    category: str = Field(..., description="桥段类别")
    characters: List[str] = Field(..., description="参与角色")
    scenario: Optional[str] = Field(None, description="场景设定")
    tone: str = Field("serious", description="基调")
    complexity: str = Field("medium", description="复杂度")

class BridgeResponse(BaseModel):
    """桥段生成响应"""
    success: bool
    bridge: Dict[str, Any]

@router.post("/bridge/generate", response_model=BridgeResponse, tags=["角色桥段库"])
async def generate_bridge_api(request: BridgeRequest):
    """生成桥段"""
    try:
        from ..bridge_library import generate_bridge
        
        result = await generate_bridge(
            category=request.category,
            characters=request.characters,
            scenario=request.scenario,
            tone=request.tone,
            complexity=request.complexity
        )
        
        if result.get("success"):
            return BridgeResponse(
                success=True,
                bridge=result["bridge"]
            )
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "桥段生成失败"))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"桥段生成失败: {str(e)}")

class CombineBridgesRequest(BaseModel):
    """组合桥段请求"""
    bridge_names: List[str] = Field(..., description="桥段名称列表")
    characters: List[str] = Field(..., description="参与角色")
    combination_style: str = Field("sequential", description="组合方式")

@router.post("/bridge/combine", tags=["角色桥段库"])
async def combine_bridges_api(request: CombineBridgesRequest):
    """组合桥段"""
    try:
        from ..bridge_library import combine_bridges
        
        result = await combine_bridges(
            bridge_names=request.bridge_names,
            characters=request.characters,
            combination_style=request.combination_style
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"桥段组合失败: {str(e)}")

@router.get("/bridge/search", tags=["角色桥段库"])
async def search_bridges_api(query: str, category: Optional[str] = None):
    """搜索桥段"""
    try:
        from ..bridge_library import search_bridges
        
        results = search_bridges(
            query=query,
            category=category
        )
        
        return {
            "success": True,
            "query": query,
            "results": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索桥段失败: {str(e)}")

@router.get("/bridge/categories", tags=["角色桥段库"])
async def get_bridge_categories():
    """获取桥段类别"""
    try:
        from ..bridge_library import get_bridge_manager
        
        manager = get_bridge_manager()
        
        return {
            "success": True,
            "categories": manager.get_categories()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取桥段类别失败: {str(e)}")

# ==================== 健康检查 API ====================

@router.get("/new-features/health", tags=["健康检查"])
async def new_features_health_check():
    """新功能健康检查"""
    try:
        # 检查各个模块是否可用
        modules_status = {}
        
        try:
            from ..vector_store import get_vector_store_manager
            modules_status["vector_store"] = "available"
        except ImportError:
            modules_status["vector_store"] = "unavailable"
        
        try:
            from ..consistency_checker import get_consistency_checker
            modules_status["consistency_checker"] = "available"
        except ImportError:
            modules_status["consistency_checker"] = "unavailable"
        
        try:
            from ..finalization import get_finalization_manager
            modules_status["finalization"] = "available"
        except ImportError:
            modules_status["finalization"] = "unavailable"
        
        try:
            from ..dialogue import get_dialogue_manager
            modules_status["dialogue"] = "available"
        except ImportError:
            modules_status["dialogue"] = "unavailable"
        
        try:
            from ..story_flow import get_story_flow_manager
            modules_status["story_flow"] = "available"
        except ImportError:
            modules_status["story_flow"] = "unavailable"
        
        try:
            from ..style_transfer import get_style_transfer_manager
            modules_status["style_transfer"] = "available"
        except ImportError:
            modules_status["style_transfer"] = "unavailable"
        
        try:
            from ..description_library import get_description_manager
            modules_status["description_library"] = "available"
        except ImportError:
            modules_status["description_library"] = "unavailable"
        
        try:
            from ..bridge_library import get_bridge_manager
            modules_status["bridge_library"] = "available"
        except ImportError:
            modules_status["bridge_library"] = "unavailable"
        
        return {
            "status": "healthy",
            "modules": modules_status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
