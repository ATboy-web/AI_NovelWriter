"""
文生图模块 - 支持ComfyUI和SD API
"""

import time
from pathlib import Path
from typing import Optional

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

import httpx

from .config import AppConfig


class ImageGenerator:
    """文生图模块 - 支持ComfyUI和SD API"""

    def __init__(self, config: AppConfig):
        self.config = config

    def is_configured(self) -> bool:
        provider = self.config.get("img_provider", "disabled")
        return provider != "disabled"

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

    def generate(
        self, prompt: str, negative_prompt: str = "", width: int | None = None, height: int | None = None
    ) -> Optional[bytes]:
        """生成图片，返回图片字节数据。

        `width` / `height` 为 `None` 时**从配置取**（`img_width` / `img_height`）。
        原先两者的默认值是写死的 1024，于是"图片宽/高"填了也不生效
        —— 属于"声明了但无效"的配置项（审计发现）。
        显式传参仍然优先，保持调用方可覆盖。
        """
        provider = self.config.get("img_provider", "comfyui")
        # 先判后端：未启用/未知后端直接返回，**不要**去读尺寸配置 ——
        # 否则一个无关的坏配置值（例如 MagicMock 或空串）会让本函数抛错，
        # 把"未启用"这种正常情况变成异常（单测正是这么发现的）。
        if provider not in ("comfyui", "sdapi"):
            return None

        width = self._dimension(width, "img_width")
        height = self._dimension(height, "img_height")
        if provider == "comfyui":
            return self._generate_comfyui(prompt, negative_prompt, width, height)
        return self._generate_sdapi(prompt, negative_prompt, width, height)

    def _generate_comfyui(self, prompt, negative_prompt, width, height) -> Optional[bytes]:
        """通过ComfyUI生成图片"""
        try:
            api_base = self.config.get("img_api_base", "http://127.0.0.1:8188")
            model = self.config.get("img_model", "sd_xl_base_1.0.safetensors")

            # ComfyUI工作流
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

            # 提交工作流
            resp = httpx.post(f"{api_base}/prompt", json={"prompt": workflow}, timeout=10)
            resp.raise_for_status()
            prompt_id = resp.json()["prompt_id"]

            # 轮询等待完成
            for _ in range(120):  # 最多等2分钟
                time.sleep(1)
                hist_resp = httpx.get(f"{api_base}/history/{prompt_id}", timeout=5)
                if hist_resp.status_code == 200:
                    history = hist_resp.json()
                    if prompt_id in history:
                        outputs = history[prompt_id].get("outputs", {})
                        if "9" in outputs:
                            img_info = outputs["9"]["images"][0]
                            img_resp = httpx.get(
                                f"{api_base}/view",
                                params={
                                    "filename": img_info["filename"],
                                    "subfolder": img_info.get("subfolder", ""),
                                    "type": img_info["type"],
                                },
                                timeout=10,
                            )
                            return img_resp.content

            return None
        except Exception as e:
            logger.error(f"ComfyUI生成失败: {e}")
            return None

    def _generate_sdapi(self, prompt, negative_prompt, width, height) -> Optional[bytes]:
        """通过Stable Diffusion WebUI API生成图片"""
        try:
            import base64

            api_base = self.config.get("img_api_base", "http://127.0.0.1:7860")

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
                timeout=120,
            )
            resp.raise_for_status()

            images = resp.json().get("images", [])
            if images:
                return base64.b64decode(images[0])
            return None
        except Exception as e:
            logger.error(f"SD API生成失败: {e}")
            return None

    def save_image(self, img_data: bytes, save_dir: Path, name: str) -> Path:
        """保存图片"""
        img_dir = save_dir / "images"
        img_dir.mkdir(exist_ok=True)
        filepath = img_dir / f"{name}.png"
        with open(filepath, "wb") as f:
            f.write(img_data)
        return filepath
