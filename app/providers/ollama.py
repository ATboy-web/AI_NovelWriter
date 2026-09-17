"""Ollama 本地模型适配器。

与 OpenAI 系的差异：
- 路径 `/api/chat`（不是 `/chat/completions`），默认端口 `11434`
- **无鉴权**（本地服务）
- 采样参数放在 `options` 里：`temperature` / `num_predict`（=`max_tokens`）
- 响应是 `{"message": {"content": ...}}`（不是 `choices`）
- usage 字段是 `prompt_eval_count` / `eval_count` ——
  ⚠️ 修 P6：旧实现**完全没有解析**这两个字段，本地模型的 token 消耗既不计入统计、
  也不参与成本计算（本地无计费，但"消耗量"对上下文预算仍有用）。

## 本地模型管理（2026-09-17 补全）

除对话之外，Ollama 还提供"列出已装模型 / 查版本 / 拉取模型"的管理接口。
这些**以前只有 `AIClient.get_ollama_models()` 一处、且全仓零界面调用**，
用户只能手打模型名（填错了直到生成时才失败）。现在按本仓既有风格补齐：

- **路径常量** `OLLAMA_PATHS` 是唯一来源（`registry.py` 的 `chat_path` 也从这里取，
  避免"路径写两处"）；
- **纯解析函数**（`parse_tags` / `parse_version` / `parse_pull_progress`）不碰网络，
  便于单测 —— 与 `providers/balance.py` 的 `BALANCE_PROBES` + 纯解析是同一套做法；
- **HTTP 调用**留给持有传输层的 `AIClient`（`list_local_models` / `check_local_service` /
  `pull_local_model`），这样传输可以注入、单测不碰真实网络。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .base import (
    ChatRequest,
    ChatResult,
    PreparedRequest,
    ProviderAdapter,
    UsageData,
)

__all__ = [
    "OLLAMA_PATHS",
    "LocalModel",
    "OllamaAdapter",
    "parse_pull_progress",
    "parse_tags",
    "parse_version",
]


#: Ollama 各接口路径 —— **唯一来源**。
#: `registry.py` 的 `spac.chat_path` 也从这里取，避免"同一个路径写两处会漂移"。
OLLAMA_PATHS: Dict[str, str] = {
    "chat": "/api/chat",
    "tags": "/api/tags",
    "version": "/api/version",
    "pull": "/api/pull",
    "delete": "/api/delete",
    "show": "/api/show",
}


@dataclass(frozen=True)
class LocalModel:
    """一个本地已安装模型的摘要（来自 `GET /api/tags`）。"""

    name: str
    size: int = 0
    parameter_size: str = ""
    quantization: str = ""
    family: str = ""
    modified_at: str = ""

    @property
    def size_gb(self) -> float:
        """人类可读的体量，用于界面上提示"这个模型装不装得下"。"""
        return round(self.size / (1024**3), 2) if self.size else 0.0

    def label(self) -> str:
        """下拉框里显示的一行文本。"""
        bits = [self.name]
        extra = []
        if self.parameter_size:
            extra.append(self.parameter_size)
        if self.quantization:
            extra.append(self.quantization)
        if self.size_gb:
            extra.append(f"{self.size_gb}GB")
        return f"{bits[0]}（{' / '.join(extra)}）" if extra else bits[0]

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "size": self.size,
            "size_gb": self.size_gb,
            "parameter_size": self.parameter_size,
            "quantization": self.quantization,
            "family": self.family,
            "modified_at": self.modified_at,
        }


def parse_tags(data: Any) -> List[LocalModel]:
    """解析 `GET /api/tags` 的响应。

    真实形状：`{"models": [{"name": "...", "size": 123, "modified_at": "...",
    "details": {"parameter_size": "8.0B", "quantization_level": "Q4_K_M", "family": "qwen2"}}]}`。

    逐层 `isinstance` 校验、任何一层不符就跳过该项 —— 这是给界面下拉框用的，
    宁可少列几个，也不要因为一个畸形条目把整个设置页弄崩。
    """
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return []
    out: List[LocalModel] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("model") or ""
        if not name:
            continue
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        try:
            size = int(item.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        out.append(
            LocalModel(
                name=str(name),
                size=size,
                parameter_size=str(details.get("parameter_size", "") or ""),
                quantization=str(details.get("quantization_level", "") or ""),
                family=str(details.get("family", "") or ""),
                modified_at=str(item.get("modified_at", "") or ""),
            )
        )
    return out


def parse_version(data: Any) -> str:
    """解析 `GET /api/version` → 版本号字符串（形如 `0.3.12`）。"""
    if isinstance(data, dict):
        return str(data.get("version", "") or "")
    return ""


def parse_pull_progress(line: str) -> Optional[Dict[str, Any]]:
    """解析 `POST /api/pull` 的**流式**进度行（每行一个 JSON）。

    真实形状：`{"status": "pulling manifest"}` /
    `{"status": "downloading", "completed": 123, "total": 456}` /
    结束时 `{"status": "success"}`。

    返回 `None` 表示这一行不是合法 JSON（拉取过程中可能出现空行/心跳）。
    """
    if not line or not line.strip():
        return None
    try:
        obj = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None

    completed = obj.get("completed")
    total = obj.get("total")
    percent = None
    try:
        if completed is not None and total:
            percent = round(float(completed) / float(total) * 100, 1)
    except (TypeError, ValueError, ZeroDivisionError):
        percent = None

    return {
        "status": str(obj.get("status", "") or ""),
        "completed": completed,
        "total": total,
        "percent": percent,
        "error": str(obj.get("error", "") or ""),
        "done": str(obj.get("status", "")) == "success",
    }


class OllamaAdapter(ProviderAdapter):
    """Ollama `/api/chat`。"""

    label = "Ollama"

    def build_request(self, req: ChatRequest) -> PreparedRequest:
        body = {
            "model": req.model,
            "messages": req.openai_messages(),
            "stream": bool(req.stream),
            "options": {
                "temperature": req.temperature,
                "num_predict": req.max_tokens,
            },
        }
        if req.extra:
            body.update(req.extra)
        return PreparedRequest(
            path=self.spec.chat_path,
            json_body=body,
            headers=dict(self.spec.default_headers),
        )

    def parse_response(self, data: dict) -> ChatResult:
        message = data.get("message") or {}
        if not isinstance(message, dict):
            message = {}
        return ChatResult(
            text=message.get("content", "") or "",
            reasoning=message.get("thinking", "") or "",
            usage=self._parse_usage(data),
            finish_reason=data.get("done_reason", "") or "",
            raw=data,
        )

    def _parse_usage(self, data: dict) -> UsageData:
        """Ollama 把计数放在**响应顶层**，不在 `usage` 对象里。"""
        prompt = data.get("prompt_eval_count", 0) or 0
        completion = data.get("eval_count", 0) or 0
        return UsageData(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        )

    def parse_stream_chunk(self, line: str):
        """Ollama 流式是**裸 JSON 行**（不带 `data: ` 前缀）。

        与 OpenAI / Anthropic 的 SSE 都不同 —— 这是"各家实现独立"的又一个例子。
        """
        if not line:
            return None
        try:
            chunk = json.loads(line)
        except (ValueError, TypeError):
            return None
        if not isinstance(chunk, dict):
            return None

        from .base import StreamDelta

        message = chunk.get("message") or {}
        delta = StreamDelta(
            text=(message.get("content", "") if isinstance(message, dict) else "") or "",
            done=bool(chunk.get("done")),
        )
        if chunk.get("done"):
            delta.usage = self._parse_usage(chunk)
        return delta
