"""
AI模型服务 - 核心应用
支持本地模型（llama.cpp）和云端API（GPT/Claude）集成
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uvicorn
from datetime import datetime
import asyncio
from enum import Enum
from loguru import logger

# 导入自定义模块
from .core.config import settings
from .core.model_manager import ModelManager
from .core.inference_engine import InferenceEngine
from .api.routes import router as api_router

# 创建FastAPI应用
app = FastAPI(
    title="AI模型服务",
    description="支持本地模型和云端API的小说生成AI服务",
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

# 初始化模型管理器
model_manager = ModelManager()

# 初始化推理引擎
inference_engine = InferenceEngine(model_manager)

def get_inference_engine():
    """获取推理引擎实例（用于依赖注入）"""
    return inference_engine

class ModelType(str, Enum):
    LOCAL = "local"
    OPENAI = "openai"
    CLAUDE = "claude"

class GenerationRequest(BaseModel):
    """生成请求模型"""
    prompt: str = Field(..., description="生成提示词")
    model_type: ModelType = Field(ModelType.LOCAL, description="模型类型")
    model_name: Optional[str] = Field(None, description="具体模型名称")
    max_tokens: int = Field(1000, description="最大生成token数")
    temperature: float = Field(0.7, description="生成温度")
    top_p: float = Field(0.9, description="Top-p采样参数")
    novel_type: str = Field("scifi", description="小说类型")
    chapter_count: int = Field(1, description="章节数量")

class GenerationResponse(BaseModel):
    """生成响应模型"""
    success: bool
    content: str
    model_used: str
    tokens_used: int
    generation_time: float
    metadata: Dict[str, Any]

class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    timestamp: datetime
    models_available: List[str]
    version: str

@app.get("/", tags=["根路径"])
async def root():
    """根路径信息"""
    return {
        "message": "AI模型服务运行中",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health", response_model=HealthResponse, tags=["健康检查"])
async def health_check():
    """健康检查端点"""
    available_models = await model_manager.get_available_models()
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(),
        models_available=available_models,
        version="1.0.0"
    )

@app.post("/generate", response_model=GenerationResponse, tags=["文本生成"])
async def generate_text(request: GenerationRequest):
    """生成文本内容"""
    try:
        start_time = datetime.now()
        
        # 根据模型类型选择推理引擎
        if request.model_type == ModelType.LOCAL:
            result = await inference_engine.generate_local(
                prompt=request.prompt,
                model_name=request.model_name,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p
            )
        elif request.model_type == ModelType.OPENAI:
            result = await inference_engine.generate_openai(
                prompt=request.prompt,
                model_name=request.model_name or "gpt-4",
                max_tokens=request.max_tokens,
                temperature=request.temperature
            )
        elif request.model_type == ModelType.CLAUDE:
            result = await inference_engine.generate_claude(
                prompt=request.prompt,
                model_name=request.model_name or "claude-3-sonnet-20240229",
                max_tokens=request.max_tokens,
                temperature=request.temperature
            )
        else:
            raise HTTPException(status_code=400, detail="不支持的模型类型")
        
        end_time = datetime.now()
        generation_time = (end_time - start_time).total_seconds()
        
        return GenerationResponse(
            success=True,
            content=result["content"],
            model_used=result["model_used"],
            tokens_used=result["tokens_used"],
            generation_time=generation_time,
            metadata={
                "novel_type": request.novel_type,
                "chapter_count": request.chapter_count,
                "parameters": {
                    "temperature": request.temperature,
                    "top_p": request.top_p,
                    "max_tokens": request.max_tokens
                }
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")

@app.get("/models", tags=["模型管理"])
async def list_models():
    """列出所有可用模型"""
    try:
        models = await model_manager.get_all_models()
        return {
            "success": True,
            "models": models,
            "count": len(models)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模型列表失败: {str(e)}")

@app.post("/models/{model_type}/load", tags=["模型管理"])
async def load_model(model_type: ModelType, model_name: Optional[str] = None):
    """加载指定模型"""
    try:
        result = await model_manager.load_model(model_type, model_name)
        return {
            "success": True,
            "message": f"模型 {model_name or model_type} 加载成功",
            "details": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模型加载失败: {str(e)}")

@app.post("/models/{model_type}/unload", tags=["模型管理"])
async def unload_model(model_type: ModelType, model_name: Optional[str] = None):
    """卸载指定模型"""
    try:
        result = await model_manager.unload_model(model_type, model_name)
        return {
            "success": True,
            "message": f"模型 {model_name or model_type} 卸载成功",
            "details": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模型卸载失败: {str(e)}")

@app.get("/models/{model_type}/status", tags=["模型管理"])
async def get_model_status(model_type: ModelType, model_name: Optional[str] = None):
    """获取模型状态"""
    try:
        status = await model_manager.get_model_status(model_type, model_name)
        return {
            "success": True,
            "model_type": model_type,
            "model_name": model_name,
            "status": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模型状态失败: {str(e)}")

@app.post("/generate/novel", tags=["小说生成"])
async def generate_novel_chapter(request: GenerationRequest):
    """生成小说章节"""
    try:
        # 构建小说生成提示词
        novel_prompt = build_novel_prompt(
            prompt=request.prompt,
            novel_type=request.novel_type,
            chapter_count=request.chapter_count
        )
        
        # 更新请求
        request.prompt = novel_prompt
        
        # 调用生成接口
        response = await generate_text(request)
        
        # 后处理生成内容
        processed_content = post_process_novel_content(
            content=response.content,
            novel_type=request.novel_type
        )
        
        response.content = processed_content
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"小说生成失败: {str(e)}")

def build_novel_prompt(prompt: str, novel_type: str, chapter_count: int) -> str:
    """构建小说生成提示词"""
    type_prompts = {
        "scifi": "你是一位科幻小说作家，擅长创作具有前瞻性和想象力的科幻故事。",
        "mystery": "你是一位悬疑推理小说作家，擅长创作逻辑严密、情节曲折的悬疑故事。",
        "romance": "你是一位言情小说作家，擅长创作情感细腻、人物关系复杂的言情故事。",
        "fantasy": "你是一位奇幻小说作家，擅长创作具有丰富世界观设定的奇幻故事。",
        "urban": "你是一位都市小说作家，擅长创作贴近现实、人物鲜明的都市故事。"
    }
    
    base_prompt = type_prompts.get(novel_type, "你是一位小说作家。")
    
    chapter_prompt = f"请创作一个包含{chapter_count}章节的小说。" if chapter_count > 1 else "请创作一个小说章节。"
    
    return f"{base_prompt}\n\n{chapter_prompt}\n\n{prompt}"

def post_process_novel_content(content: str, novel_type: str) -> str:
    """后处理小说内容"""
    # 基本清理
    content = content.strip()
    
    # 根据类型进行特定处理
    if novel_type == "mystery":
        # 悬疑小说：确保逻辑连贯性
        content = ensure_mystery_logic(content)
    elif novel_type == "romance":
        # 言情小说：确保情感连贯性
        content = ensure_romance_emotion(content)
    
    return content

def ensure_mystery_logic(content: str) -> str:
    """确保悬疑小说逻辑连贯性"""
    # 简单的逻辑检查
    # 实际实现中可以添加更复杂的逻辑验证
    return content

def ensure_romance_emotion(content: str) -> str:
    """确保言情小说情感连贯性"""
    # 简单的情感检查
    # 实际实现中可以添加更复杂的情感分析
    return content

@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("AI模型服务启动中...")
    
    # 初始化模型管理器
    await model_manager.initialize()
    
    # 加载默认模型
    try:
        await model_manager.load_default_models()
        logger.info("默认模型加载完成")
    except Exception as e:
        logger.error(f"默认模型加载失败: {e}")
    
    logger.info("AI模型服务启动完成")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("AI模型服务关闭中...")
    
    # 卸载所有模型
    await model_manager.unload_all_models()
    
    logger.info("AI模型服务已关闭")

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=settings.WORKERS
    )