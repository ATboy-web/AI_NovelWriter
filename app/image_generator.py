"""文生图模块 — 支持 ComfyUI 与 Stable Diffusion WebUI（SD API）。

## 设计（与 `app/providers/` 保持同一风格）

- **后端注册表** `IMAGE_BACKENDS`：新增一个后端只改这里一处，
  与 `app/providers/registry.py` 的 `DEFAULT_SPECS`、`app/providers/balance.py` 的
  `BALANCE_PROBES` 是同一个思路 —— 避免"能力清单散落在多处"。
- **纯解析函数**（`parse_comfyui_models` / `parse_sdapi_models` / `parse_health`）：
  不碰网络，便于单测；HTTP 留给 `ImageGenerator` 自己（本模块一直是自持 httpx 的）。
- **结构化结果** `ImageGenResult`：仿 `BalanceResult` 的形状
  （`ok` / `message` / `as_dict()`），让界面既能显示成功也能显示**失败原因**。

## 为什么补这些（2026-09-17 审计）

原实现只有 `generate()` 一个出口，而且：
1. **全仓零调用** —— 实例建了、`is_configured()` 只用来拼状态栏文案，
   没有任何界面路径能真的生成一张图 ⇒ 整组配置（`img_provider` / `img_api_base` /
   `img_model` / `img_width` / `img_height`）喂给了一个没人调用的对象；
2. **失败不可见** —— 出错只 `logger.error` 后返回 `None`，界面拿不到原因；
3. **`img_api_key` 被声明为敏感字段却从未被读取** ⇒ 需要鉴权的远端/自建端点无法使用；
4. **没有健康探测与模型列表** —— 用户只能手打模型文件名，填错了要到生成时才失败。
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

import httpx

from .config import AppConfig

__all__ = [
    "IMAGE_BACKENDS",
    "ImageBackend",
    "ImageGenResult",
    "ImageGenerator",
    "parse_comfyui_models",
    "parse_sdapi_models",
]

#: 未配置/明确关闭时使用的占位值。单独提出是因为它在"读配置"与"写配置"两端都要用。
DISABLED_PROVIDER = "disabled"


# ============================================================ 解析（纯函数，可单测）


def parse_comfyui_models(data: Any) -> List[str]:
    """从 ComfyUI `GET /object_info/CheckpointLoaderSimple` 的响应里取 checkpoint 名列表。

    该接口的形状是 `{"CheckpointLoaderSimple": {"input": {"required":
    {"ckpt_name": [["a.safetensors", "b.safetensors"], {...}]}}}}` ——
    即"字段名 → [候选值列表, 附加选项]"。层级较深，所以逐层 `isinstance` 校验，
    任何一层形状不符就返回空列表，**不抛异常**（这是给界面下拉框用的，
    探测失败应当安静地退化成"空列表"，而不是把设置页弄崩）。
    """
    try:
        node = data.get("CheckpointLoaderSimple")
        required = node.get("input", {}).get("required", {})
        ckpt = required.get("ckpt_name", [])
        candidates = ckpt[0] if isinstance(ckpt, list) and ckpt else []
        return [str(x) for x in candidates if isinstance(x, str)]
    except (AttributeError, TypeError, IndexError):
        return []


def parse_sdapi_models(data: Any) -> List[str]:
    """从 SD WebUI `GET /sdapi/v1/sd-models` 的响应里取模型标题。

    响应是 `[{"title": "sd_xl_base_1.0 [hash]", "model_name": "sd_xl_base_1.0", ...}, ...]`。
    **优先用 `model_name`**（可读、也是 txt2img 实际接受的形式），没有才退回 `title`。
    """
    if not isinstance(data, list):
        return []
    out: List[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("model_name") or item.get("title") or ""
        if name:
            out.append(str(name))
    return out


# ============================================================ 后端注册表


@dataclass(frozen=True)
class ImageBackend:
    """一个文生图后端的静态定义。

    把"默认地址 / 健康探测路径 / 模型列表路径与解析方式"集中在一处，
    新增后端（例如远程 SD 服务、其它 WebUI 分支）只需在 `IMAGE_BACKENDS` 加一条。
    """

    key: str
    label: str
    default_base: str
    #: 健康探测路径（相对 base）
    health_path: str
    #: 模型列表路径（相对 base）；为空表示该后端不提供列表接口
    models_path: str = ""
    #: 模型列表解析函数
    models_parser: Optional[Callable[[Any], List[str]]] = None
    #: 该后端是否支持用 API Key 鉴权（自建反代/云托管常见）
    supports_api_key: bool = True
    #: 生成超时（秒）。ComfyUI 是"提交 + 轮询"，超时由轮询上限控制，这里给单次请求用
    request_timeout: float = 120.0


IMAGE_BACKENDS: Dict[str, ImageBackend] = {
    "comfyui": ImageBackend(
        key="comfyui",
        label="ComfyUI",
        default_base="http://127.0.0.1:8188",
        health_path="/system_stats",
        models_path="/object_info/CheckpointLoaderSimple",
        models_parser=parse_comfyui_models,
    ),
    "sdapi": ImageBackend(
        key="sdapi",
        label="Stable Diffusion WebUI",
        default_base="http://127.0.0.1:7860",
        # SD WebUI 没有轻量 ping（`/internal/ping` 版本不一），
        # 用 sd-models 同时充当"健康探测"和"模型列表"——一次请求两用，也少一个会变的接口。
        health_path="/sdapi/v1/sd-models",
        models_path="/sdapi/v1/sd-models",
        models_parser=parse_sdapi_models,
    ),
}


# ============================================================ 结果对象


class ImageGenResult:
    """一次文生图的结果。仿 `BalanceResult`：`ok` 判成败、`message` 给人看。

    为什么需要它：旧实现出错只写 logger 后返回 `None`，
    界面无法区分"未启用 / 后端连不上 / 模型名不对 / 生成超时"，
    只能显示一句无信息量的"生成失败"。
    """

    __slots__ = ("ok", "provider", "data", "path", "width", "height", "elapsed_ms", "error", "message")

    def __init__(
        self,
        ok: bool = False,
        provider: str = "",
        data: Optional[bytes] = None,
        path: Optional[Path] = None,
        width: int = 0,
        height: int = 0,
        elapsed_ms: float = 0.0,
        error: str = "",
        message: str = "",
    ):
        self.ok = ok
        self.provider = provider
        self.data = data
        self.path = path
        self.width = width
        self.height = height
        self.elapsed_ms = elapsed_ms
        self.error = error
        self.message = message

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "provider": self.provider,
            "width": self.width,
            "height": self.height,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "error": self.error,
            "message": self.message,
            "path": str(self.path) if self.path else "",
            "bytes": len(self.data) if self.data else 0,
        }

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"ImageGenResult(ok={self.ok}, provider={self.provider!r}, error={self.error!r})"


# ============================================================ 生成器


class ImageGenerator:
    """文生图。对外分两层：

    - `generate()`          —— 兼容旧签名，成功返回 `bytes`、失败返回 `None`
    - `generate_result()`   —— 结构化结果，**界面应当用这个**（能拿到失败原因）
    """

    def __init__(self, config: AppConfig):
        self.config = config
        #: 最近一次失败的说明（供界面显示；`generate()` 调用方也能读）
        self.last_error: str = ""

    # ------------------------------------------------------------ 配置读取

    def provider(self) -> str:
        return str(self.config.get("img_provider", "comfyui") or DISABLED_PROVIDER)

    def is_configured(self) -> bool:
        """是否启用了文生图（旧语义：不是 `disabled` 即认为"配置过"）。

        注意它**只反映配置意愿**，不代表后端真的可用 —— 要判断可用性请用 `check_backend()`。
        旧实现把这两件事混为一谈，于是状态栏会显示「+ 文生图」而实际连不上后端。
        """
        return self.provider() != DISABLED_PROVIDER

    def backend(self) -> Optional[ImageBackend]:
        return IMAGE_BACKENDS.get(self.provider())

    def base_url(self) -> str:
        """生效的后端地址：配置优先，否则用该后端的默认地址。"""
        configured = str(self.config.get("img_api_base", "") or "").strip()
        if configured:
            return configured.rstrip("/")
        backend = self.backend()
        return backend.default_base if backend else ""

    def model_name(self) -> str:
        backend = self.backend()
        configured = str(self.config.get("img_model", "") or "").strip()
        if configured:
            return configured
        return "sd_xl_base_1.0.safetensors" if backend and backend.key == "comfyui" else ""

    def _headers(self) -> Dict[str, str]:
        """按 `img_api_key` 组装鉴权头。

        ❗ 这是审计发现的缺口：`img_api_key` 一直被声明为**敏感字段**（会被加密落盘），
        但全仓**没有任何读取点** ⇒ 需要鉴权的远端/自建端点（常见的做法是
        在 SD/ComfyUI 前面套一层带 Bearer 的反代）根本用不了。
        没有 key 时不加头，保持本地直连的旧行为。
        """
        key = str(self.config.get("img_api_key", "") or "").strip()
        return {"Authorization": f"Bearer {key}"} if key else {}

    def _dimension(self, explicit: int | None, key: str, default: int = 1024) -> int:
        """取尺寸：显式入参优先，否则读配置，读不到/读坏了退回默认。

        ❗ 必须做防御性转换：配置里的值可能来自 Entry 控件（**字符串**）、
        可能是 `None`、也可能被手工改成了任意文本。直接 `int()` 会抛 ValueError，
        而这是在生成图片的主路径上 —— 宁可退回默认尺寸，也不要让一张图都生不出来。
        """
        if explicit is not None:
            try:
                value = int(explicit)
            except (TypeError, ValueError):
                return default
            return value if value > 0 else default
        raw = self.config.get(key, default)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        return value if value > 0 else default

    # ------------------------------------------------------------ 探测

    def check_backend(self, timeout: float = 5.0) -> ImageGenResult:
        """探测后端是否可用（界面「检测后端」按钮）。

        三种结果要能分辨：未启用 / 连不上（附原因）/ 可用（附模型数量）。
        """
        if not self.is_configured():
            return ImageGenResult(ok=False, provider=self.provider(), message="文生图未启用")

        backend = self.backend()
        if backend is None:
            return ImageGenResult(ok=False, provider=self.provider(), message=f"未知后端：{self.provider()}")

        base = self.base_url()
        if not base:
            return ImageGenResult(ok=False, provider=backend.key, message="未配置后端地址")

        try:
            resp = httpx.get(f"{base}{backend.health_path}", headers=self._headers(), timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - 探测失败要转成可展示文本
            return ImageGenResult(
                ok=False,
                provider=backend.key,
                error=f"{type(exc).__name__}: {exc}",
                message=f"连不上 {backend.label}（{base}）—— 请确认服务已启动、端口与地址正确",
            )

        if resp.status_code != 200:
            return ImageGenResult(
                ok=False,
                provider=backend.key,
                error=f"HTTP {resp.status_code}",
                message=f"{backend.label} 返回 HTTP {resp.status_code}"
                + ("（若后端启用了鉴权，请在设置中填写图片 API Key）" if resp.status_code in (401, 403) else ""),
            )

        models: List[str] = []
        if backend.models_path == backend.health_path and backend.models_parser is not None:
            # SD WebUI：一个接口同时充当健康探测与模型列表，直接用刚拿到的响应，省一次请求
            try:
                models = backend.models_parser(resp.json())
            except ValueError:
                models = []
        return ImageGenResult(
            ok=True,
            provider=backend.key,
            message=f"{backend.label} 可用（探测到 {len(models)} 个模型）" if models else f"{backend.label} 可用",
        )

    def list_models(self, timeout: float = 10.0) -> List[str]:
        """拉取后端可用的模型名列表（界面下拉框用）。

        失败时返回**空列表**而不是抛异常 —— 探测不到就让用户继续手填，
        不该因为"列不出来"就把设置页卡住。
        """
        backend = self.backend()
        if backend is None or not backend.models_path or backend.models_parser is None:
            return []
        base = self.base_url()
        if not base:
            return []
        try:
            resp = httpx.get(f"{base}{backend.models_path}", headers=self._headers(), timeout=timeout)
            if resp.status_code != 200:
                return []
            return backend.models_parser(resp.json())
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[文生图] 拉取模型列表失败：{type(exc).__name__}: {exc}")
            return []

    # ------------------------------------------------------------ 生成

    def generate(
        self, prompt: str, negative_prompt: str = "", width: int | None = None, height: int | None = None
    ) -> Optional[bytes]:
        """生成图片，返回图片字节数据（兼容旧签名）。

        `width` / `height` 为 `None` 时**从配置取**（`img_width` / `img_height`）。
        需要失败原因时改用 `generate_result()` —— 本方法只保留 `last_error`。
        """
        result = self.generate_result(prompt, negative_prompt, width, height)
        return result.data if result.ok else None

    def generate_result(
        self, prompt: str, negative_prompt: str = "", width: int | None = None, height: int | None = None
    ) -> ImageGenResult:
        """生成图片并返回**结构化结果**（含失败原因）。界面用这个。"""
        started = time.perf_counter()
        provider = self.provider()

        def _fail(msg: str, err: str = "") -> ImageGenResult:
            self.last_error = err or msg
            return ImageGenResult(
                ok=False,
                provider=provider,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                error=err,
                message=msg,
            )

        if not prompt or not prompt.strip():
            return _fail("提示词为空，无法生成")

        backend = self.backend()
        if backend is None:
            # 未启用/未知后端：**明确说明**，不要静默返回 None
            if provider == DISABLED_PROVIDER:
                return _fail("文生图未启用（当前设为 disabled），请在设置 → 文生图中选择后端")
            return _fail(f"未知的图片后端：{provider}")

        width = self._dimension(width, "img_width")
        height = self._dimension(height, "img_height")

        if backend.key == "comfyui":
            data, error = self._generate_comfyui(prompt, negative_prompt, width, height)
        else:
            data, error = self._generate_sdapi(prompt, negative_prompt, width, height)

        if not data:
            return _fail(f"{backend.label} 生成失败：{error or '未返回图片数据'}", error)
        self.last_error = ""
        return ImageGenResult(
            ok=True,
            provider=backend.key,
            data=data,
            width=width,
            height=height,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            message=f"{backend.label} 生成成功（{width}×{height}）",
        )

    def _generate_comfyui(self, prompt, negative_prompt, width, height):
        """通过 ComfyUI 生成图片。

        返回 `(data, error)` —— 出错时 err 是可展示的说明，而不是一个裸 `None`。
        """
        api_base = self.base_url()
        model = self.model_name()
        if not api_base:
            return None, "未配置后端地址"
        if not model:
            return None, "未选择模型（Checkpoint 文件名）"

        try:
            workflow = {
                "3": {
                    "class_type": "KSampler",
                    "inputs": {
                        "seed": int(time.time()) % (2**32),
                        "steps": 25,
                        "cfg": 7.0,
                        "sampler_name": "euler",
                        "scheduler": "normal",
                        "denoise": 1.0,
                        "model": ["4", 0],
                        "positive": ["6", 0],
                        "negative": ["7", 0],
                        "latent_image": ["5", 0],
                    },
                },
                "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": model}},
                "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
                "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
                "7": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"text": negative_prompt or "low quality, blurry, deformed", "clip": ["4", 1]},
                },
                "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
                "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "novel_img", "images": ["8", 0]}},
            }

            resp = httpx.post(f"{api_base}/prompt", json={"prompt": workflow}, headers=self._headers(), timeout=10)
            resp.raise_for_status()
            prompt_id = resp.json()["prompt_id"]

            # 轮询等待完成（ComfyUI 是异步队列，没有同步返回的接口）
            for _ in range(240):  # 最多等 4 分钟
                time.sleep(1)
                hist_resp = httpx.get(f"{api_base}/history/{prompt_id}", headers=self._headers(), timeout=5)
                if hist_resp.status_code != 200:
                    continue
                history = hist_resp.json()
                outputs = (history.get(prompt_id) or {}).get("outputs", {})
                if "9" in outputs:
                    img_info = outputs["9"]["images"][0]
                    img_resp = httpx.get(
                        f"{api_base}/view",
                        params={
                            "filename": img_info["filename"],
                            "subfolder": img_info.get("subfolder", ""),
                            "type": img_info["type"],
                        },
                        headers=self._headers(),
                        timeout=10,
                    )
                    return img_resp.content, ""
            return None, "等待生成结果超时（4 分钟）—— 后端可能排队过长或模型加载失败"
        except KeyError as exc:
            return None, f"ComfyUI 响应缺少字段 {exc}（可能是工作流节点不兼容）"
        except Exception as exc:  # noqa: BLE001 - 主路径必须给出可展示原因
            logger.error(f"ComfyUI生成失败: {exc}")
            return None, f"{type(exc).__name__}: {exc}"

    def _generate_sdapi(self, prompt, negative_prompt, width, height):
        """通过 SD WebUI API 生成图片。返回 `(data, error)`。"""
        api_base = self.base_url()
        if not api_base:
            return None, "未配置后端地址"
        try:
            resp = httpx.post(
                f"{api_base}/sdapi/v1/txt2img",
                json={
                    "prompt": prompt,
                    "negative_prompt": negative_prompt or "low quality, blurry",
                    "width": width,
                    "height": height,
                    "steps": 25,
                    "cfg_scale": 7.0,
                    "sampler_name": "Euler a",
                },
                headers=self._headers(),
                timeout=180,
            )
            resp.raise_for_status()

            images = resp.json().get("images", [])
            if images:
                return base64.b64decode(images[0]), ""
            return None, "接口未返回 images 字段"
        except Exception as exc:  # noqa: BLE001
            logger.error(f"SD API生成失败: {exc}")
            return None, f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------ 落盘

    def save_image(self, img_data: bytes, save_dir: Path, name: str) -> Path:
        """保存图片到 `<save_dir>/images/<name>.png`。"""
        img_dir = Path(save_dir) / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        filepath = img_dir / f"{name}.png"
        with open(filepath, "wb") as f:
            f.write(img_data)
        return filepath

    def generate_to_novel(
        self,
        prompt: str,
        novel_dir: Path,
        name: str,
        negative_prompt: str = "",
        width: int | None = None,
        height: int | None = None,
    ) -> ImageGenResult:
        """生成并直接存进作品目录（界面按钮的调用逻辑）。

        "生成 + 落盘"合成一个动作，是因为界面要的就是"给我一张能看的图"；
        拆成两步会让调用方各自重复一遍路径拼接与错误处理。
        """
        result = self.generate_result(prompt, negative_prompt, width, height)
        if not result.ok or not result.data:
            return result
        try:
            result.path = self.save_image(result.data, Path(novel_dir), name)
            result.message += f"，已保存到 {result.path.name}"
        except OSError as exc:
            result.ok = False
            result.error = f"{type(exc).__name__}: {exc}"
            result.message = f"图片已生成但保存失败：{exc}"
        return result
