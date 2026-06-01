"""
推理引擎
负责实际调用模型进行文本生成
"""

import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
import time

from .config import settings
from .model_manager import ModelManager

class InferenceEngine:
    """推理引擎"""
    
    def __init__(self, model_manager: ModelManager):
        self.model_manager = model_manager
        self._request_count = 0
        self._total_tokens = 0
        self._start_time = datetime.now()
    
    async def generate_local(
        self,
        prompt: str,
        model_name: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        top_p: float = 0.9
    ) -> Dict[str, Any]:
        """使用本地模型生成文本"""
        try:
            # 获取本地模型
            local_model = self.model_manager.get_local_model()
            if not local_model:
                # 尝试加载模型
                await self.model_manager.load_model("local", model_name)
                local_model = self.model_manager.get_local_model()
            
            if not local_model:
                raise ValueError("本地模型未加载")
            
            # 记录开始时间
            start_time = time.time()
            
            # 调用模型生成
            response = local_model.create_completion(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                repeat_penalty=1.1,
                stop=["\n\n", "User:", "Assistant:"]
            )
            
            # 计算生成时间
            generation_time = time.time() - start_time
            
            # 提取生成内容
            content = response["choices"][0]["text"]
            tokens_used = response["usage"]["total_tokens"]
            
            # 更新统计
            self._request_count += 1
            self._total_tokens += tokens_used
            
            # 更新模型使用统计
            await self.model_manager.update_model_usage("local", model_name)
            
            return {
                "content": content.strip(),
                "model_used": f"local_{model_name or 'default'}",
                "tokens_used": tokens_used,
                "generation_time": generation_time,
                "metadata": {
                    "temperature": temperature,
                    "top_p": top_p,
                    "max_tokens": max_tokens
                }
            }
            
        except Exception as e:
            raise ValueError(f"本地模型生成失败: {e}")
    
    async def generate_openai(
        self,
        prompt: str,
        model_name: str = "gpt-4",
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """使用OpenAI模型生成文本"""
        try:
            # 获取OpenAI客户端
            openai_client = self.model_manager.get_openai_client()
            if not openai_client:
                raise ValueError("OpenAI客户端未初始化")
            
            # 记录开始时间
            start_time = time.time()
            
            # 调用OpenAI API
            response = await openai_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "你是一位专业的小说作家，擅长创作各种类型的小说。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=0.9
            )
            
            # 计算生成时间
            generation_time = time.time() - start_time
            
            # 提取生成内容
            content = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
            
            # 更新统计
            self._request_count += 1
            self._total_tokens += tokens_used
            
            return {
                "content": content.strip(),
                "model_used": f"openai_{model_name}",
                "tokens_used": tokens_used,
                "generation_time": generation_time,
                "metadata": {
                    "model": model_name,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            }
            
        except Exception as e:
            raise ValueError(f"OpenAI生成失败: {e}")
    
    async def generate_claude(
        self,
        prompt: str,
        model_name: str = "claude-3-sonnet-20240229",
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """使用Claude模型生成文本"""
        try:
            # 获取Claude客户端
            claude_client = self.model_manager.get_claude_client()
            if not claude_client:
                raise ValueError("Claude客户端未初始化")
            
            # 记录开始时间
            start_time = time.time()
            
            # 调用Claude API
            response = await claude_client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # 计算生成时间
            generation_time = time.time() - start_time
            
            # 提取生成内容
            content = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens
            
            # 更新统计
            self._request_count += 1
            self._total_tokens += tokens_used
            
            return {
                "content": content.strip(),
                "model_used": f"claude_{model_name}",
                "tokens_used": tokens_used,
                "generation_time": generation_time,
                "metadata": {
                    "model": model_name,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            }
            
        except Exception as e:
            raise ValueError(f"Claude生成失败: {e}")
    
    async def generate_with_fallback(
        self,
        prompt: str,
        preferred_model: str = "local",
        model_name: Optional[str] = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        top_p: float = 0.9
    ) -> Dict[str, Any]:
        """带降级的生成方法"""
        models_to_try = []
        
        # 根据首选模型确定尝试顺序
        if preferred_model == "local":
            models_to_try = ["local", "openai", "claude"]
        elif preferred_model == "openai":
            models_to_try = ["openai", "claude", "local"]
        elif preferred_model == "claude":
            models_to_try = ["claude", "openai", "local"]
        else:
            models_to_try = ["local", "openai", "claude"]
        
        last_error = None
        
        # 依次尝试各个模型
        for model_type in models_to_try:
            try:
                if model_type == "local":
                    return await self.generate_local(
                        prompt, model_name, max_tokens, temperature, top_p
                    )
                elif model_type == "openai":
                    return await self.generate_openai(
                        prompt, model_name or "gpt-4", max_tokens, temperature
                    )
                elif model_type == "claude":
                    return await self.generate_claude(
                        prompt, model_name or "claude-3-sonnet-20240229", max_tokens, temperature
                    )
            except Exception as e:
                last_error = e
                print(f"模型 {model_type} 生成失败: {e}")
                continue
        
        # 所有模型都失败
        raise ValueError(f"所有模型生成失败，最后错误: {last_error}")
    
    async def generate_novel_chapter(
        self,
        novel_type: str,
        chapter_title: str,
        chapter_outline: str,
        previous_content: str = "",
        model_type: str = "local",
        model_name: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.8
    ) -> Dict[str, Any]:
        """生成小说章节"""
        try:
            # 构建章节生成提示词
            prompt = self._build_chapter_prompt(
                novel_type=novel_type,
                chapter_title=chapter_title,
                chapter_outline=chapter_outline,
                previous_content=previous_content
            )
            
            # 生成内容
            result = await self.generate_with_fallback(
                prompt=prompt,
                preferred_model=model_type,
                model_name=model_name,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            # 后处理生成内容
            processed_content = self._post_process_chapter(
                content=result["content"],
                novel_type=novel_type,
                chapter_title=chapter_title
            )
            
            result["content"] = processed_content
            result["metadata"]["chapter_title"] = chapter_title
            result["metadata"]["novel_type"] = novel_type
            
            return result
            
        except Exception as e:
            raise ValueError(f"小说章节生成失败: {e}")
    
    def _build_chapter_prompt(
        self,
        novel_type: str,
        chapter_title: str,
        chapter_outline: str,
        previous_content: str
    ) -> str:
        """构建章节生成提示词"""
        # 小说类型描述
        type_descriptions = {
            "scifi": "科幻小说，具有前瞻性的科技设定和世界观",
            "mystery": "悬疑推理小说，逻辑严密、情节曲折",
            "romance": "言情小说，情感细腻、人物关系复杂",
            "fantasy": "奇幻小说，丰富的魔法和世界观设定",
            "urban": "都市小说，贴近现实、人物鲜明"
        }
        
        type_desc = type_descriptions.get(novel_type, "小说")
        
        # 构建提示词
        prompt = f"""你是一位专业的{type_desc}作家。

请根据以下信息创作小说章节：

章节标题：{chapter_title}
章节大纲：{chapter_outline}

"""
        
        # 添加前文内容（如果有）
        if previous_content:
            prompt += f"""前文内容：
{previous_content[-2000:]}  # 只取最后2000字符

"""
        
        prompt += """请创作这个章节的内容，要求：
1. 保持与前文的连贯性
2. 符合小说类型的特点
3. 情节生动，人物鲜明
4. 语言流畅，可读性强
5. 字数适中，不要太短或太长

请直接开始创作章节内容："""
        
        return prompt
    
    def _post_process_chapter(
        self,
        content: str,
        novel_type: str,
        chapter_title: str
    ) -> str:
        """后处理章节内容"""
        # 基本清理
        content = content.strip()
        
        # 移除可能的AI生成痕迹
        ai_phrases = [
            "作为一位AI", "我是AI", "作为语言模型", "我无法",
            "根据您的要求", "以下是", "这是", "我将"
        ]
        
        for phrase in ai_phrases:
            if content.startswith(phrase):
                # 找到第一个句号后的内容
                first_period = content.find("。")
                if first_period != -1:
                    content = content[first_period + 1:].strip()
        
        # 确保章节标题存在
        if not content.startswith(f"第") and not content.startswith(chapter_title):
            content = f"{chapter_title}\n\n{content}"
        
        return content
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取推理统计信息"""
        uptime = (datetime.now() - self._start_time).total_seconds()
        
        return {
            "total_requests": self._request_count,
            "total_tokens": self._total_tokens,
            "uptime_seconds": uptime,
            "requests_per_minute": (self._request_count / uptime * 60) if uptime > 0 else 0,
            "tokens_per_request": (self._total_tokens / self._request_count) if self._request_count > 0 else 0,
            "model_status": {
                "local_loaded": self.model_manager.get_local_model() is not None,
                "openai_available": self.model_manager.get_openai_client() is not None,
                "claude_available": self.model_manager.get_claude_client() is not None
            }
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 检查模型状态
            local_model = self.model_manager.get_local_model()
            openai_client = self.model_manager.get_openai_client()
            claude_client = self.model_manager.get_claude_client()
            
            # 测试本地模型
            local_status = "unavailable"
            if local_model:
                try:
                    # 简单测试
                    test_response = local_model.create_completion(
                        prompt="测试",
                        max_tokens=5,
                        temperature=0.1
                    )
                    local_status = "healthy"
                except:
                    local_status = "error"
            
            # 测试云端模型
            openai_status = "unavailable"
            if openai_client:
                try:
                    # 简单测试
                    test_response = await openai_client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": "test"}],
                        max_tokens=5
                    )
                    openai_status = "healthy"
                except:
                    openai_status = "error"
            
            claude_status = "unavailable"
            if claude_client:
                try:
                    # 简单测试
                    test_response = await claude_client.messages.create(
                        model="claude-3-haiku-20240307",
                        max_tokens=5,
                        messages=[{"role": "user", "content": "test"}]
                    )
                    claude_status = "healthy"
                except:
                    claude_status = "error"
            
            return {
                "status": "healthy",
                "models": {
                    "local": local_status,
                    "openai": openai_status,
                    "claude": claude_status
                },
                "statistics": await self.get_statistics()
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }