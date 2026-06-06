"""
小说生成服务 - 核心应用
负责小说生成的核心业务逻辑
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uvicorn
from datetime import datetime

# 导入自定义模块
from .core.config import settings
from .generators.novel_generator import NovelGeneratorFactory, NovelType
from .api.routes import router as api_router

# 延迟导入新功能路由（避免PyInstaller打包问题）
try:
    from .api.new_features_routes import router as new_features_router
    HAS_NEW_FEATURES = True
except ImportError:
    HAS_NEW_FEATURES = False
    new_features_router = None

# 创建FastAPI应用
app = FastAPI(
    title="小说生成服务",
    description="负责小说生成的核心业务逻辑",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 包含API路由
app.include_router(api_router, prefix="/api/v1")
if HAS_NEW_FEATURES and new_features_router:
    app.include_router(new_features_router, prefix="/api/v1")


class NovelRequest(BaseModel):
    """小说生成请求"""
    title: str = Field(..., description="小说标题")
    synopsis: str = Field(..., description="小说简介")
    novel_type: NovelType = Field(NovelType.SCIFI, description="小说类型")
    chapter_count: int = Field(10, description="章节数量")
    ai_service_url: str = Field("http://localhost:8001", description="AI服务地址")

class NovelResponse(BaseModel):
    """小说生成响应"""
    success: bool
    title: str
    novel_type: str
    chapters: List[Dict[str, Any]]
    characters: List[Dict[str, Any]]
    statistics: Dict[str, Any]
    generation_time: float

class ChapterRequest(BaseModel):
    """章节生成请求"""
    novel_type: NovelType = Field(NovelType.SCIFI, description="小说类型")
    chapter_title: str = Field(..., description="章节标题")
    chapter_outline: str = Field(..., description="章节大纲")
    previous_content: Optional[str] = Field(None, description="前文内容")
    ai_service_url: str = Field("http://localhost:8001", description="AI服务地址")

class ChapterResponse(BaseModel):
    """章节生成响应"""
    success: bool
    content: str
    chapter_title: str
    novel_type: str
    word_count: int
    generation_time: float

class CharacterRequest(BaseModel):
    """人物生成请求"""
    novel_type: NovelType = Field(NovelType.SCIFI, description="小说类型")
    character_name: str = Field(..., description="人物姓名")
    character_role: str = Field(..., description="人物角色")
    character_traits: List[str] = Field(..., description="人物特征")
    ai_service_url: str = Field("http://localhost:8001", description="AI服务地址")

class CharacterResponse(BaseModel):
    """人物生成响应"""
    success: bool
    character_name: str
    character_profile: Dict[str, Any]
    generation_time: float

class OutlineRequest(BaseModel):
    """大纲生成请求"""
    novel_type: NovelType = Field(NovelType.SCIFI, description="小说类型")
    title: str = Field(..., description="小说标题")
    synopsis: str = Field(..., description="小说简介")
    chapter_count: int = Field(10, description="章节数量")
    ai_service_url: str = Field("http://localhost:8001", description="AI服务地址")

class OutlineResponse(BaseModel):
    """大纲生成响应"""
    success: bool
    title: str
    novel_type: str
    chapters: List[Dict[str, Any]]
    characters: List[Dict[str, Any]]
    generation_time: float

@app.get("/", tags=["根路径"])
async def root():
    """根路径信息"""
    return {
        "message": "小说生成服务运行中",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health", tags=["健康检查"])
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(),
        "version": "1.0.0"
    }

@app.post("/generate/novel", response_model=NovelResponse, tags=["小说生成"])
async def generate_novel(request: NovelRequest):
    """生成完整小说"""
    try:
        start_time = datetime.now()
        
        # 创建小说生成器
        generator = NovelGeneratorFactory.create_generator(
            novel_type=request.novel_type,
            ai_service_url=request.ai_service_url
        )
        
        # 生成完整小说
        result = await generator.generate_full_novel(
            title=request.title,
            synopsis=request.synopsis,
            chapter_count=request.chapter_count
        )
        
        generation_time = (datetime.now() - start_time).total_seconds()
        
        if result.get("success"):
            return NovelResponse(
                success=True,
                title=result["title"],
                novel_type=result["novel_type"],
                chapters=result["chapters"],
                characters=result["characters"],
                statistics=result["statistics"],
                generation_time=generation_time
            )
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "小说生成失败"))
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"小说生成失败: {str(e)}")

@app.post("/generate/chapter", response_model=ChapterResponse, tags=["章节生成"])
async def generate_chapter(request: ChapterRequest):
    """生成单个章节"""
    try:
        start_time = datetime.now()
        
        # 创建小说生成器
        generator = NovelGeneratorFactory.create_generator(
            novel_type=request.novel_type,
            ai_service_url=request.ai_service_url
        )
        
        # 生成章节内容
        content = await generator.generate_chapter(
            chapter_index=0,
            chapter_outline=request.chapter_outline,
            previous_content=request.previous_content or ""
        )
        
        generation_time = (datetime.now() - start_time).total_seconds()
        word_count = len(content)
        
        return ChapterResponse(
            success=True,
            content=content,
            chapter_title=request.chapter_title,
            novel_type=request.novel_type.value,
            word_count=word_count,
            generation_time=generation_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"章节生成失败: {str(e)}")

@app.post("/generate/character", response_model=CharacterResponse, tags=["人物生成"])
async def generate_character(request: CharacterRequest):
    """生成人物设定"""
    try:
        start_time = datetime.now()
        
        # 创建小说生成器
        generator = NovelGeneratorFactory.create_generator(
            novel_type=request.novel_type,
            ai_service_url=request.ai_service_url
        )
        
        # 生成人物设定
        character_profile = await generator.generate_character(
            character_name=request.character_name,
            character_role=request.character_role,
            character_traits=request.character_traits
        )
        
        generation_time = (datetime.now() - start_time).total_seconds()
        
        return CharacterResponse(
            success=True,
            character_name=request.character_name,
            character_profile=character_profile,
            generation_time=generation_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"人物生成失败: {str(e)}")

@app.post("/generate/outline", response_model=OutlineResponse, tags=["大纲生成"])
async def generate_outline(request: OutlineRequest):
    """生成小说大纲"""
    try:
        start_time = datetime.now()
        
        # 创建小说生成器
        generator = NovelGeneratorFactory.create_generator(
            novel_type=request.novel_type,
            ai_service_url=request.ai_service_url
        )
        
        # 生成大纲
        outline_result = await generator.generate_outline(
            title=request.title,
            synopsis=request.synopsis,
            chapter_count=request.chapter_count
        )
        
        generation_time = (datetime.now() - start_time).total_seconds()
        
        return OutlineResponse(
            success=True,
            title=request.title,
            novel_type=request.novel_type.value,
            chapters=outline_result.get("chapters", []),
            characters=outline_result.get("characters", []),
            generation_time=generation_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"大纲生成失败: {str(e)}")

@app.get("/novel-types", tags=["小说类型"])
async def get_novel_types():
    """获取支持的小说类型"""
    return {
        "success": True,
        "novel_types": NovelGeneratorFactory.get_supported_types()
    }

@app.get("/statistics", tags=["统计信息"])
async def get_statistics():
    """获取服务统计信息"""
    return {
        "success": True,
        "statistics": {
            "service": "小说生成服务",
            "version": "1.0.0",
            "supported_types": len(NovelGeneratorFactory.get_supported_types()),
            "status": "running"
        }
    }

@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    print("小说生成服务启动中...")
    print("小说生成服务启动完成")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    print("小说生成服务关闭中...")
    print("小说生成服务已关闭")

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=settings.WORKERS
    )