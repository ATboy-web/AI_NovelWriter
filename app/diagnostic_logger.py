"""
AI 诊断日志系统 - JSON 结构化日志，供 AI/开发者分析
与用户日志（简单文本）完全独立，记录完整调用链、错误栈、性能数据
"""

import json
import os
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# ── 脱敏（L-6）────────────────────────────────────────

#: 字段名里出现这些片段就整值替换成 `***`（大小写不敏感）。
#: 判据刻意保守：宁可多盖一个无关键，也不要漏掉一个凭据。
_SENSITIVE_MARKERS = (
    "API_KEY",
    "APIKEY",
    "ACCESS_TOKEN",
    "REFRESH_TOKEN",
    "AUTH_TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "COOKIE",
    "BEARER",
)

#: 文本里的"键=值"凭据（URL 查询串最常见）。
_INLINE_SECRET_RE = re.compile(
    r"(?i)(access_token|refresh_token|api_key|apikey|token|password|passwd|secret|sessionid)=([^&\s\"']+)"
)
#: `Authorization: Bearer xxx` / 裸 Bearer token
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/]{12,}=*")
#: 常见云厂商/服务商密钥前缀（OpenAI/Anthropic/GitHub/Slack）
_KEY_PREFIX_RE = re.compile(r"\b(sk-[A-Za-z0-9\-_]{16,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9\-]{10,})")


def is_sensitive_key(key: Any) -> bool:
    """字段名是否像凭据。"""
    upper = str(key).upper()
    return any(marker in upper for marker in _SENSITIVE_MARKERS)


def redact_text(text: str) -> str:
    """把文本里的凭据替换成 `***`。幂等。

    刻意**不做异常兜底**：入参在所有调用点都已是 `str`
    （见 `_truncate_data` 与 `str(error)`），出现非字符串属于编程错误，
    静默吞掉只会让"某类日志永远不被脱敏"这件事无人察觉。
    """
    if not text:
        return text
    text = _INLINE_SECRET_RE.sub(r"\1=***", text)
    text = _BEARER_RE.sub(r"\1***", text)
    text = _KEY_PREFIX_RE.sub("***", text)
    return text


# ── 单例 ──────────────────────────────────────────────
_logger_instance: Optional["DiagnosticLogger"] = None
_lock = threading.Lock()

#: 日志目录的环境变量覆盖名。
#: 存在的理由：`__init__` 原本**硬编码** `~/.ai_novel_writer/diagnostic_logs`，
#: 而 `ai_client` / `generation_ui` / `novel_agent` 都在**模块级**调用 `get_logger()` 建单例，
#: 于是测试进程与真实使用**写进同一个文件**，真实数据被淹没（实测：连续 3 天
#: `CHAPTER` 事件数为 0，而 `API_CALL` 有 3126 条全是同一份测试指纹）。
#: 有了它，`tests/conftest.py` 可以在任何 `app.*` 模块被导入之前把目录指向临时目录。
DIAGNOSTIC_LOG_DIR_ENV = "AI_NOVEL_DIAGNOSTIC_DIR"


def resolve_log_dir(explicit: Optional[Path] = None) -> Path:
    """决定诊断日志目录：显式参数 > 环境变量 > 默认 `~/.ai_novel_writer/diagnostic_logs`。

    抽成函数是为了让"目录从哪来"只有一处实现 —— 面板导出、性能报告落盘都要用同一个答案。
    """
    if explicit is not None:
        return Path(explicit)
    from_env = os.environ.get(DIAGNOSTIC_LOG_DIR_ENV)
    if from_env:
        return Path(from_env)
    return Path.home() / ".ai_novel_writer" / "diagnostic_logs"


