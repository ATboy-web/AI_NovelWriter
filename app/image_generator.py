"""
文生图模块 - 支持ComfyUI和SD API
"""

import time
from pathlib import Path
from typing import Optional
from loguru import logger

import httpx

from .config import AppConfig


class ImageGenerator:
    """文生图模块 - 支持ComfyUI和SD API"""
    
    def __init__(self, config: AppConfig):
        self.config = config
    
    def is_configured(self) -> bool:
        provider = self.config.get("img_provider", "disabled")
        return provider != "disabled"
    
    def generate(self, prompt: str, negative_prompt: str = "", width: int = 1024, height: int = 1024) -> Optional[bytes]:
        """生成图片，返回图片字节数据"""
        provider = self.config.get("img_provider", "comfyui")
        
        if provider == "comfyui":
            return self._generate_comfyui(prompt, negative_prompt, width, height)
        elif provider == "sdapi":
            return self._generate_sdapi(prompt, negative_prompt, width, height)
        return None
    
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
                    }
                },
                "4": {
                    "class_type": "CheckpointLoaderSimple",
                    "inputs": {"ckpt_name": model}
                },
                "5": {
                    "class_type": "EmptyLatentImage",
                    "inputs": {"width": width, "height": height, "batch_size": 1}
                },
                "6": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"text": prompt, "clip": ["4", 1]}
                },
                "7": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"text": negative_prompt or "low quality, blurry, deformed", "clip": ["4", 1]}
                },
                "8": {
                    "class_type": "VAEDecode",
                    "inputs": {"samples": ["3", 0], "vae": ["4", 2]}
                },
                "9": {
                    "class_type": "SaveImage",
                    "inputs": {"filename_prefix": "novel_img", "images": ["8", 0]}
                },
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
                                params={"filename": img_info["filename"], "subfolder": img_info.get("subfolder", ""), "type": img_info["type"]},
                                timeout=10
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
            
            resp = httpx.post(f"{api_base}/sdapi/v1/txt2img", json={
                "prompt": prompt,
                "negative_prompt": negative_prompt or "low quality, blurry",
                "width": width,
                "height": height,
                "steps": 25,
                "cfg_scale": 7.0,
                "sampler_name": "Euler a",
            }, timeout=120)
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
        with open(filepath, 'wb') as f:
            f.write(img_data)
        return filepath
