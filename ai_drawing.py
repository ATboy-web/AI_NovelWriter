"""
AI绘图模块 - 支持ComfyUI和SD WebUI
"""

import json
import time
import httpx
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class AIDrawing:
    """AI绘图管理器"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.comfyui_url = self.config.get("comfyui_url", "http://127.0.0.1:8188")
        self.sdwebui_url = self.config.get("sdwebui_url", "http://127.0.0.1:7860")
        self.provider = self.config.get("provider", "comfyui")  # comfyui / sdwebui / disabled
        
    def is_available(self) -> bool:
        """检查AI绘图服务是否可用"""
        if self.provider == "disabled":
            return False
        
        try:
            if self.provider == "comfyui":
                resp = httpx.get(f"{self.comfyui_url}/system_stats", timeout=5)
                return resp.status_code == 200
            elif self.provider == "sdwebui":
                resp = httpx.get(f"{self.sdwebui_url}/sdapi/v1/options", timeout=5)
                return resp.status_code == 200
        except:
            pass
        
        return False
    
    def generate_image(self, prompt: str, negative_prompt: str = "",
                      width: int = 1024, height: int = 1024,
                      steps: int = 25, cfg_scale: float = 7.0) -> Optional[bytes]:
        """生成图片"""
        if self.provider == "comfyui":
            return self._generate_comfyui(prompt, negative_prompt, width, height, steps, cfg_scale)
        elif self.provider == "sdwebui":
            return self._generate_sdwebui(prompt, negative_prompt, width, height, steps, cfg_scale)
        return None
    
    def _generate_comfyui(self, prompt: str, negative_prompt: str,
                          width: int, height: int, steps: int, cfg_scale: float) -> Optional[bytes]:
        """通过ComfyUI生成图片"""
        try:
            # 构建工作流
            workflow = self._build_comfyui_workflow(prompt, negative_prompt, width, height, steps, cfg_scale)
            
            # 提交工作流
            resp = httpx.post(f"{self.comfyui_url}/prompt", json={"prompt": workflow}, timeout=10)
            resp.raise_for_status()
            prompt_id = resp.json()["prompt_id"]
            
            # 等待完成
            for _ in range(120):  # 最多等2分钟
                time.sleep(1)
                hist_resp = httpx.get(f"{self.comfyui_url}/history/{prompt_id}", timeout=5)
                if hist_resp.status_code == 200:
                    history = hist_resp.json()
                    if prompt_id in history:
                        outputs = history[prompt_id].get("outputs", {})
                        # 查找SaveImage节点的输出
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                img_info = node_output["images"][0]
                                img_resp = httpx.get(
                                    f"{self.comfyui_url}/view",
                                    params={
                                        "filename": img_info["filename"],
                                        "subfolder": img_info.get("subfolder", ""),
                                        "type": img_info["type"]
                                    },
                                    timeout=10
                                )
                                return img_resp.content
            
            return None
        except Exception as e:
            print(f"ComfyUI生成失败: {e}")
            return None
    
    def _build_comfyui_workflow(self, prompt: str, negative_prompt: str,
                                width: int, height: int, steps: int, cfg_scale: float) -> Dict:
        """构建ComfyUI工作流"""
        model = self.config.get("model", "sd_xl_base_1.0.safetensors")
        
        return {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": int(time.time()) % (2**32),
                    "steps": steps,
                    "cfg": cfg_scale,
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
    
    def _generate_sdwebui(self, prompt: str, negative_prompt: str,
                          width: int, height: int, steps: int, cfg_scale: float) -> Optional[bytes]:
        """通过SD WebUI生成图片"""
        try:
            import base64
            
            resp = httpx.post(f"{self.sdwebui_url}/sdapi/v1/txt2img", json={
                "prompt": prompt,
                "negative_prompt": negative_prompt or "low quality, blurry",
                "width": width,
                "height": height,
                "steps": steps,
                "cfg_scale": cfg_scale,
                "sampler_name": "Euler a",
            }, timeout=120)
            resp.raise_for_status()
            
            images = resp.json().get("images", [])
            if images:
                return base64.b64decode(images[0])
            return None
        except Exception as e:
            print(f"SD WebUI生成失败: {e}")
            return None
    
    def generate_character_portrait(self, character_name: str, appearance: str,
                                   style: str = "anime") -> Optional[bytes]:
        """生成角色立绘"""
        prompt = f"{character_name}, {appearance}, character portrait, {style} style, detailed face, masterpiece, best quality"
        negative = "low quality, blurry, deformed, ugly, bad anatomy"
        return self.generate_image(prompt, negative, 768, 1024)
    
    def generate_scene(self, scene_description: str, style: str = "anime") -> Optional[bytes]:
        """生成场景插图"""
        prompt = f"{scene_description}, {style} style, detailed background, cinematic lighting, masterpiece, best quality"
        negative = "low quality, blurry, deformed, ugly"
        return self.generate_image(prompt, negative, 1024, 768)
    
    def generate_cover(self, title: str, genre: str, description: str) -> Optional[bytes]:
        """生成封面"""
        prompt = f"book cover, {title}, {genre}, {description}, professional design, masterpiece, best quality"
        negative = "low quality, blurry, text, watermark"
        return self.generate_image(prompt, negative, 800, 1200)
    
    def save_image(self, image_data: bytes, save_dir: Path, name: str) -> Path:
        """保存图片"""
        save_dir.mkdir(exist_ok=True)
        filepath = save_dir / f"{name}.png"
        with open(filepath, 'wb') as f:
            f.write(image_data)
        return filepath


class SceneDetector:
    """场景检测器 - 从文本中检测适合插图的场景"""
    
    SCENE_KEYWORDS = {
        "战斗": ["战", "斗", "杀", "剑", "刀", "拳", "攻", "击", "斩", "劈", "刺"],
        "风景": ["山", "水", "海", "天空", "星空", "森林", "草原", "沙漠", "雪"],
        "城市": ["城", "街", "楼", "宫", "殿", "塔", "桥", "广场"],
        "人物": ["容貌", "美貌", "英俊", "潇洒", "绝美", "倾城", "飘逸"],
        "情感": ["爱", "恨", "泪", "笑", "心", "情", "思念", "牵挂"],
        "修炼": ["修炼", "突破", "境界", "灵气", "丹田", "功法", "渡劫"],
    }
    
    @classmethod
    def detect_scenes(cls, content: str, max_scenes: int = 5) -> List[Dict]:
        """从文本中检测适合插图的场景"""
        scenes = []
        
        for scene_type, keywords in cls.SCENE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in content:
                    # 提取包含关键词的段落
                    for para in content.split('\n'):
                        if keyword in para and len(para.strip()) > 20:
                            scenes.append({
                                "type": scene_type,
                                "keyword": keyword,
                                "text": para.strip()[:200],
                                "prompt": cls._build_prompt(para.strip(), scene_type)
                            })
                            break  # 每个关键词只取第一个匹配
        
        # 去重并限制数量
        unique_scenes = []
        seen = set()
        for scene in scenes:
            key = scene["text"][:50]
            if key not in seen:
                seen.add(key)
                unique_scenes.append(scene)
        
        return unique_scenes[:max_scenes]
    
    @classmethod
    def _build_prompt(cls, text: str, scene_type: str) -> str:
        """构建绘图提示词"""
        style_map = {
            "战斗": "epic battle scene, dynamic action, dramatic lighting, anime style",
            "风景": "beautiful landscape, scenic view, anime style, detailed",
            "城市": "city scene, architecture, anime style, detailed",
            "人物": "character portrait, anime style, detailed face, beautiful",
            "情感": "emotional scene, anime style, warm lighting, expressive",
            "修炼": "cultivation scene, mystical energy, anime style, dramatic",
        }
        
        style = style_map.get(scene_type, "anime style, detailed, masterpiece")
        return f"{text[:100]}, {style}, best quality, masterpiece"