class DiagnosticLogger:
    """结构化诊断日志记录器

    输出格式: 每行一个 JSON 对象（JSON Lines）
    记录内容: 完整请求/响应、错误栈、函数调用链、性能计时、系统状态
    """

    # 日志轮转: 单文件最大 5MB，保留最近 5 个文件
    MAX_FILE_SIZE = 5 * 1024 * 1024
    MAX_BACKUP_FILES = 5

    def __init__(self, log_dir: Path = None):
        self.log_dir = resolve_log_dir(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_file = self._get_log_file()
        self._write_lock = threading.Lock()
        self._sequence = 0
        self._session_id = self._generate_session_id()

        # 启动日志
        self.log(
            "SYSTEM",
            "startup",
            {
                "python_version": sys.version,
                "platform": sys.platform,
                "pid": os.getpid(),
                "session_id": self._session_id,
            },
        )

    def _generate_session_id(self) -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + str(os.getpid())

    def _get_log_file(self) -> Path:
        """获取当前日志文件，自动轮转"""
        today = datetime.now().strftime("%Y-%m-%d")
        base = self.log_dir / f"diagnostic-{today}.jsonl"

        # 如果文件超过限制，轮转
        if base.exists() and base.stat().st_size > self.MAX_FILE_SIZE:
            for i in range(self.MAX_BACKUP_FILES - 1, 0, -1):
                old = self.log_dir / f"diagnostic-{today}.{i}.jsonl"
                new = self.log_dir / f"diagnostic-{today}.{i + 1}.jsonl"
                if old.exists():
                    if new.exists():
                        new.unlink()
                    old.rename(new)
            backup = self.log_dir / f"diagnostic-{today}.1.jsonl"
            base.rename(backup)

        return base

    def log(
        self, category: str, event: str, data: Dict[str, Any] = None, error: Exception = None, duration_ms: float = None
    ):
        """记录一条诊断日志

        Args:
            category: 类别 (API_CALL, FUNC_ENTRY, FUNC_EXIT, ERROR, SYSTEM, CHAPTER)
            event: 事件名称
            data: 附加数据
            error: 异常对象
            duration_ms: 执行耗时(毫秒)
        """
        with self._write_lock:
            self._sequence += 1

            entry = {
                "seq": self._sequence,
                "ts": datetime.now(timezone.utc).isoformat(),
                "session": self._session_id,
                "thread": threading.current_thread().name,
                "category": category,
                "event": event,
            }

            if data:
                # 限制数据大小，避免撑爆日志
                entry["data"] = self._truncate_data(data)

            if error:
                entry["error"] = {
                    "type": type(error).__name__,
                    # L-6：异常文本常带完整 URL（含 access_token=…）或 Bearer 头
                    "message": redact_text(str(error))[:500],
                    "traceback": redact_text(traceback.format_exc())[-2000:],  # 最后2000字符（核心栈）
                }

            if duration_ms is not None:
                entry["duration_ms"] = round(duration_ms, 2)

            try:
                # 写入前检查轮转
                if self._current_file.exists() and self._current_file.stat().st_size > self.MAX_FILE_SIZE:
                    self._current_file = self._get_log_file()

                with open(self._current_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    f.flush()
            except Exception:
                pass  # 日志写入失败不能影响主流程

    def _truncate_data(self, data: Any, max_depth: int = 3, max_str: int = 2000) -> Any:
        """截断大数据，防止日志爆炸；**同时做兜底脱敏**（L-6）。

        当前调用方都只记元数据（provider / model / 计数），但"当前没泄露"
        不等于"以后不会"：任何人往 `data` 里塞一个 `api_key` 或带查询串的 URL，
        就会把长期凭据写进可被上传/打包的 JSONL。这里按 key 名与文本模式兜底。
        """
        if isinstance(data, str):
            text = redact_text(data)
            if len(text) > max_str:
                return text[:max_str] + f"...[截断,原长{len(text)}]"
            return text
        elif isinstance(data, dict):
            if max_depth <= 0:
                return {"_truncated": True, "_keys": list(data.keys())[:20]}
            result = {}
            for k, v in list(data.items())[:50]:
                if is_sensitive_key(k):
                    result[k] = "***"
                else:
                    result[k] = self._truncate_data(v, max_depth - 1, max_str)
            return result
        elif isinstance(data, list):
            if max_depth <= 0:
                return [f"...[{len(data)}项]"]
            return [self._truncate_data(v, max_depth - 1, max_str) for v in data[:30]]
        elif isinstance(data, (int, float, bool, type(None))):
            return data
        else:
            return redact_text(str(data))[:max_str]

    # ── 便捷方法 ─────────────────────────────────────

    def api_call(
        self,
        provider: str,
        endpoint: str,
        request_data: dict,
        response_data: dict = None,
        error: Exception = None,
        duration_ms: float = None,
    ):
        """记录 AI API 调用"""
        # 兼容两种response_data格式
        resp_info = None
        if response_data:
            if "choices" in response_data:
                # OpenAI格式
                resp_info = {
                    "status": "success",
                    "choices_count": len(response_data.get("choices", [])),
                    "usage": response_data.get("usage", {}),
                    "content_preview": str(response_data.get("choices", [{}])[0].get("message", {}).get("content", ""))[
                        :300
                    ]
                    if response_data.get("choices")
                    else "",
                }
            else:
                # 简化格式 (from ai_client.py)
                resp_info = {
                    "status": response_data.get("status", "success"),
                    "result_len": response_data.get("result_len", 0),
                    "content_preview": str(response_data.get("content_preview", ""))[:300],
                }

        self.log(
            "API_CALL",
            f"{provider}::{endpoint}",
            {
                "provider": provider,
                "endpoint": endpoint,
                "request": {
                    "model": request_data.get("model", "unknown"),
                    "messages_count": len(request_data.get("messages", []))
                    if "messages" in request_data
                    else request_data.get("messages_count", 0),
                    "max_tokens": request_data.get("max_tokens", 0),
                },
                "response": resp_info,
            },
            error=error,
            duration_ms=duration_ms,
        )

    def func_entry(self, func_name: str, params: dict = None):
        """记录函数入口"""
        safe_params = {}
        if params:
            for k, v in params.items():
                if k in ("content", "text", "prompt", "system_prompt"):
                    safe_params[k] = f"[{len(str(v))} chars]"
                elif isinstance(v, (int, float, bool, str, type(None))):
                    safe_params[k] = v
                else:
                    safe_params[k] = type(v).__name__
        self.log("FUNC_ENTRY", func_name, {"params": safe_params})

    def func_exit(self, func_name: str, result_summary: str = None, duration_ms: float = None):
        """记录函数退出"""
        self.log("FUNC_EXIT", func_name, {"result": result_summary} if result_summary else {}, duration_ms=duration_ms)

    def chapter_event(self, chapter_num: int, event: str, data: dict = None, duration_ms: float = None):
        """记录章节相关事件

        `duration_ms` 用于**段级耗时归因**：单章生成会发 3–9 次网络往返，
        只有把"这一段花了多久"落到同一行，才可能回答"这一章为什么慢"。
        """
        self.log(
            "CHAPTER",
            f"ch{chapter_num:04d}/{event}",
            {"chapter": chapter_num, **(data or {})},
            duration_ms=duration_ms,
        )

    def character_event(self, char_name: str, event: str, data: dict = None):
        """记录角色相关事件"""
        self.log("CHARACTER", f"{char_name}/{event}", {"character": char_name, **(data or {})})

    def memory_event(self, event: str, data: dict = None):
        """记录记忆系统事件"""
        self.log("MEMORY", event, data or {})

    def generation_event(self, genre: str, chapter_num: int, event: str, data: dict = None, duration_ms: float = None):
        """记录生成事件"""
        self.log(
            "GENERATION",
            f"{genre}/ch{chapter_num:04d}/{event}",
            {"genre": genre, "chapter": chapter_num, **(data or {})},
            duration_ms=duration_ms,
        )

    # ── 导出 ─────────────────────────────────────────

    def export_recent(self, count: int = 100) -> str:
        """导出最近 N 条日志为可读文本（用于导出给 AI 分析）"""
        try:
            # 用Python原生方式读取最后N行（跨平台兼容）
            lines = []
            with open(self._current_file, "r", encoding="utf-8") as f:
                for line in f:
                    lines.append(line.strip())
            lines = lines[-count:]  # 取最后count行
        except Exception:
            return "无法读取诊断日志"

        report = []
        report.append("═" * 60)
        report.append("AI小说创作工坊 诊断日志导出")
        report.append(f"会话: {self._session_id}")
        report.append(f"导出时间: {datetime.now().isoformat()}")
        report.append(f"记录数: {len(lines)} 条 (最近)")
        report.append("═" * 60)

        error_count = 0
        api_count = 0

        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            cat = entry.get("category", "?")
            evt = entry.get("event", "?")
            ts = entry.get("ts", "")[11:23]  # 只取时间部分

            if cat == "ERROR" or entry.get("error"):
                error_count += 1
                report.append(f"\n❌ [{ts}] {cat}/{evt}")
                if entry.get("error"):
                    report.append(f"   错误: {entry['error'].get('message', '')}")
                    tb = entry["error"].get("traceback", "")
                    if tb:
                        for line in tb.split("\n")[-5:]:  # 最后5行关键栈
                            if line.strip():
                                report.append(f"   {line.strip()}")
            elif cat == "API_CALL":
                api_count += 1
                d = entry.get("data", {})
                req = d.get("request", {})
                res = d.get("response", {})
                dur = entry.get("duration_ms", 0)
                report.append(f"\n🔗 [{ts}] API {evt} ({dur:.0f}ms)")
                report.append(f"   模型: {req.get('model', '?')} | 消息数: {req.get('messages_count', 0)}")
                if res:
                    usage = res.get("usage", {})
                    report.append(f"   用量: {usage} | 回复: {res.get('content_preview', '')[:100]}")
                if entry.get("error"):
                    report.append(f"   失败: {entry['error'].get('message', '')[:100]}")

        report.append("\n" + "═" * 60)
        report.append(f"统计: {len(lines)}条日志 | {api_count}次API | {error_count}个错误")
        report.append("═" * 60)

        return "\n".join(report)

    def get_log_dir(self) -> Path:
        return self.log_dir


def get_logger(log_dir: Path = None) -> DiagnosticLogger:
    """获取诊断日志单例

    注意：单例**忽略后续传入的 `log_dir`**（一旦建好就固定）。因此切换日志目录
    必须走 `reset_logger()`，这也是测试隔离与"面板导出"能拿到正确目录的前提。
    """
    global _logger_instance
    with _lock:
        if _logger_instance is None:
            _logger_instance = DiagnosticLogger(log_dir)
        return _logger_instance


def reset_logger() -> None:
    """丢弃单例，使下一次 `get_logger()` 按当前环境重新决定目录。

    仅给测试隔离（`tests/conftest.py`）与诊断工具的目录切换用；
    生产代码不要调用 —— 中途换目录会让一次会话的日志分裂成两个文件。
    """
    global _logger_instance
    with _lock:
        _logger_instance = None


# ── 装饰器 ──────────────────────────────────────────


def trace_api(func):
    """装饰器: 自动记录 API 调用"""
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_logger()
        func_name = func.__name__

        # 从 self 提取信息
        provider = "unknown"
        if args and hasattr(args[0], "__class__"):
            provider = args[0].__class__.__name__

        t0 = time.time()
        try:
            result = func(*args, **kwargs)
            duration_ms = (time.time() - t0) * 1000

            logger.api_call(
                provider=provider,
                endpoint=func_name,
                request_data={"kwargs": {k: str(v)[:200] for k, v in kwargs.items()}},
                response_data={"result_type": type(result).__name__, "result_len": len(str(result)) if result else 0},
                duration_ms=duration_ms,
            )
            return result
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            logger.api_call(
                provider=provider,
                endpoint=func_name,
                request_data={"kwargs": {k: str(v)[:200] for k, v in kwargs.items()}},
                error=e,
                duration_ms=duration_ms,
            )
            raise

    return wrapper
