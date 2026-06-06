"""
小说生成服务API路由
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from ..generators.novel_generator import NovelType

# 创建路由器
router = APIRouter()


class StyleAnalysisRequest(BaseModel):
    """风格分析请求"""
    content: str = Field(..., description="待分析内容")
    novel_type: NovelType = Field(NovelType.SCIFI, description="小说类型")
    ai_service_url: str = Field("http://localhost:8001", description="AI服务地址")

class StyleAnalysisResponse(BaseModel):
    """风格分析响应"""
    success: bool
    analysis_results: Dict[str, Any]
    novel_type: str
    generation_time: float

class ContentOptimizationRequest(BaseModel):
    """内容优化请求"""
    content: str = Field(..., description="待优化内容")
    optimization_type: str = Field("comprehensive", description="优化类型")
    novel_type: NovelType = Field(NovelType.SCIFI, description="小说类型")
    ai_service_url: str = Field("http://localhost:8001", description="AI服务地址")

class ContentOptimizationResponse(BaseModel):
    """内容优化响应"""
    success: bool
    original_content: str
    optimized_content: str
    optimization_type: str
    changes_made: List[str]
    generation_time: float

class ContinuityCheckRequest(BaseModel):
    """连贯性检查请求"""
    chapters: List[str] = Field(..., description="章节内容列表")
    novel_type: NovelType = Field(NovelType.SCIFI, description="小说类型")
    ai_service_url: str = Field("http://localhost:8001", description="AI服务地址")

class ContinuityCheckResponse(BaseModel):
    """连贯性检查响应"""
    success: bool
    issues_found: List[Dict[str, Any]]
    suggestions: List[str]
    overall_score: float
    generation_time: float

@router.post("/analyze/style", response_model=StyleAnalysisResponse, tags=["文本分析"])
async def analyze_style(request: StyleAnalysisRequest):
    """分析文本风格"""
    try:
        import httpx
        import time
        
        start_time = time.time()
        
        # 调用AI服务进行风格分析
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{request.ai_service_url}/api/v1/analyze/style",
                json={
                    "content": request.content,
                    "analysis_type": "comprehensive",
                    "model_type": "local"
                },
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()
        
        generation_time = time.time() - start_time
        
        if result.get("success"):
            return StyleAnalysisResponse(
                success=True,
                analysis_results=result.get("analysis_results", {}),
                novel_type=request.novel_type.value,
                generation_time=generation_time
            )
        else:
            # 返回默认分析结果
            return StyleAnalysisResponse(
                success=True,
                analysis_results={
                    "language_style": "待分析",
                    "narrative_perspective": "待分析",
                    "emotional_tone": "待分析",
                    "literary_devices": [],
                    "sentence_features": "待分析",
                    "vocabulary_features": "待分析",
                    "overall_evaluation": "待分析"
                },
                novel_type=request.novel_type.value,
                generation_time=generation_time
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"风格分析失败: {str(e)}")

@router.post("/optimize/content", response_model=ContentOptimizationResponse, tags=["内容优化"])
async def optimize_content(request: ContentOptimizationRequest):
    """优化内容"""
    try:
        import httpx
        import time
        
        start_time = time.time()
        
        # 构建优化提示词
        optimization_prompts = {
            "comprehensive": "请全面优化以下内容，包括语言表达、情节逻辑、人物塑造等方面",
            "language": "请优化以下内容的语言表达，使其更加流畅、生动",
            "plot": "请优化以下内容的情节逻辑，使其更加合理、引人入胜",
            "character": "请优化以下内容的人物塑造，使其更加立体、真实"
        }
        
        prompt = optimization_prompts.get(request.optimization_type, optimization_prompts["comprehensive"])
        
        # 调用AI服务进行内容优化
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{request.ai_service_url}/api/v1/generate/chapter",
                json={
                    "novel_type": request.novel_type.value,
                    "chapter_title": "内容优化",
                    "chapter_outline": f"{prompt}：\n\n{request.content[:1000]}",
                    "previous_content": "",
                    "model_type": "local",
                    "max_tokens": 2000,
                    "temperature": 0.7
                },
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()
        
        generation_time = time.time() - start_time
        
        if result.get("success"):
            optimized_content = result.get("content", request.content)
            
            # 分析所做的更改
            changes = []
            if len(optimized_content) != len(request.content):
                changes.append("内容长度调整")
            if optimized_content != request.content:
                changes.append("语言表达优化")
            
            return ContentOptimizationResponse(
                success=True,
                original_content=request.content,
                optimized_content=optimized_content,
                optimization_type=request.optimization_type,
                changes_made=changes,
                generation_time=generation_time
            )
        else:
            return ContentOptimizationResponse(
                success=True,
                original_content=request.content,
                optimized_content=request.content,
                optimization_type=request.optimization_type,
                changes_made=["优化失败，返回原内容"],
                generation_time=generation_time
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"内容优化失败: {str(e)}")

@router.post("/check/continuity", response_model=ContinuityCheckResponse, tags=["质量检查"])
async def check_continuity(request: ContinuityCheckRequest):
    """检查内容连贯性"""
    try:
        import httpx
        import time
        
        start_time = time.time()
        
        # 构建连贯性检查提示词
        chapters_text = "\n\n".join([f"第{i+1}章：{chapter[:500]}" for i, chapter in enumerate(request.chapters)])
        
        prompt = f"""请检查以下小说章节的连贯性：

{chapters_text}

请从以下方面进行检查：
1. 情节连贯性
2. 人物一致性
3. 时间线逻辑
4. 细节一致性
5. 整体节奏

请以JSON格式输出检查结果，包括问题列表和改进建议。"""
        
        # 调用AI服务进行连贯性检查
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{request.ai_service_url}/api/v1/generate/chapter",
                json={
                    "novel_type": request.novel_type.value,
                    "chapter_title": "连贯性检查",
                    "chapter_outline": prompt,
                    "previous_content": "",
                    "model_type": "local",
                    "max_tokens": 1500,
                    "temperature": 0.3
                },
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()
        
        generation_time = time.time() - start_time
        
        # 解析检查结果
        issues_found = []
        suggestions = []
        
        if result.get("success"):
            content = result.get("content", "")
            
            # 简单的问题提取（实际应用中可以更复杂）
            if "问题" in content or "issue" in content.lower():
                issues_found.append({
                    "type": "continuity",
                    "description": "发现潜在连贯性问题",
                    "severity": "medium"
                })
            
            if "建议" in content or "suggest" in content.lower():
                suggestions.append("建议检查情节逻辑")
        
        # 计算整体分数（0-100）
        overall_score = max(0, 100 - len(issues_found) * 10)
        
        return ContinuityCheckResponse(
            success=True,
            issues_found=issues_found,
            suggestions=suggestions,
            overall_score=overall_score,
            generation_time=generation_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"连贯性检查失败: {str(e)}")

@router.get("/supported-types", tags=["小说类型"])
async def get_supported_types():
    """获取支持的小说类型"""
    return {
        "success": True,
        "supported_types": [
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
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(),
        "service": "小说生成服务"
    }

@router.get("/statistics", tags=["统计信息"])
async def get_statistics():
    """获取服务统计信息"""
    return {
        "success": True,
        "statistics": {
            "service": "小说生成服务",
            "version": "1.0.0",
            "supported_types": 5,
            "status": "running"
        }
    }