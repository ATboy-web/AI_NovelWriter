"""
智能体优化模块 - 并行协作、上下文管理
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List

from .ai_client import AIClient
from .token_estimator import estimate_tokens, truncate_to_tokens


class AgentOrchestrator:
    """智能体编排器 - 管理多智能体并行协作"""

    def __init__(self, ai_client: AIClient, log_callback: Callable = None):
        self.ai = ai_client
        self.log = log_callback or print
        self.metrics = ai_client.metrics
        self._executor = ThreadPoolExecutor(max_workers=3)

    def shutdown(self, wait: bool = True):
        """关闭线程池"""
        if self._executor:
            self._executor.shutdown(wait=wait)

    def __del__(self):
        """析构时关闭线程池"""
        try:
            self.shutdown(wait=False)
        except Exception:
            pass

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
        # 智能截断：尽量在段落边界截断
        truncated = text[:budget]
        # 尝试在最后一个段落边界截断
        last_para = max(truncated.rfind('\n\n'), truncated.rfind('。'), truncated.rfind('！'), truncated.rfind('？'))
        if last_para > budget * 0.8:  # 如果找到的边界在80%之后，就用这个边界
            truncated = truncated[:last_para + 1]
        return truncated + "\n...(已压缩)"


class PromptOptimizer:
    """提示词优化器"""

    @classmethod
    def optimize_prompt(cls, base_prompt: str, context: str,
                       max_tokens: int = 4000) -> str:
        """优化提示词 - 控制长度和结构

        v3 §3.5(3)：这里原来是 `len(x) // 2`（注释写"中文约 2 字符/token"）。
        该口径对中文**低估约 3 倍**，而且末尾那句 `context[:max_tokens * 2 - len(base_prompt)]`
        又混用了字符与 token 两种单位（`* 2` 是在延续 `// 2` 的错误换算）。
        现在统一走 `token_estimator`：估算用真实比例，截断按估算反推字符数。
        """
        budget = max_tokens * 0.8
        if estimate_tokens(base_prompt) + estimate_tokens(context) > budget:
            allowed = max(0.0, budget - estimate_tokens(base_prompt))
            context = truncate_to_tokens(context, allowed)

        return f"{base_prompt}\n\n{context}"
