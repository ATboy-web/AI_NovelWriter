"""
智能体优化模块 - 并行协作、上下文管理
"""

import json
import threading
import time
from typing import Dict, List, Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from .ai_client import AIClient, PromptManager, AIMetrics


class AgentOrchestrator:
    """智能体编排器 - 管理多智能体并行协作"""
    
    def __init__(self, ai_client: AIClient, log_callback: Callable = None):
        self.ai = ai_client
        self.log = log_callback or print
        self.metrics = ai_client.metrics
        self._executor = ThreadPoolExecutor(max_workers=3)
    
    def run_parallel(self, tasks: List[Dict]) -> List[Dict]:
        """并行执行多个AI任务"""
        results = []
        futures = {}
        
        for task in tasks:
            future = self._executor.submit(
                self._execute_task, task
            )
            futures[future] = task.get("name", "unknown")
        
        for future in as_completed(futures):
            task_name = futures[future]
            try:
                result = future.result()
                results.append({"name": task_name, "success": True, "result": result})
            except Exception as e:
                self.log(f"任务 {task_name} 失败: {e}")
                results.append({"name": task_name, "success": False, "error": str(e)})
        
        return results
    
    def _execute_task(self, task: Dict) -> str:
        """执行单个AI任务"""
        system = task.get("system", "")
        prompt = task.get("prompt", "")
        return self.ai.chat(
            [{"role": "user", "content": prompt}],
            system=system,
            max_tokens=task.get("max_tokens", 2048)
        )
    
    def get_metrics(self) -> dict:
        """获取AI性能指标"""
        return self.metrics.get_summary()


class ContextOptimizer:
    """上下文优化器 - 智能管理长文本上下文"""
    
    MAX_CONTEXT_CHARS = 8000
    COMPRESSION_RATIOS = {
        "global_summary": 0.10,
        "volume_summary": 0.15,
        "characters": 0.15,
        "recent_chapters": 0.40,
        "rag_results": 0.10,
        "extra": 0.10,
    }
    
    @classmethod
    def optimize(cls, sections: Dict[str, str], max_chars: int = None) -> str:
        """优化上下文布局"""
        max_chars = max_chars or cls.MAX_CONTEXT_CHARS
        result = []
        used = 0
        
        for section_name, ratio in cls.COMPRESSION_RATIOS.items():
            content = sections.get(section_name, "")
            if not content or used >= max_chars:
                continue
            
            budget = int(max_chars * ratio)
            truncated = cls._truncate(content, budget)
            result.append(truncated)
            used += len(truncated)
        
        return "\n\n".join(result)
    
    @staticmethod
    def _truncate(text: str, budget: int) -> str:
        if len(text) <= budget:
            return text
        return text[:budget] + "\n...(已压缩)"


class PromptOptimizer:
    """提示词优化器"""
    
    @classmethod
    def optimize_prompt(cls, base_prompt: str, context: str, 
                       max_tokens: int = 4000) -> str:
        """优化提示词 - 控制长度和结构"""
        # 估算token数（中文约2字符/token）
        estimated_tokens = len(context) // 2 + len(base_prompt) // 2
        
        if estimated_tokens > max_tokens * 0.8:
            context = context[:max_tokens * 2 - len(base_prompt)]
        
        return f"{base_prompt}\n\n{context}"
