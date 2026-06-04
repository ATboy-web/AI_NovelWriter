"""
AI自动写小说系统 - 桌面应用程序
集成AI API、长上下文记忆、智能体机制
"""

import json
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# GUI
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

# HTTP客户端
import httpx

# 文件格式支持（条件导入）
try:
    from ebooklib import epub
    EPUB_SUPPORT = True
except ImportError:
    EPUB_SUPPORT = False

try:
    import PyPDF2
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

try:
    from docx import Document
    DOCX_SUPPORT = True
except ImportError:
    DOCX_SUPPORT = False

# 小说工具集
from novel_toolkit import (ElementLibrary, BridgeLibrary, DescriptionLibrary,
                           DialogueEngine, StoryFlowEngine, StyleTransferEngine, AdaptEngine,
                           WebSearchAdaptEngine)
from character_system import CharacterSystem
from format_converter import FormatConverter, ImageManager
from cloud_storage import CloudStorageManager


# ==================== 配置管理 ====================

class AppConfig:
    """应用配置"""
    
    def __init__(self):
        self.config_dir = Path.home() / ".ai_novel_writer"
        self.config_dir.mkdir(exist_ok=True)
        self.config_file = self.config_dir / "config.json"
        self.novels_dir = self.config_dir / "novels"
        self.novels_dir.mkdir(exist_ok=True)
        self.config = self._load()
    
    def _load(self) -> dict:
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "api_provider": "ollama",  # openai / claude / deepseek / ollama / custom
            "api_key": "",
            "api_base": "http://localhost:11434",
            "model": "qwen2.5:14b",
            "max_tokens": 4096,
            "temperature": 0.8,
            "context_window": 32000,  # 上下文窗口大小（字符数）
            "auto_save": True,
            "theme": "light",
            # 文生图配置
            "img_provider": "comfyui",  # comfyui / sdapi / disabled
            "img_api_base": "http://127.0.0.1:8188",
            "img_model": "sd_xl_base_1.0.safetensors",
            "img_width": 1024,
            "img_height": 1024,
            "auto_detect_scene": True,  # 自动检测名场面
        }
    
    def save(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
    
    def get(self, key: str, default=None):
        return self.config.get(key, default)
    
    def set(self, key: str, value):
        self.config[key] = value
        self.save()


# ==================== AI客户端 ====================

class AIClient:
    """统一AI客户端"""
    
    PROVIDERS = {
        "ollama": {
            "name": "Ollama (本地)",
            "base_url": "http://localhost:11434",
            "models": ["qwen2.5:14b", "qwen2.5:7b", "llama3.1:8b", "deepseek-r1:14b", "glm4:9b"],
        },
        "openai": {
            "name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        },
        "deepseek": {
            "name": "DeepSeek",
            "base_url": "https://api.deepseek.com/v1",
            "models": ["deepseek-chat", "deepseek-reasoner"],
        },
        "claude": {
            "name": "Claude",
            "base_url": "https://api.anthropic.com/v1",
            "models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"],
        },
        "custom": {
            "name": "自定义API",
            "base_url": "",
            "models": [],
        },
    }
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.client = None
        self._init_client()
    
    def _init_client(self):
        provider = self.config.get("api_provider", "ollama")
        api_key = self.config.get("api_key", "")
        api_base = self.config.get("api_base", "")
        
        base_url = api_base or self.PROVIDERS.get(provider, {}).get("base_url", "")
        
        if provider == "claude" and api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                pass
        elif provider == "ollama":
            # Ollama不需要API密钥
            self.client = httpx.Client(base_url=base_url, timeout=300.0)
        elif api_key:
            self.client = httpx.Client(
                base_url=base_url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=120.0,
            )
    
    def is_configured(self) -> bool:
        provider = self.config.get("api_provider", "ollama")
        if provider == "ollama":
            return self.client is not None
        return self.client is not None and self.config.get("api_key", "")
    
    def get_ollama_models(self) -> List[str]:
        """获取Ollama本地模型列表"""
        try:
            base_url = self.config.get("api_base", "http://localhost:11434")
            resp = httpx.get(f"{base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                return [m["name"] for m in models]
        except:
            pass
        return []
    
    def chat(self, messages: List[Dict], system: str = "", **kwargs) -> str:
        """发送聊天请求"""
        if not self.is_configured():
            raise Exception("AI API未配置，请在设置中配置API密钥")
        
        provider = self.config.get("api_provider", "ollama")
        model = self.config.get("model", "qwen2.5:14b")
        max_tokens = kwargs.get("max_tokens", self.config.get("max_tokens", 4096))
        temperature = kwargs.get("temperature", self.config.get("temperature", 0.8))
        
        if provider == "claude":
            return self._chat_claude(messages, system, model, max_tokens, temperature)
        elif provider == "ollama":
            return self._chat_ollama(messages, system, model, max_tokens, temperature)
        else:
            return self._chat_openai(messages, system, model, max_tokens, temperature)
    
    def _chat_openai(self, messages, system, model, max_tokens, temperature) -> str:
        """OpenAI兼容接口"""
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)
        
        response = self.client.post("/chat/completions", json={
            "model": model,
            "messages": full_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    
    def _chat_ollama(self, messages, system, model, max_tokens, temperature) -> str:
        """Ollama本地模型接口"""
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)
        
        response = self.client.post("/api/chat", json={
            "model": model,
            "messages": full_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        })
        response.raise_for_status()
        return response.json()["message"]["content"]
    
    def _chat_claude(self, messages, system, model, max_tokens, temperature) -> str:
        """Claude接口"""
        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or "",
            messages=messages,
        )
        return response.content[0].text


# ==================== 文生图模块 ====================

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
            print(f"ComfyUI生成失败: {e}")
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
            print(f"SD API生成失败: {e}")
            return None
    
    def save_image(self, img_data: bytes, save_dir: Path, name: str) -> Path:
        """保存图片"""
        img_dir = save_dir / "images"
        img_dir.mkdir(exist_ok=True)
        filepath = img_dir / f"{name}.png"
        with open(filepath, 'wb') as f:
            f.write(img_data)
        return filepath


# ==================== 名场面检测器 ====================

class SceneDetector:
    """名场面检测器 - 检测适合生成插图的场景"""
    
    # 触发关键词
    SCENE_KEYWORDS = [
        # 战斗场面
        "大战", "对决", "交锋", "激战", "厮杀", "出剑", "拔刀", "施展",
        # 震撼场面
        "震撼", "壮观", "磅礴", "恢弘", "浩瀚", "天地变色", "风云变幻",
        # 帅气描写
        "英俊", "潇洒", "飘逸", "凌厉", "霸气", "威严", "冷峻", "邪魅",
        # 美丽描写
        "绝美", "倾城", "惊艳", "如画", "仙子", "出尘", "清丽", "妩媚",
        # 情感高潮
        "告白", "拥吻", "热泪", "重逢", "离别", "生死", "牺牲",
        # 场景转换
        "踏入", "登临", "俯瞰", "仰望", "穿越", "降临",
    ]
    
    CHARACTER_KEYWORDS = [
        "主角", "少年", "少女", "男子", "女子", "将军", "帝王", "仙人",
        "剑客", "侠女", "公主", "王子", "魔王", "天使", "龙", "凤",
    ]
    
    @staticmethod
    def detect(content: str) -> List[Dict[str, str]]:
        """检测内容中的名场面，返回场景列表"""
        scenes = []
        
        # 方法1: 关键词匹配
        for keyword in SceneDetector.SCENE_KEYWORDS:
            if keyword in content:
                # 找到关键词所在的句子
                for sentence in content.replace("。", "。\n").replace("！", "！\n").replace("？", "？\n").split("\n"):
                    if keyword in sentence and len(sentence.strip()) > 10:
                        scene_type = SceneDetector._classify_scene(sentence)
                        scenes.append({
                            "text": sentence.strip()[:200],
                            "keyword": keyword,
                            "type": scene_type,
                            "prompt": SceneDetector._build_prompt(sentence, scene_type),
                        })
        
        # 去重
        seen = set()
        unique_scenes = []
        for s in scenes:
            key = s["text"][:50]
            if key not in seen:
                seen.add(key)
                unique_scenes.append(s)
        
        return unique_scenes[:5]  # 最多返回5个场景
    
    @staticmethod
    def _classify_scene(text: str) -> str:
        """分类场景类型"""
        battle_words = ["战", "斗", "杀", "剑", "刀", "拳", "攻", "击"]
        beauty_words = ["美", "仙", "丽", "艳", "俊", "帅", "魅"]
        emotion_words = ["泪", "笑", "爱", "恨", "告白", "拥", "吻"]
        
        for w in battle_words:
            if w in text:
                return "battle"
        for w in beauty_words:
            if w in text:
                return "beauty"
        for w in emotion_words:
            if w in text:
                return "emotion"
        return "epic"
    
    @staticmethod
    def _build_prompt(text: str, scene_type: str) -> str:
        """构建文生图提示词"""
        style_map = {
            "battle": "epic battle scene, dynamic action, dramatic lighting, cinematic, anime style, high detail",
            "beauty": "beautiful character portrait, elegant pose, soft lighting, anime style, highly detailed",
            "emotion": "emotional scene, cinematic composition, warm lighting, anime style, expressive",
            "epic": "epic fantasy scene, grand scale, dramatic atmosphere, anime style, masterpiece",
        }
        base_style = style_map.get(scene_type, style_map["epic"])
        return f"{text[:100]}, {base_style}, best quality, masterpiece"


# ==================== 长上下文记忆管理 ====================

class MemoryManager:
    """长上下文记忆管理器 - 分层架构，支持5000章小说
    
    分层架构：
    1. 全局摘要 - 整个故事的核心概述 (1个文件)
    2. 卷级摘要 - 每100章为一卷的概述 (50个文件)
    3. 弧线摘要 - 重要剧情弧线的概述 (200个文件)
    4. 章节摘要 - 每章的详细摘要 (5000个文件)
    
    核心机制：
    1. RAG检索 - 倒排索引+关键词匹配，支持百万级检索
    2. 语义去重 - 相似记忆自动合并
    3. 记忆评分 - 根据重要性/新鲜度/引用次数打分
    4. 知识图谱 - 角色关系+事件时间线
    5. 分页加载 - 按需加载，不全部读入内存
    6. 角色活跃度 - 按活跃度加载角色卡片
    """
    
    VOLUME_SIZE = 100  # 每卷100章
    
    def __init__(self, novel_dir: Path):
        self.novel_dir = novel_dir
        self.memory_dir = novel_dir / "memory"
        self.memory_dir.mkdir(exist_ok=True)
        
        # 全局摘要
        self.global_summary_file = self.memory_dir / "global_summary.txt"
        # 章节摘要目录
        self.chapters_dir = self.memory_dir / "chapters"
        self.chapters_dir.mkdir(exist_ok=True)
        # 卷级摘要目录 (新增)
        self.volumes_dir = self.memory_dir / "volumes"
        self.volumes_dir.mkdir(exist_ok=True)
        # 弧线摘要目录 (新增)
        self.arcs_dir = self.memory_dir / "arcs"
        self.arcs_dir.mkdir(exist_ok=True)
        # 角色档案（含关系图）
        self.characters_file = self.memory_dir / "characters.json"
        # 世界观设定
        self.settings_file = self.memory_dir / "settings.json"
        # 事件时间线目录 (改为分页存储)
        self.timeline_dir = self.memory_dir / "timeline"
        self.timeline_dir.mkdir(exist_ok=True)
        # 记忆块分页存储 (改为分页)
        self.chunks_dir = self.memory_dir / "chunks"
        self.chunks_dir.mkdir(exist_ok=True)
        # 倒排索引 (新增，替代全量遍历)
        self.inverted_index_file = self.memory_dir / "inverted_index.json"
        # 记忆评分
        self.scores_file = self.memory_dir / "scores.json"
        # 角色活跃度 (新增)
        self.character_activity_file = self.memory_dir / "character_activity.json"
        
        # 缓存
        self._inverted_index = self._load_inverted_index()
        self._scores = self._load_scores()
        self._character_activity = self._load_character_activity()
        self._current_page = 0  # 当前chunks页
        self._chunks_cache = []  # 当前页的chunks缓存
    
    # ===== 初始化加载方法 =====
    
    def _load_inverted_index(self) -> Dict:
        if self.inverted_index_file.exists():
            try:
                return json.loads(self.inverted_index_file.read_text(encoding='utf-8'))
            except: pass
        return {}
    
    def _save_inverted_index(self):
        self.inverted_index_file.write_text(json.dumps(self._inverted_index, ensure_ascii=False), encoding='utf-8')
    
    def _load_scores(self) -> Dict:
        if self.scores_file.exists():
            try:
                return json.loads(self.scores_file.read_text(encoding='utf-8'))
            except: pass
        return {}
    
    def _save_scores(self):
        self.scores_file.write_text(json.dumps(self._scores, ensure_ascii=False), encoding='utf-8')
    
    def _load_character_activity(self) -> Dict:
        if self.character_activity_file.exists():
            try:
                return json.loads(self.character_activity_file.read_text(encoding='utf-8'))
            except: pass
        return {}
    
    def _save_character_activity(self):
        self.character_activity_file.write_text(json.dumps(self._character_activity, ensure_ascii=False), encoding='utf-8')
    
    # ===== 卷级摘要管理 =====
    
    def _chapter_to_volume(self, chapter_num: int) -> int:
        """章节号转卷号 (每100章一卷)"""
        return (chapter_num - 1) // self.VOLUME_SIZE + 1
    
    def save_volume_summary(self, volume_num: int, summary: str):
        """保存卷级摘要"""
        file = self.volumes_dir / f"volume_{volume_num:03d}.txt"
        file.write_text(summary, encoding='utf-8')
    
    def get_volume_summary(self, volume_num: int) -> str:
        """获取卷级摘要"""
        file = self.volumes_dir / f"volume_{volume_num:03d}.txt"
        if file.exists():
            return file.read_text(encoding='utf-8')
        return ""
    
    def get_current_volume_summary(self, chapter_num: int) -> str:
        """获取当前卷的摘要"""
        vol = self._chapter_to_volume(chapter_num)
        return self.get_volume_summary(vol)
    
    def auto_generate_volume_summary(self, volume_num: int, ai_client=None):
        """自动生成卷级摘要（汇总该卷所有章节摘要）"""
        start_ch = (volume_num - 1) * self.VOLUME_SIZE + 1
        end_ch = volume_num * self.VOLUME_SIZE
        
        summaries = []
        for ch_num in range(start_ch, end_ch + 1):
            ch_sum = self.get_chapter_summary(ch_num)
            if ch_sum:
                summaries.append(f"第{ch_num}章: {ch_sum[:100]}")
        
        if not summaries:
            return ""
        
        # 简单拼接（如果有AI可以进一步压缩）
        summary = f"第{volume_num}卷 (第{start_ch}-{end_ch}章):\n" + "\n".join(summaries)
        self.save_volume_summary(volume_num, summary)
        return summary
    
    # ===== 弧线摘要管理 =====
    
    def save_arc_summary(self, arc_name: str, summary: str, chapters: List[int] = None):
        """保存弧线摘要"""
        safe_name = "".join(c for c in arc_name if c.isalnum() or c in "_ -")[:30]
        file = self.arcs_dir / f"arc_{safe_name}.json"
        data = {
            "name": arc_name,
            "summary": summary,
            "chapters": chapters or [],
            "updated_at": datetime.now().isoformat()
        }
        file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    
    def get_arc_summary(self, arc_name: str) -> str:
        """获取弧线摘要"""
        safe_name = "".join(c for c in arc_name if c.isalnum() or c in "_ -")[:30]
        file = self.arcs_dir / f"arc_{safe_name}.json"
        if file.exists():
            data = json.loads(file.read_text(encoding='utf-8'))
            return data.get("summary", "")
        return ""
    
    def get_all_arcs(self) -> List[Dict]:
        """获取所有弧线"""
        arcs = []
        for f in self.arcs_dir.glob("arc_*.json"):
            try:
                arcs.append(json.loads(f.read_text(encoding='utf-8')))
            except: pass
        return arcs
    
    # ===== 核心记忆保存 =====
    
    def save_global_summary(self, summary: str):
        with open(self.global_summary_file, 'w', encoding='utf-8') as f:
            f.write(summary)
    
    def get_global_summary(self) -> str:
        if self.global_summary_file.exists():
            return self.global_summary_file.read_text(encoding='utf-8')
        return ""
    
    def save_chapter_summary(self, chapter_num: int, summary: str):
        file = self.chapters_dir / f"chapter_{chapter_num:05d}.txt"
        with open(file, 'w', encoding='utf-8') as f:
            f.write(summary)
        # 更新倒排索引
        self._update_inverted_index(f"chapter_{chapter_num}", summary)
        # 更新记忆评分
        self._update_score(f"chapter_{chapter_num}", "summary", importance=8)
        # 检查是否需要自动生成卷级摘要
        if chapter_num % self.VOLUME_SIZE == 0:
            vol = self._chapter_to_volume(chapter_num)
            self.auto_generate_volume_summary(vol)
    
    def get_chapter_summary(self, chapter_num: int) -> str:
        file = self.chapters_dir / f"chapter_{chapter_num:05d}.txt"
        if file.exists():
            return file.read_text(encoding='utf-8')
        return ""
    
    def get_recent_summaries(self, count: int = 5) -> str:
        """获取最近N章的摘要"""
        chapters = sorted(self.chapters_dir.glob("chapter_*.txt"), reverse=True)
        summaries = []
        for ch in chapters[:count]:
            num_str = ch.stem.split("_")[1]
            content = ch.read_text(encoding='utf-8')
            summaries.append(f"第{num_str}章摘要：\n{content}")
            self._increment_reference(f"chapter_{num_str}")
        return "\n\n".join(reversed(summaries))
    
    def get_chapter_range_summary(self, start: int, end: int) -> str:
        """获取章节范围的摘要（分页加载）"""
        summaries = []
        for ch_num in range(start, min(end + 1, start + 50)):  # 最多50章
            ch_sum = self.get_chapter_summary(ch_num)
            if ch_sum:
                summaries.append(f"第{ch_num}章: {ch_sum[:80]}")
        return "\n".join(summaries) if summaries else ""
    
    # ===== 角色活跃度管理 =====
    
    def update_character_activity(self, char_name: str, chapter_num: int):
        """更新角色活跃度"""
        if char_name not in self._character_activity:
            self._character_activity[char_name] = {
                "appearances": [],
                "last_seen": chapter_num,
                "importance": 5
            }
        activity = self._character_activity[char_name]
        if chapter_num not in activity["appearances"]:
            activity["appearances"].append(chapter_num)
            # 只保留最近100次出场
            if len(activity["appearances"]) > 100:
                activity["appearances"] = activity["appearances"][-100:]
        activity["last_seen"] = chapter_num
        self._save_character_activity()
    
    def get_active_characters(self, chapter_num: int, window: int = 50) -> List[str]:
        """获取最近活跃的角色（按活跃度排序）"""
        active = []
        for name, activity in self._character_activity.items():
            last_seen = activity.get("last_seen", 0)
            if chapter_num - last_seen <= window:
                count = len([c for c in activity.get("appearances", []) if c >= chapter_num - window])
                active.append((name, count, last_seen))
        
        # 按出场次数排序
        active.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _, _ in active[:10]]  # 返回前10个活跃角色
    
    # ===== RAG检索 - 倒排索引优化 =====
    
    def _update_inverted_index(self, doc_id: str, content: str):
        """更新倒排索引"""
        keywords = self._extract_keywords(content)
        for kw in keywords:
            if kw not in self._inverted_index:
                self._inverted_index[kw] = []
            if doc_id not in self._inverted_index[kw]:
                self._inverted_index[kw].append(doc_id)
        # 定期保存（每100次更新保存一次）
        if len(self._inverted_index) % 100 == 0:
            self._save_inverted_index()
    
    def retrieve_relevant(self, query: str, top_k: int = 5) -> List[Dict]:
        """RAG检索：使用倒排索引快速查找
        
        使用倒排索引避免遍历所有chunks，支持百万级检索
        """
        query_keywords = set(self._extract_keywords(query))
        if not query_keywords:
            return []
        
        # 使用倒排索引快速找到候选文档
        candidate_ids = set()
        for kw in query_keywords:
            if kw in self._inverted_index:
                candidate_ids.update(self._inverted_index[kw])
        
        # 如果没有索引，降级为遍历章节摘要
        if not candidate_ids:
            return self._fallback_search(query_keywords, top_k)
        
        # 计算候选文档的相关性
        scored = []
        for doc_id in candidate_ids:
            content = self._get_document_content(doc_id)
            if content:
                chunk = {"id": doc_id, "content": content}
                score = self._calculate_relevance(chunk, query_keywords)
                if score > 0:
                    scored.append({**chunk, "relevance": score})
        
        scored.sort(key=lambda x: x["relevance"], reverse=True)
        top = scored[:top_k]
        
        for chunk in top:
            self._increment_reference(chunk.get("id", ""))
        
        return top
    
    def _fallback_search(self, query_keywords: set, top_k: int) -> List[Dict]:
        """降级搜索：遍历最近的章节摘要"""
        scored = []
        chapters = sorted(self.chapters_dir.glob("chapter_*.txt"), reverse=True)
        for ch_file in chapters[:200]:  # 只搜索最近200章
            try:
                content = ch_file.read_text(encoding='utf-8')
                doc_id = ch_file.stem
                chunk = {"id": doc_id, "content": content}
                score = self._calculate_relevance(chunk, query_keywords)
                if score > 0:
                    scored.append({**chunk, "relevance": score})
            except: pass
        
        scored.sort(key=lambda x: x["relevance"], reverse=True)
        return scored[:top_k]
    
    def _get_document_content(self, doc_id: str) -> str:
        """获取文档内容（支持不同类型的文档）"""
        # 章节摘要
        if doc_id.startswith("chapter_"):
            file = self.chapters_dir / f"{doc_id}.txt"
            if file.exists():
                return file.read_text(encoding='utf-8')
        # 卷级摘要
        elif doc_id.startswith("volume_"):
            file = self.volumes_dir / f"{doc_id}.txt"
            if file.exists():
                return file.read_text(encoding='utf-8')
        # 弧线摘要
        elif doc_id.startswith("arc_"):
            file = self.arcs_dir / f"{doc_id}.json"
            if file.exists():
                data = json.loads(file.read_text(encoding='utf-8'))
                return data.get("summary", "")
        return ""
    
    def _calculate_relevance(self, chunk: Dict, query_keywords: set) -> float:
        """计算记忆块与查询的相关性分数"""
        content = chunk.get("content", "")
        content_keywords = set(self._extract_keywords(content))
        
        # 关键词匹配得分
        overlap = query_keywords & content_keywords
        keyword_score = len(overlap) / max(len(query_keywords), 1)
        
        # 新鲜度得分（指数衰减，7天半衰期）
        created = chunk.get("created_at", "")
        freshness = self._calc_freshness(created)
        
        # 重要性得分
        importance = chunk.get("importance", 5) / 10.0
        
        # 引用得分
        ref_count = self._scores.get(chunk.get("id", ""), {}).get("references", 0)
        ref_score = min(ref_count / 10.0, 1.0)
        
        # 加权计算
        weights = {"keyword": 0.40, "freshness": 0.20, "importance": 0.30, "ref": 0.10}
        total = (
            keyword_score * weights["keyword"] +
            freshness * weights["freshness"] +
            importance * weights["importance"] +
            ref_score * weights["ref"]
        )
        
        return round(total, 4)
    
    def _calc_freshness(self, created_at: str) -> float:
        """计算新鲜度得分（指数衰减）"""
        if not created_at:
            return 0.5
        try:
            created = datetime.fromisoformat(created_at)
            days_ago = (datetime.now() - created).days
            # 7天半衰期
            return 2 ** (-days_ago / 7)
        except:
            return 0.5
    
    # ===== 记忆块（Chunks）分页管理 =====
    
    def _get_chunks_page(self, page: int, page_size: int = 100) -> List[Dict]:
        """获取指定页的chunks（分页加载）"""
        page_file = self.chunks_dir / f"page_{page:04d}.json"
        if page_file.exists():
            try:
                return json.loads(page_file.read_text(encoding='utf-8'))
            except: pass
        return []
    
    def _save_chunks_page(self, page: int, chunks: List[Dict]):
        """保存指定页的chunks"""
        page_file = self.chunks_dir / f"page_{page:04d}.json"
        page_file.write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding='utf-8')
    
    def _get_total_chunk_count(self) -> int:
        """获取chunks总数"""
        pages = list(self.chunks_dir.glob("page_*.json"))
        if not pages:
            return 0
        last_page = sorted(pages)[-1]
        try:
            chunks = json.loads(last_page.read_text(encoding='utf-8'))
            return (len(pages) - 1) * 100 + len(chunks)
        except:
            return 0
    
    def add_chunk(self, chunk_type: str, content: str, importance: int = 5, 
                  tags: List[str] = None, related_to: List[str] = None):
        """添加记忆块（分页存储）"""
        # 去重检查（只检查最近几页）
        existing = self._find_similar_chunk(content)
        if existing:
            self._merge_chunk(existing["id"], content, tags)
            return existing["id"]
        
        chunk = {
            "id": f"{chunk_type}_{int(time.time() * 1000)}",
            "type": chunk_type,
            "content": content,
            "importance": importance,
            "tags": tags or [],
            "related_to": related_to or [],
            "created_at": datetime.now().isoformat(),
            "references": 0,
        }
        
        # 找到当前页
        total = self._get_total_chunk_count()
        current_page = total // 100
        page_chunks = self._get_chunks_page(current_page)
        page_chunks.append(chunk)
        self._save_chunks_page(current_page, page_chunks)
        
        # 更新倒排索引
        self._update_inverted_index(chunk["id"], content)
        self._update_score(chunk["id"], chunk_type, importance)
        
        return chunk["id"]
    
    def _find_similar_chunk(self, content: str, threshold: float = 0.7) -> Optional[Dict]:
        """查找相似的记忆块（只检查最近几页）"""
        content_keywords = set(self._extract_keywords(content))
        if not content_keywords:
            return None
        
        # 只检查最近3页（300个chunks）
        total = self._get_total_chunk_count()
        max_page = total // 100
        for page in range(max(0, max_page - 2), max_page + 1):
            for chunk in self._get_chunks_page(page):
                chunk_keywords = set(self._extract_keywords(chunk.get("content", "")))
                if not chunk_keywords:
                    continue
                overlap = len(content_keywords & chunk_keywords)
                similarity = overlap / min(len(content_keywords), len(chunk_keywords))
                if similarity > threshold:
                    return chunk
        return None
    
    def _merge_chunk(self, chunk_id: str, new_content: str, new_tags: List[str] = None):
        """合并记忆块"""
        # 查找chunk所在的页
        total = self._get_total_chunk_count()
        max_page = total // 100
        for page in range(max_page + 1):
            page_chunks = self._get_chunks_page(page)
            for chunk in page_chunks:
                if chunk["id"] == chunk_id:
                    if new_content not in chunk["content"]:
                        chunk["content"] += f"\n\n[更新]\n{new_content}"
                    if new_tags:
                        chunk["tags"] = list(set(chunk.get("tags", []) + new_tags))
                    chunk["updated_at"] = datetime.now().isoformat()
                    self._save_chunks_page(page, page_chunks)
                    return
        self._save_inverted_index()
    
    def _update_score(self, doc_id: str, doc_type: str, importance: int = 5):
        """更新记忆评分"""
        if doc_id not in self._scores:
            self._scores[doc_id] = {"type": doc_type, "importance": importance, "references": 0, "created": datetime.now().isoformat()}
        else:
            self._scores[doc_id]["importance"] = max(self._scores[doc_id].get("importance", 5), importance)
        self._save_scores()
    
    def _increment_reference(self, doc_id: str):
        """增加引用计数"""
        if doc_id not in self._scores:
            self._scores[doc_id] = {"references": 0}
        self._scores[doc_id]["references"] = self._scores[doc_id].get("references", 0) + 1
    
    # ===== 事件时间线（分页存储）=====
    
    def _get_timeline_page(self, chapter_num: int) -> int:
        """章节号转时间线页码（每100章一页）"""
        return (chapter_num - 1) // 100
    
    def add_event(self, chapter_num: int, event: str, event_type: str = "story", 
                  characters_involved: List[str] = None):
        """添加事件到时间线（分页存储）"""
        page = self._get_timeline_page(chapter_num)
        page_file = self.timeline_dir / f"timeline_{page:03d}.json"
        
        events = []
        if page_file.exists():
            try:
                events = json.loads(page_file.read_text(encoding='utf-8'))
            except: pass
        
        events.append({
            "chapter": chapter_num,
            "event": event,
            "type": event_type,
            "characters": characters_involved or [],
            "timestamp": datetime.now().isoformat(),
        })
        
        page_file.write_text(json.dumps(events, ensure_ascii=False, indent=1), encoding='utf-8')
    
    def get_timeline(self, from_chapter: int = 0, to_chapter: int = None) -> List[Dict]:
        """获取时间线（按范围加载）"""
        if to_chapter is None:
            to_chapter = from_chapter + 200 if from_chapter > 0 else 999999
        
        all_events = []
        start_page = self._get_timeline_page(from_chapter)
        end_page = self._get_timeline_page(to_chapter)
        
        for page in range(start_page, end_page + 1):
            page_file = self.timeline_dir / f"timeline_{page:03d}.json"
            if page_file.exists():
                try:
                    events = json.loads(page_file.read_text(encoding='utf-8'))
                    for e in events:
                        ch = e.get("chapter", 0)
                        if from_chapter <= ch <= to_chapter:
                            all_events.append(e)
                except: pass
        
        return sorted(all_events, key=lambda e: (e.get("chapter", 0), e.get("timestamp", "")))
    
    # ===== 角色档案和关系图 =====
    
    def save_characters(self, characters: dict):
        with open(self.characters_file, 'w', encoding='utf-8') as f:
            json.dump(characters, f, indent=2, ensure_ascii=False)
    
    def get_characters(self) -> dict:
        if self.characters_file.exists():
            with open(self.characters_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def update_character(self, name: str, data: dict):
        """更新角色信息，自动检测关系变化"""
        characters = self.get_characters()
        
        old_data = characters.get(name, {})
        
        # 合并更新
        if isinstance(old_data, dict) and isinstance(data, dict):
            old_data.update(data)
            characters[name] = old_data
        else:
            characters[name] = data
        
        self.save_characters(characters)
        
        # 检测关系变化并记录
        if "relationships" in data:
            for rel_name, rel_type in data["relationships"].items():
                self.add_event(
                    chapter_num=0,
                    event=f"角色关系更新: {name} ↔ {rel_name} ({rel_type})",
                    event_type="character",
                    characters_involved=[name, rel_name]
                )
    
    # ===== 记忆评分和衰减 =====
    
    def _update_score(self, item_id: str, item_type: str, importance: int = 5):
        """更新记忆评分"""
        if item_id not in self._scores:
            self._scores[item_id] = {
                "type": item_type,
                "importance": importance,
                "references": 0,
                "created_at": datetime.now().isoformat(),
            }
        self._scores[item_id]["importance"] = max(
            self._scores[item_id].get("importance", 5), importance
        )
        self._save_scores()
    
    def _increment_reference(self, item_id: str):
        """增加引用计数"""
        if item_id not in self._scores:
            self._scores[item_id] = {"type": "unknown", "importance": 5, "references": 0,
                                      "created_at": datetime.now().isoformat()}
        self._scores[item_id]["references"] = self._scores[item_id].get("references", 0) + 1
        self._scores[item_id]["last_referenced"] = datetime.now().isoformat()
        self._save_scores()
    
    def _save_scores(self):
        with open(self.scores_file, 'w', encoding='utf-8') as f:
            json.dump(self._scores, f, indent=2, ensure_ascii=False)
    
    def _load_scores(self) -> dict:
        if self.scores_file.exists():
            with open(self.scores_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    # ===== 记忆健康检查 =====
    
    def health_check(self) -> Dict:
        """检查记忆系统的健康状况
        
        参考Supermemory的质量控制思路：
        1. 检测矛盾信息
        2. 检测衰减严重的记忆
        3. 检测孤立记忆（无关联）
        4. 统计记忆状态
        """
        total_chunks = self._get_total_chunk_count()
        total_chapters = len(list(self.chapters_dir.glob("chapter_*.txt")))
        total_volumes = len(list(self.volumes_dir.glob("volume_*.txt")))
        
        report = {
            "total_chunks": total_chunks,
            "total_chapters": total_chapters,
            "total_volumes": total_volumes,
            "total_characters": len(self.get_characters()),
            "total_arcs": len(list(self.arcs_dir.glob("arc_*.json"))),
            "stale_chunks": [],
            "orphan_chunks": [],
            "recommendations": [],
        }
        
        # 检测衰减（只检查最近几页）
        total = self._get_total_chunk_count()
        max_page = total // 100
        for page in range(max(0, max_page - 2), max_page + 1):
            for chunk in self._get_chunks_page(page):
                score = self._scores.get(chunk.get("id", ""), {})
                refs = score.get("references", 0)
                created = score.get("created_at", "")
                freshness = self._calc_freshness(created)
                if freshness < 0.2 and refs < 2:
                    report["stale_chunks"].append({
                        "id": chunk["id"],
                        "type": chunk.get("type", ""),
                        "freshness": round(freshness, 3),
                    })
        
        # 生成建议
        if report["stale_chunks"]:
            report["recommendations"].append(f"有 {len(report['stale_chunks'])} 条记忆已衰减")
        if total_chunks > 5000:
            report["recommendations"].append("记忆块超过5000个，建议归档旧章节记忆")
        if total_chapters > 100 and total_volumes == 0:
            report["recommendations"].append(f"已有{total_chapters}章但无卷级摘要，建议生成卷级摘要")
        
        return report
    
    # ===== 关键词提取和搜索 =====
    
    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """提取关键词（简易分词）"""
        # 中文常见停用词
        stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
                     '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有',
                     '看', '好', '自己', '这', '他', '她', '它', '们', '那', '被', '把',
                     '可以', '这个', '那个', '什么', '怎么', '因为', '所以', '但是', '然后'}
        
        # 提取2-4字词组
        keywords = []
        cleaned = ''
        for c in text:
            if '\u4e00' <= c <= '\u9fff' or c.isalnum():
                cleaned += c
            else:
                cleaned += ' '
        
        # 提取词组
        for i in range(len(cleaned)):
            for l in [2, 3, 4]:
                if i + l <= len(cleaned):
                    word = cleaned[i:i+l]
                    if word not in stopwords and all('\u4e00' <= c <= '\u9fff' for c in word):
                        keywords.append(word)
        
        # 去重并排序
        from collections import Counter
        counted = Counter(keywords)
        return [word for word, _ in counted.most_common(30)]
    
    def get_settings(self) -> dict:
        if self.settings_file.exists():
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def save_settings(self, settings: dict):
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    
    def update_index(self, chapter_num: int, keywords: List[str]):
        index = self._load_index()
        index[str(chapter_num)] = keywords
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
    
    def search_by_keyword(self, keyword: str) -> List[int]:
        index = self._load_index()
        results = []
        for ch_num, keywords in index.items():
            if keyword in keywords:
                results.append(int(ch_num))
        return sorted(results)
    
    def _load_index(self) -> dict:
        if self.index_file.exists():
            with open(self.index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    # ===== 智能上下文构建 =====
    
    def build_smart_context(self, chapter_num: int, query: str = "",
                            max_items: int = 10) -> str:
        """智能构建上下文 - 核心RAG方法
        
        优先级排序：
        1. 当前查询相关的记忆块（RAG检索）
        2. 最近章节的事件时间线
        3. 高频引用的角色信息
        4. 世界观设定
        """
        parts = []
        
        # 1. RAG检索相关记忆
        if query:
            relevant = self.retrieve_relevant(query, top_k=5)
            if relevant:
                items = []
                for r in relevant:
                    items.append(f"[{r.get('type', '')}|相关性{r.get('relevance', 0):.2f}] {r.get('content', '')[:200]}")
                parts.append(f"【相关记忆】\n" + "\n\n".join(items))
        
        # 2. 最近时间线事件（使用分页加载）
        recent_events = self.get_timeline(from_chapter=max(1, chapter_num - 5), to_chapter=chapter_num)
        if recent_events:
            event_lines = []
            for e in recent_events[-10:]:
                event_lines.append(f"第{e.get('chapter', 0)}章: {e.get('event', '')}")
            parts.append(f"【故事时间线（最近）】\n" + "\n".join(event_lines))
        
        # 3. 活跃角色（按活跃度排序）
        characters = self.get_characters()
        if characters:
            active_names = self.get_active_characters(chapter_num, window=50)
            char_lines = []
            for name in active_names[:5]:
                if name in characters:
                    info = characters[name]
                    if isinstance(info, dict):
                        char_lines.append(f"- {name}: {info.get('personality', '')[:50]}")
                    else:
                        char_lines.append(f"- {name}: {str(info)[:50]}")
            if not char_lines:
                # 降级到引用次数排序
                for name, info in list(characters.items())[:5]:
                    if isinstance(info, dict):
                        char_lines.append(f"- {name}: {info.get('personality', '')[:50]}")
                    else:
                        char_lines.append(f"- {name}: {str(info)[:50]}")
            if char_lines:
                parts.append(f"【活跃角色】\n" + "\n".join(char_lines))
        
        # 4. 世界观
        settings = self.get_settings()
        if settings:
            settings_text = json.dumps(settings, ensure_ascii=False, indent=2)[:500]
            parts.append(f"【世界观】\n{settings_text}")
        
        return "\n\n---\n\n".join(parts)


# ==================== 笔记管理器 ====================

class NoteManager:
    """笔记管理器 - 文档笔记、工程笔记、便笺本"""
    
    def __init__(self, novel_dir: Optional[Path] = None, config: Optional[AppConfig] = None):
        self.novel_dir = novel_dir
        self.config = config
        
        # 便笺本（全局共享）
        if config:
            self.sticky_file = config.config_dir / "sticky_notes.json"
        else:
            self.sticky_file = Path.home() / ".ai_novel_writer" / "sticky_notes.json"
        
        # 工程笔记和文档笔记在 novel_dir 下
        if novel_dir:
            self.notes_dir = novel_dir / "notes"
            self.notes_dir.mkdir(exist_ok=True)
            self.project_note_file = self.notes_dir / "_project_notes.json"
            self.doc_notes_dir = self.notes_dir / "docs"
            self.doc_notes_dir.mkdir(exist_ok=True)
    
    # ===== 便笺本（全局）=====
    
    def get_sticky_notes(self) -> List[Dict]:
        if self.sticky_file.exists():
            with open(self.sticky_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def save_sticky_notes(self, notes: List[Dict]):
        with open(self.sticky_file, 'w', encoding='utf-8') as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)
    
    def add_sticky_note(self, content: str, tags: List[str] = None) -> Dict:
        notes = self.get_sticky_notes()
        note = {
            "id": int(time.time() * 1000),
            "content": content,
            "tags": tags or [],
            "created_at": datetime.now().isoformat(),
        }
        notes.append(note)
        self.save_sticky_notes(notes)
        return note
    
    def delete_sticky_note(self, note_id: int):
        notes = self.get_sticky_notes()
        notes = [n for n in notes if n.get("id") != note_id]
        self.save_sticky_notes(notes)
    
    # ===== 工程笔记 =====
    
    def get_project_notes(self) -> List[Dict]:
        if not self.novel_dir:
            return []
        if self.project_note_file.exists():
            with open(self.project_note_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def save_project_notes(self, notes: List[Dict]):
        if not self.novel_dir:
            return
        with open(self.project_note_file, 'w', encoding='utf-8') as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)
    
    def add_project_note(self, title: str, content: str) -> Dict:
        notes = self.get_project_notes()
        note = {
            "id": int(time.time() * 1000),
            "title": title,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        notes.append(note)
        self.save_project_notes(notes)
        return note
    
    def update_project_note(self, note_id: int, title: str = None, content: str = None):
        notes = self.get_project_notes()
        for n in notes:
            if n.get("id") == note_id:
                if title is not None:
                    n["title"] = title
                if content is not None:
                    n["content"] = content
                n["updated_at"] = datetime.now().isoformat()
                break
        self.save_project_notes(notes)
    
    def delete_project_note(self, note_id: int):
        notes = self.get_project_notes()
        notes = [n for n in notes if n.get("id") != note_id]
        self.save_project_notes(notes)
    
    # ===== 文档笔记 =====
    
    def get_doc_notes(self, chapter_num: int) -> List[Dict]:
        if not self.novel_dir:
            return []
        note_file = self.doc_notes_dir / f"chapter_{chapter_num:04d}.json"
        if note_file.exists():
            with open(note_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def save_doc_notes(self, chapter_num: int, notes: List[Dict]):
        if not self.novel_dir:
            return
        note_file = self.doc_notes_dir / f"chapter_{chapter_num:04d}.json"
        with open(note_file, 'w', encoding='utf-8') as f:
            json.dump(notes, f, indent=2, ensure_ascii=False)
    
    def add_doc_note(self, chapter_num: int, content: str, position: int = 0) -> Dict:
        notes = self.get_doc_notes(chapter_num)
        note = {
            "id": int(time.time() * 1000),
            "content": content,
            "position": position,
            "created_at": datetime.now().isoformat(),
        }
        notes.append(note)
        self.save_doc_notes(chapter_num, notes)
        return note
    
    def delete_doc_note(self, chapter_num: int, note_id: int):
        notes = self.get_doc_notes(chapter_num)
        notes = [n for n in notes if n.get("id") != note_id]
        self.save_doc_notes(chapter_num, notes)
    
    # ===== 便笺发送到工程 =====
    
    def send_sticky_to_project(self, note_id: int, target: str = "project"):
        """将便笺内容发送到工程笔记"""
        sticky_notes = self.get_sticky_notes()
        note = None
        for n in sticky_notes:
            if n.get("id") == note_id:
                note = n
                break
        if note and self.novel_dir:
            self.add_project_note(
                title=f"来自便笺 - {note['content'][:20]}",
                content=note["content"]
            )


# ==================== 全屏写作窗口 ====================

class FullscreenWriter:
    """全屏沉浸式写作窗口"""
    
    def __init__(self, parent, ai_client: AIClient, config: AppConfig, 
                 initial_text: str = "", save_callback=None, shared_context: str = ""):
        self.parent = parent
        self.ai = ai_client
        self.config = config
        self.save_callback = save_callback
        self.text_content = initial_text
        self.shared_context = shared_context  # 共享上下文（世界观、角色、大纲等）
        
        # 写作设置
        self.font_size = 18
        self.paper_width = 700
        self.paper_position = "center"  # center / left / right
        self.bg_opacity = 0.85
        self.typewriter_mode = True  # 打字机模式
        self.ai_assist_enabled = True
        
        # AI续写相关
        self.ai_suggestion = ""
        self.suggestion_active = False
        
        # 创建窗口
        self.win = tk.Toplevel(parent)
        self.win.title("全屏写作")
        self.win.attributes('-fullscreen', True)
        self.win.configure(bg='#1a1a2e')
        
        self._create_widgets()
        self._bind_events()
        
        # 加载设置
        self._load_writer_settings()
    
    def _create_widgets(self):
        """创建全屏写作界面"""
        C = UIStyle.COLORS
        
        # 顶部工具栏
        self.toolbar = tk.Frame(self.win, bg='#16213e', height=40)
        self.toolbar.pack(fill=tk.X)
        self.toolbar.pack_propagate(False)
        
        # 左侧按钮
        left_btns = tk.Frame(self.toolbar, bg='#16213e')
        left_btns.pack(side=tk.LEFT, padx=15, fill=tk.Y)
        
        tk.Button(left_btns, text="退出 (Esc)", font=('微软雅黑', 9),
                 bg='#e74c3c', fg='white', relief=tk.FLAT, padx=10,
                 command=self._exit_fullscreen).pack(side=tk.LEFT, pady=5)
        tk.Button(left_btns, text="保存", font=('微软雅黑', 9),
                 bg='#27ae60', fg='white', relief=tk.FLAT, padx=10,
                 command=self._save).pack(side=tk.LEFT, padx=8, pady=5)
        
        # AI功能按钮区
        ai_btns = tk.Frame(self.toolbar, bg='#16213e')
        ai_btns.pack(side=tk.LEFT, padx=20, fill=tk.Y)
        
        tk.Label(ai_btns, text="AI辅助:", font=('微软雅黑', 9),
                bg='#16213e', fg='#a78bfa').pack(side=tk.LEFT, pady=5)
        
        ai_features = [
            ("续写 (Tab)", self._ai_continue, '#7c3aed'),
            ("扩写", self._ai_expand, '#3b82f6'),
            ("简写", self._ai_compress, '#f59e0b'),
            ("润色", self._ai_polish, '#10b981'),
            ("改写", self._ai_rewrite, '#ef4444'),
            ("对话", self._ai_dialogue, '#8b5cf6'),
        ]
        
        for text, cmd, color in ai_features:
            tk.Button(ai_btns, text=text, font=('微软雅黑', 8),
                     bg=color, fg='white', relief=tk.FLAT, padx=8, pady=3,
                     cursor='hand2', activebackground=color,
                     command=cmd).pack(side=tk.LEFT, padx=2, pady=5)
        
        # 右侧控件
        right_ctrls = tk.Frame(self.toolbar, bg='#16213e')
        right_ctrls.pack(side=tk.RIGHT, padx=15, fill=tk.Y)
        
        # 打字机模式
        self.tw_var = tk.BooleanVar(value=self.typewriter_mode)
        tk.Checkbutton(right_ctrls, text="打字机", variable=self.tw_var,
                      font=('微软雅黑', 9), bg='#16213e', fg='#94a3b8',
                      selectcolor='#7c3aed', activebackground='#16213e',
                      command=self._toggle_typewriter).pack(side=tk.LEFT, pady=5)
        
        # 字数统计
        self.word_count_label = tk.Label(right_ctrls, text="字数: 0",
                                        font=('微软雅黑', 9), bg='#16213e', fg='#94a3b8')
        self.word_count_label.pack(side=tk.LEFT, padx=15, pady=5)
        
        # 设置按钮
        tk.Button(right_ctrls, text="设置", font=('微软雅黑', 9),
                 bg='#353548', fg='#94a3b8', relief=tk.FLAT, padx=10,
                 command=self._show_writer_settings).pack(side=tk.LEFT, pady=5)
        
        # 背景层
        self.bg_frame = tk.Frame(self.win, bg='#1a1a2e')
        self.bg_frame.pack(fill=tk.BOTH, expand=True)
        
        # 纸张容器（用于控制位置）
        self.paper_container = tk.Frame(self.bg_frame, bg='#1a1a2e')
        self.paper_container.pack(fill=tk.BOTH, expand=True, padx=50, pady=20)
        
        # 纸张
        self.paper = tk.Frame(self.paper_container, bg='#f5f0e8', 
                             width=self.paper_width, relief=tk.FLAT)
        
        # 内边距
        self.inner_frame = tk.Frame(self.paper, bg='#f5f0e8')
        self.inner_frame.pack(fill=tk.BOTH, expand=True, padx=60, pady=40)
        
        # Markdown工具栏
        md_toolbar = tk.Frame(self.inner_frame, bg='#f5f0e8')
        md_toolbar.pack(fill=tk.X, pady=(0, 5))
        
        md_btns = [
            ("H1", "heading1", "# "), ("H2", "heading2", "## "), ("H3", "heading3", "### "),
            ("B", "bold", "**"), ("I", "italic", "*"), ("S", "strike", "~~"),
            ("•", "list", "- "), ("1.", "olist", "1. "), (">", "quote", "> "),
            ("—", "hr", "\n---\n"), ("`", "code", "`"), ("```", "codeblock", "```\n"),
        ]
        
        for text, name, prefix in md_btns:
            btn = tk.Button(md_toolbar, text=text, font=('Consolas', 9, 'bold'),
                          bg='#e8e3d8', fg='#5c5647', relief=tk.FLAT,
                          padx=6, pady=2, cursor='hand2',
                          activebackground='#d4cfc4',
                          command=lambda p=prefix, n=name: self._insert_markdown(p, n))
            btn.pack(side=tk.LEFT, padx=1)
        
        # Markdown预览开关
        self.preview_var = tk.BooleanVar(value=False)
        tk.Checkbutton(md_toolbar, text="预览", variable=self.preview_var,
                      font=('微软雅黑', 8), bg='#f5f0e8', fg='#5c5647',
                      selectcolor='#7c3aed',
                      command=self._toggle_preview).pack(side=tk.RIGHT, padx=5)
        
        # 写作区域容器（编辑+预览）
        self.text_container = tk.Frame(self.inner_frame, bg='#f5f0e8')
        self.text_container.pack(fill=tk.BOTH, expand=True)
        
        # 写作区域
        self.text_widget = tk.Text(
            self.text_container,
            wrap=tk.WORD,
            font=("Consolas", self.font_size),
            bg='#f5f0e8',
            fg='#2c2c2c',
            insertbackground='#e74c3c',
            insertwidth=3,
            relief=tk.FLAT,
            padx=20,
            pady=20,
            spacing1=2,
            spacing3=2,
            selectbackground='#3498db',
            undo=True,
        )
        self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 预览区域（默认隐藏）
        self.preview_widget = tk.Text(
            self.text_container,
            wrap=tk.WORD,
            font=("微软雅黑", self.font_size),
            bg='#ffffff',
            fg='#2c2c2c',
            relief=tk.FLAT,
            padx=20,
            pady=20,
            state=tk.DISABLED,
        )
        # 预览默认不显示
        
        # 配置Markdown语法高亮
        self._setup_markdown_highlighting()
        
        # 加载初始内容
        if self.text_content:
            self.text_widget.insert("1.0", self.text_content)
        
        # AI续写提示标签
        self.suggestion_label = tk.Label(
            self.inner_frame, text="", font=("微软雅黑", self.font_size),
            fg='#999999', bg='#f5f0e8', anchor=tk.W, justify=tk.LEFT
        )
        
        # AI处理状态标签
        self.ai_status_label = tk.Label(
            self.inner_frame, text="", font=("微软雅黑", 12),
            fg='#f59e0b', bg='#f5f0e8', anchor=tk.CENTER
        )
        
        # 右键菜单
        self.context_menu = tk.Menu(self.text_widget, tearoff=0, 
                                   font=('微软雅黑', 10),
                                   bg='#2d2d3f', fg='#f8fafc',
                                   activebackground='#7c3aed',
                                   activeforeground='white')
        self.context_menu.add_command(label="AI续写 (Tab)", command=self._ai_continue)
        self.context_menu.add_command(label="AI扩写", command=self._ai_expand)
        self.context_menu.add_command(label="AI简写", command=self._ai_compress)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="AI润色", command=self._ai_polish)
        self.context_menu.add_command(label="AI改写", command=self._ai_rewrite)
        self.context_menu.add_command(label="AI生成对话", command=self._ai_dialogue)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="撤销 (Ctrl+Z)", command=lambda: self.text_widget.edit_undo())
        self.context_menu.add_command(label="重做 (Ctrl+Y)", command=lambda: self.text_widget.edit_redo())
        
        self.text_widget.bind("<Button-3>", self._show_context_menu)
        
        # 底部状态栏
        self.status_bar = tk.Frame(self.win, bg='#16213e')
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.status_label = ttk.Label(self.status_bar, text="AI辅助: 开启 | 打字机模式: 开启", 
                                      background='#16213e', foreground='white')
        self.status_label.pack(side=tk.LEFT, padx=20, pady=5)
        
        self._update_paper_position()
    
    def _bind_events(self):
        """绑定事件"""
        self.win.bind('<Escape>', lambda e: self._exit_fullscreen())
        self.win.bind('<Control-s>', lambda e: self._save())
        self.win.bind('<Control-z>', lambda e: self.text_widget.edit_undo())
        self.win.bind('<Control-y>', lambda e: self.text_widget.edit_redo())
        
        # AI功能快捷键
        self.win.bind('<Control-e>', lambda e: self._ai_expand())   # Ctrl+E 扩写
        self.win.bind('<Control-q>', lambda e: self._ai_compress()) # Ctrl+Q 简写
        self.win.bind('<Control-r>', lambda e: self._ai_rewrite())  # Ctrl+R 改写
        self.win.bind('<Control-p>', lambda e: self._ai_polish())   # Ctrl+P 润色
        
        # Markdown快捷键
        self.win.bind('<Control-b>', lambda e: self._insert_markdown('**', 'bold'))     # Ctrl+B 加粗
        self.win.bind('<Control-i>', lambda e: self._insert_markdown('*', 'italic'))    # Ctrl+I 斜体
        self.win.bind('<Control-`>', lambda e: self._insert_markdown('`', 'code'))      # Ctrl+` 代码
        self.win.bind('<Control-l>', lambda e: self._insert_markdown('- ', 'list'))     # Ctrl+L 列表
        self.win.bind('<Control-Shift-P>', lambda e: self._toggle_preview())            # Ctrl+Shift+P 预览
        
        # 按键事件 - 用于打字机模式和AI辅助
        self.text_widget.bind('<KeyRelease>', self._on_key_release)
        self.text_widget.bind('<Tab>', self._on_tab)
        
        # 字体大小调整
        self.win.bind('<Control-plus>', lambda e: self._change_font_size(1))
        self.win.bind('<Control-minus>', lambda e: self._change_font_size(-1))
        self.win.bind('<Control-equal>', lambda e: self._change_font_size(1))
    
    def _show_context_menu(self, event):
        """显示右键菜单"""
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
    
    def _on_key_release(self, event=None):
        """按键释放事件 - 打字机模式+字数统计+Markdown高亮"""
        content = self.text_widget.get("1.0", tk.END).strip()
        self.word_count_label.config(text=f"字数: {len(content)}")
        
        if self.typewriter_mode:
            self._center_current_line()
        
        if self.suggestion_active and event and event.keysym not in ('Tab', 'Shift_L', 'Shift_R', 'Control_L', 'Control_R'):
            self._clear_suggestion()
        
        # Markdown高亮（延迟更新避免频繁触发）
        if hasattr(self, '_highlight_after_id'):
            self.win.after_cancel(self._highlight_after_id)
        self._highlight_after_id = self.win.after(300, self._update_markdown_highlighting)
    
    def _on_tab(self, event):
        """Tab键接受AI建议"""
        if self.suggestion_active and self.ai_suggestion:
            # 插入AI建议
            self.text_widget.insert(tk.INSERT, self.ai_suggestion)
            self._clear_suggestion()
            return "break"  # 阻止默认Tab行为
        
        # 如果没有建议，触发AI续写
        if self.ai_assist_enabled:
            self._trigger_ai_suggestion()
        return "break"
    
    def _trigger_ai_suggestion(self):
        """触发AI续写建议 - 使用共享上下文"""
        if not self.ai.is_configured():
            return
        
        current_text = self.text_widget.get("1.0", tk.END).strip()
        if not current_text:
            return
        
        context = current_text[-500:]
        system = "你是一位小说写作助手。请根据用户正在写的内容，续写20-50字。直接输出续写内容，不要添加任何说明。保持风格和语气一致。"
        if self.shared_context:
            system += f"\n\n小说背景信息（供参考，保持一致性）：\n{self.shared_context[:1000]}"
        
        def generate():
            try:
                response = self.ai.chat(
                    [{"role": "user", "content": f"请续写以下内容：\n\n{context}"}],
                    system=system,
                    max_tokens=200,
                    temperature=0.8
                )
                
                self.ai_suggestion = response.strip()[:100]  # 限制长度
                self.suggestion_active = True
                
                # 在主线程显示建议
                self.win.after(0, self._show_suggestion)
            except Exception as e:
                print(f"AI续写失败: {e}")
        
        threading.Thread(target=generate, daemon=True).start()
    
    def _show_suggestion(self):
        """显示AI建议（灰色提示文字）"""
        if self.ai_suggestion:
            # 在光标位置后显示灰色提示
            cursor_pos = self.text_widget.index(tk.INSERT)
            self.suggestion_label.config(text=self.ai_suggestion)
            self.suggestion_label.place(in_=self.text_widget, relx=0, rely=1.0, anchor=tk.NW)
    
    def _clear_suggestion(self):
        """清除AI建议"""
        self.ai_suggestion = ""
        self.suggestion_active = False
        self.suggestion_label.place_forget()
    
    def _center_current_line(self):
        """打字机模式 - 当前行居中"""
        try:
            # 获取光标位置
            cursor_line = self.text_widget.index(tk.INSERT).split('.')[0]
            
            # 获取文本框高度
            self.text_widget.update_idletasks()
            widget_height = self.text_widget.winfo_height()
            
            # 计算当前行在文本中的位置
            line_y = self.text_widget.dlineinfo(f"{cursor_line}.0")
            if line_y:
                # 计算滚动位置，使当前行居中
                total_lines = int(self.text_widget.index(tk.END).split('.')[0])
                target_pos = (int(cursor_line) - widget_height / (self.font_size * 2)) / total_lines
                target_pos = max(0, min(1, target_pos))
                self.text_widget.yview_moveto(target_pos)
        except:
            pass
    
    def _change_font_size(self, delta):
        """调整字体大小"""
        self.font_size = max(12, min(36, self.font_size + delta))
        self.text_widget.configure(font=("微软雅黑", self.font_size))
    
    def _toggle_ai(self):
        """切换AI辅助"""
        self.ai_assist_enabled = not self.ai_assist_enabled
        self._update_status()
    
    def _toggle_typewriter(self):
        """切换打字机模式"""
        self.typewriter_mode = self.tw_var.get()
        self._update_status()
    
    def _update_status(self):
        """更新状态栏"""
        ai_status = "开启" if self.ai_assist_enabled else "关闭"
        tw_status = "开启" if self.typewriter_mode else "关闭"
        self.status_label.config(text=f"AI辅助: {ai_status} | 打字机模式: {tw_status}")
    
    def _update_paper_position(self):
        """更新纸张位置"""
        self.paper_container.pack_forget()
        
        if self.paper_position == "center":
            self.paper_container.pack(fill=tk.BOTH, expand=True, padx=50, pady=20)
            self.paper.pack(anchor=tk.CENTER, expand=True)
        elif self.paper_position == "left":
            self.paper_container.pack(fill=tk.BOTH, expand=True, padx=(50, 100), pady=20)
            self.paper.pack(anchor=tk.W)
        elif self.paper_position == "right":
            self.paper_container.pack(fill=tk.BOTH, expand=True, padx=(100, 50), pady=20)
            self.paper.pack(anchor=tk.E)
        
        self.paper.configure(width=self.paper_width)
    
    def _ai_expand(self):
        """AI扩写 - 将选中文本或当前段落扩展为更详细的内容"""
        self._ai_transform("expand")
    
    def _ai_compress(self):
        """AI简写 - 将选中文本精简压缩"""
        self._ai_transform("compress")
    
    def _ai_continue(self):
        """AI续写 - 继续写下去（Tab键功能）"""
        if self.suggestion_active and self.ai_suggestion:
            self.text_widget.insert(tk.INSERT, self.ai_suggestion)
            self._clear_suggestion()
        else:
            self._trigger_ai_suggestion()
    
    def _ai_polish(self):
        """AI润色 - 优化语言表达"""
        self._ai_transform("polish")
    
    def _ai_rewrite(self):
        """AI改写 - 重新表达相同内容"""
        self._ai_transform("rewrite")
    
    def _ai_dialogue(self):
        """AI生成对话 - 根据上下文生成角色对话"""
        self._ai_transform("dialogue")
    
    def _ai_transform(self, mode: str):
        """AI文本变换通用方法"""
        if not self.ai.is_configured():
            return
        
        # 获取选中文本，如果没有选中则获取当前段落
        try:
            selected = self.text_widget.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            # 没有选中文本，获取光标所在段落
            cursor_pos = self.text_widget.index(tk.INSERT)
            line_start = cursor_pos.split('.')[0] + '.0'
            # 找到段落开头
            while line_start > '1.0':
                prev_line = self.text_widget.get(f"{line_start}-1l", line_start)
                if prev_line.strip() == '':
                    break
                line_start = f"{line_start}-1l"
            # 找到段落结尾
            line_end = line_start
            while True:
                next_line = self.text_widget.get(line_end, f"{line_end}+1l")
                if next_line.strip() == '' or line_end == self.text_widget.index(tk.END):
                    break
                line_end = f"{line_end}+1l"
            selected = self.text_widget.get(line_start, line_end).strip()
        
        if not selected:
            selected = self.text_widget.get("1.0", tk.END).strip()[-300:]
        
        # 构建提示词
        prompts = {
            "expand": {
                "system": "你是一位小说写作助手。请将用户提供的文本扩写为更详细、更生动的内容。保持原有情节和风格，增加细节描写、心理活动、环境描写等。直接输出扩写后的内容。",
                "user": f"请扩写以下内容，使其更加详细生动：\n\n{selected}",
                "max_tokens": 1000,
            },
            "compress": {
                "system": "你是一位小说写作助手。请将用户提供的文本精简压缩，保留核心情节和关键信息，去除冗余描写。直接输出精简后的内容。",
                "user": f"请精简以下内容，保留核心情节：\n\n{selected}",
                "max_tokens": 500,
            },
            "polish": {
                "system": "你是一位小说写作助手。请润色用户提供的文本，优化语言表达，使其更加流畅、优美、有感染力。保持原有情节不变。直接输出润色后的内容。",
                "user": f"请润色以下内容，优化语言表达：\n\n{selected}",
                "max_tokens": 800,
            },
            "rewrite": {
                "system": "你是一位小说写作助手。请用不同的表达方式重新改写用户提供的文本，保持相同的情节和含义，但使用不同的词汇和句式。直接输出改写后的内容。",
                "user": f"请改写以下内容，使用不同的表达方式：\n\n{selected}",
                "max_tokens": 800,
            },
            "dialogue": {
                "system": "你是一位小说写作助手。请根据用户提供的文本内容，生成一段角色之间的对话。对话要符合角色性格，自然生动。直接输出对话内容。",
                "user": f"请根据以下内容，生成角色之间的对话：\n\n{selected}",
                "max_tokens": 600,
            },
        }
        
        prompt = prompts.get(mode, prompts["polish"])
        
        # 添加共享上下文
        system = prompt["system"]
        if self.shared_context:
            system += f"\n\n小说背景（保持一致性）：\n{self.shared_context[:500]}"
        
        # 显示处理中状态
        self._show_ai_status(f"AI{mode}中...")
        
        def generate():
            try:
                response = self.ai.chat(
                    [{"role": "user", "content": prompt["user"]}],
                    system=system,
                    max_tokens=prompt["max_tokens"],
                    temperature=0.7
                )
                
                # 在主线程中替换文本
                self.win.after(0, lambda: self._replace_selection(response.strip(), mode))
                self.win.after(0, self._hide_ai_status)
                
            except Exception as e:
                self.win.after(0, lambda: self._show_ai_status(f"AI错误: {str(e)[:30]}"))
                self.win.after(3000, self._hide_ai_status)
        
        threading.Thread(target=generate, daemon=True).start()
    
    def _replace_selection(self, new_text: str, mode: str):
        """替换选中文本"""
        try:
            self.text_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            # 没有选中，插入到光标位置
            pass
        
        # 插入新文本
        if mode == "expand":
            # 扩写：插入到原位置后面
            self.text_widget.insert(tk.INSERT, "\n\n" + new_text)
        elif mode == "dialogue":
            # 对话：插入到新行
            self.text_widget.insert(tk.INSERT, "\n\n" + new_text)
        else:
            # 其他：替换
            self.text_widget.insert(tk.INSERT, new_text)
        
        # 更新字数
        content = self.text_widget.get("1.0", tk.END).strip()
        self.word_count_label.config(text=f"字数: {len(content)}")
    
    def _show_ai_status(self, text: str):
        """显示AI处理状态"""
        if hasattr(self, 'ai_status_label'):
            self.ai_status_label.config(text=text)
            self.ai_status_label.place(relx=0.5, rely=0.05, anchor=tk.CENTER)
    
    def _hide_ai_status(self):
        """隐藏AI处理状态"""
        if hasattr(self, 'ai_status_label'):
            self.ai_status_label.place_forget()
    
    # ===== Markdown功能 =====
    
    def _setup_markdown_highlighting(self):
        """设置Markdown语法高亮"""
        # 定义标签样式
        self.text_widget.tag_configure('md_h1', font=('微软雅黑', self.font_size + 6, 'bold'), foreground='#1a1a2e')
        self.text_widget.tag_configure('md_h2', font=('微软雅黑', self.font_size + 4, 'bold'), foreground='#2d2d3f')
        self.text_widget.tag_configure('md_h3', font=('微软雅黑', self.font_size + 2, 'bold'), foreground='#3d3d52')
        self.text_widget.tag_configure('md_bold', font=('Consolas', self.font_size, 'bold'))
        self.text_widget.tag_configure('md_italic', font=('Consolas', self.font_size, 'italic'))
        self.text_widget.tag_configure('md_strike', overstrike=True, foreground='#888888')
        self.text_widget.tag_configure('md_code', font=('Consolas', self.font_size - 1), 
                                      background='#e8e3d8', foreground='#c0392b')
        self.text_widget.tag_configure('md_codeblock', font=('Consolas', self.font_size - 1),
                                      background='#e8e3d8', foreground='#2c3e50')
        self.text_widget.tag_configure('md_quote', foreground='#7f8c8d', lmargin1=20, lmargin2=20)
        self.text_widget.tag_configure('md_list', lmargin1=20, lmargin2=30)
        self.text_widget.tag_configure('md_link', foreground='#3498db', underline=True)
        self.text_widget.tag_configure('md_hr', foreground='#bdc3c7')
        
        # 绑定按键事件 - 用于打字机模式和AI辅助
        self.text_widget.bind('<KeyRelease>', self._on_key_release)
    
    def _update_markdown_highlighting(self):
        """更新Markdown语法高亮"""
        content = self.text_widget.get("1.0", tk.END)
        
        # 清除所有高亮标签
        for tag in ['md_h1', 'md_h2', 'md_h3', 'md_bold', 'md_italic', 
                    'md_strike', 'md_code', 'md_codeblock', 'md_quote', 'md_list', 'md_link', 'md_hr']:
            self.text_widget.tag_remove(tag, "1.0", tk.END)
        
        import re
        
        # 标题高亮
        for match in re.finditer(r'^(# .+)$', content, re.MULTILINE):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_h1', start, end)
        
        for match in re.finditer(r'^(## .+)$', content, re.MULTILINE):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_h2', start, end)
        
        for match in re.finditer(r'^(### .+)$', content, re.MULTILINE):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_h3', start, end)
        
        # 加粗
        for match in re.finditer(r'(\*\*[^*]+\*\*)', content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_bold', start, end)
        
        # 斜体
        for match in re.finditer(r'(\*[^*]+\*)', content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_italic', start, end)
        
        # 删除线
        for match in re.finditer(r'(~~[^~]+~~)', content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_strike', start, end)
        
        # 行内代码
        for match in re.finditer(r'(`[^`]+`)', content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_code', start, end)
        
        # 代码块
        for match in re.finditer(r'(```[\s\S]*?```)', content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_codeblock', start, end)
        
        # 引用
        for match in re.finditer(r'^(> .+)$', content, re.MULTILINE):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_quote', start, end)
        
        # 列表
        for match in re.finditer(r'^(\- .+|\* .+|\d+\. .+)$', content, re.MULTILINE):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_list', start, end)
        
        # 分割线
        for match in re.finditer(r'^(---+|\*\*\*+)$', content, re.MULTILINE):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text_widget.tag_add('md_hr', start, end)
    
    def _insert_markdown(self, prefix: str, name: str):
        """插入Markdown标记"""
        try:
            # 获取选中文本
            selected = self.text_widget.get(tk.SEL_FIRST, tk.SEL_LAST)
            
            if name in ['bold', 'italic', 'strike', 'code']:
                # 包围选中文本
                self.text_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                self.text_widget.insert(tk.INSERT, f"{prefix}{selected}{prefix}")
            elif name == 'link':
                # 插入链接
                self.text_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                self.text_widget.insert(tk.INSERT, f"[{selected}](url)")
            else:
                # 在选中文本前插入
                self.text_widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                self.text_widget.insert(tk.INSERT, f"{prefix}{selected}")
        except tk.TclError:
            # 没有选中文本
            if name in ['heading1', 'heading2', 'heading3']:
                # 在行首插入标题
                cursor_pos = self.text_widget.index(tk.INSERT)
                line_start = cursor_pos.split('.')[0] + '.0'
                self.text_widget.insert(line_start, prefix)
            elif name == 'hr':
                self.text_widget.insert(tk.INSERT, "\n---\n")
            elif name == 'codeblock':
                self.text_widget.insert(tk.INSERT, "```\n\n```")
                # 移动光标到代码块中间
                cursor_pos = self.text_widget.index(tk.INSERT)
                self.text_widget.mark_set(tk.INSERT, f"{cursor_pos}-3l")
            elif name in ['list', 'olist', 'quote']:
                # 在行首插入
                cursor_pos = self.text_widget.index(tk.INSERT)
                line_start = cursor_pos.split('.')[0] + '.0'
                self.text_widget.insert(line_start, prefix)
            else:
                # 在光标位置插入标记
                self.text_widget.insert(tk.INSERT, f"{prefix}{prefix}")
                # 移动光标到标记中间
                cursor_pos = self.text_widget.index(tk.INSERT)
                self.text_widget.mark_set(tk.INSERT, f"{cursor_pos}-1c")
        
        # 更新高亮
        self._update_markdown_highlighting()
    
    def _toggle_preview(self):
        """切换Markdown预览"""
        if self.preview_var.get():
            # 显示预览
            self._update_preview()
            self.preview_widget.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        else:
            # 隐藏预览
            self.preview_widget.pack_forget()
    
    def _update_preview(self):
        """更新Markdown预览"""
        content = self.text_widget.get("1.0", tk.END)
        
        # 简单的Markdown转HTML预览
        import re
        
        # 转换Markdown为可读文本
        preview = content
        preview = re.sub(r'^# (.+)$', r'【标题】\1', preview, flags=re.MULTILINE)
        preview = re.sub(r'^## (.+)$', r'【大标题】\1', preview, flags=re.MULTILINE)
        preview = re.sub(r'^### (.+)$', r'【小标题】\1', preview, flags=re.MULTILINE)
        preview = re.sub(r'\*\*([^*]+)\*\*', r'【加粗】\1', preview)
        preview = re.sub(r'\*([^*]+)\*', r'【斜体】\1', preview)
        preview = re.sub(r'~~([^~]+)~~', r'【删除】\1', preview)
        preview = re.sub(r'`([^`]+)`', r'「\1」', preview)
        preview = re.sub(r'^> (.+)$', r'  ┃ \1', preview, flags=re.MULTILINE)
        preview = re.sub(r'^- (.+)$', r'  • \1', preview, flags=re.MULTILINE)
        preview = re.sub(r'^---+$', '─' * 40, preview, flags=re.MULTILINE)
        
        self.preview_widget.config(state=tk.NORMAL)
        self.preview_widget.delete("1.0", tk.END)
        self.preview_widget.insert("1.0", preview)
        self.preview_widget.config(state=tk.DISABLED)
    
    def _show_writer_settings(self):
        """显示写作设置对话框"""
        dialog = tk.Toplevel(self.win)
        dialog.title("写作设置")
        dialog.geometry("400x450")
        dialog.transient(self.win)
        dialog.grab_set()
        
        ttk.Label(dialog, text="字体大小:").pack(anchor=tk.W, padx=20, pady=(15,3))
        font_var = tk.IntVar(value=self.font_size)
        ttk.Scale(dialog, from_=12, to=36, variable=font_var, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=20)
        
        ttk.Label(dialog, text="纸张宽度:").pack(anchor=tk.W, padx=20, pady=(10,3))
        width_var = tk.IntVar(value=self.paper_width)
        ttk.Scale(dialog, from_=400, to=1000, variable=width_var, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=20)
        
        ttk.Label(dialog, text="纸张位置:").pack(anchor=tk.W, padx=20, pady=(10,3))
        pos_var = tk.StringVar(value=self.paper_position)
        pos_frame = ttk.Frame(dialog)
        pos_frame.pack(fill=tk.X, padx=20)
        ttk.Radiobutton(pos_frame, text="居中", variable=pos_var, value="center").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(pos_frame, text="左侧", variable=pos_var, value="left").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(pos_frame, text="右侧", variable=pos_var, value="right").pack(side=tk.LEFT, padx=10)
        
        ttk.Label(dialog, text="背景透明度:").pack(anchor=tk.W, padx=20, pady=(10,3))
        opacity_var = tk.DoubleVar(value=self.bg_opacity)
        ttk.Scale(dialog, from_=0.3, to=1.0, variable=opacity_var, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=20)
        
        ttk.Label(dialog, text="背景颜色:").pack(anchor=tk.W, padx=20, pady=(10,3))
        bg_var = tk.StringVar(value="#f5f0e8")
        colors = [("#f5f0e8", "米白"), ("#ffffff", "纯白"), ("#2c2c2c", "深灰"), ("#1a1a2e", "深蓝黑")]
        color_frame = ttk.Frame(dialog)
        color_frame.pack(fill=tk.X, padx=20)
        for color, name in colors:
            btn = tk.Button(color_frame, bg=color, width=4, height=2, 
                          command=lambda c=color: bg_var.set(c))
            btn.pack(side=tk.LEFT, padx=5)
            ttk.Label(color_frame, text=name).pack(side=tk.LEFT, padx=(0,10))
        
        def apply():
            self.font_size = font_var.get()
            self.paper_width = width_var.get()
            self.paper_position = pos_var.get()
            self.bg_opacity = opacity_var.get()
            
            bg_color = bg_var.get()
            self.paper.configure(bg=bg_color, width=self.paper_width)
            self.inner_frame.configure(bg=bg_color)
            self.text_widget.configure(bg=bg_color, font=("微软雅黑", self.font_size))
            self.suggestion_label.configure(bg=bg_color)
            
            self._update_paper_position()
            self._save_writer_settings()
            dialog.destroy()
        
        ttk.Button(dialog, text="应用", command=apply).pack(pady=20)
    
    def _load_writer_settings(self):
        """加载写作设置"""
        if self.config:
            settings_file = self.config.config_dir / "writer_settings.json"
            if settings_file.exists():
                with open(settings_file, 'r') as f:
                    s = json.load(f)
                self.font_size = s.get("font_size", 18)
                self.paper_width = s.get("paper_width", 700)
                self.paper_position = s.get("paper_position", "center")
                self.bg_opacity = s.get("bg_opacity", 0.85)
                self.typewriter_mode = s.get("typewriter_mode", True)
                self.ai_assist_enabled = s.get("ai_assist", True)
    
    def _save_writer_settings(self):
        """保存写作设置"""
        if self.config:
            settings_file = self.config.config_dir / "writer_settings.json"
            with open(settings_file, 'w') as f:
                json.dump({
                    "font_size": self.font_size,
                    "paper_width": self.paper_width,
                    "paper_position": self.paper_position,
                    "bg_opacity": self.bg_opacity,
                    "typewriter_mode": self.typewriter_mode,
                    "ai_assist": self.ai_assist_enabled,
                }, f, indent=2)
    
    def _save(self):
        """保存内容"""
        self.text_content = self.text_widget.get("1.0", tk.END).strip()
        if self.save_callback:
            self.save_callback(self.text_content)
    
    def _exit_fullscreen(self):
        """退出全屏"""
        self._save()
        self.win.destroy()
    
    def get_content(self) -> str:
        """获取写作内容"""
        return self.text_widget.get("1.0", tk.END).strip()


# ==================== 小说智能体 ====================

class NovelAgent:
    """小说创作智能体 - 参考AutoGen多智能体协作架构
    
    智能体角色：
    - Writer (作家): 负责创作小说内容
    - Reviewer (审校): 负责检查质量和一致性
    - Editor (编辑/质量门): 负责最终裁定是否通过
    
    协作流程（参考AutoGen的GroupChat模式）：
    1. Writer生成内容 → 2. Reviewer审校 → 3. Editor判定
       → 不过关 → Writer修订 → Reviewer再审校 → ...
       → 过关 → 保存定稿
    
    关键机制：
    - 迭代修订循环：质量不达标自动触发修订
    - 质量门控：设定最低通过分数线
    - 反思记忆：记录每次修订的原因，供后续参考
    """
    
    # 质量阈值
    QUALITY_THRESHOLD = 75  # 评分低于此值自动触发修订
    MAX_REVISION_ROUNDS = 3  # 最多修订轮次
    
    def __init__(self, ai_client: AIClient, memory: MemoryManager, log_callback=None, config: AppConfig = None):
        self.ai = ai_client
        self.memory = memory
        self.log = log_callback or print
        self.config = config
        
        # 智能体会话历史（参考AutoGen的对话记录）
        self._conversation_log: List[Dict] = []
        
        # 修订记忆（记录每次修订的原因）
        self._revision_memory: List[Dict] = []
    
    def _record_conversation(self, agent: str, action: str, content: str):
        """记录智能体对话（参考AutoGen的消息历史）"""
        self._conversation_log.append({
            "agent": agent,
            "action": action,
            "content": content[:200],  # 只记录摘要
            "timestamp": datetime.now().isoformat(),
        })
    
    def _build_context(self, chapter_num: int, extra_context: str = "", max_chars: int = None) -> str:
        """构建上下文 - 分层架构，支持5000章小说
        
        上下文结构：
        1. 全局摘要 (10%)
        2. 当前卷摘要 (15%)
        3. 当前弧线摘要 (10%)
        4. 活跃角色 (15%)
        5. 最近章节 (40%)
        6. RAG检索结果 (10%)
        """
        if max_chars is None:
            max_chars = self.config.get("context_window", 32000) // 4 if self.config else 8000
        
        parts = []
        used = 0
        
        # 1. 全局摘要
        gs = self.memory.get_global_summary()
        if gs:
            budget = int(max_chars * 0.10)
            text = self._compress_text(gs, budget, keep_tail=True)
            parts.append(f"【全局摘要】\n{text}")
            used += len(text)
        
        # 2. 当前卷摘要
        vol_summary = self.memory.get_current_volume_summary(chapter_num)
        if vol_summary and used < max_chars:
            budget = int(max_chars * 0.15)
            text = self._compress_text(vol_summary, budget, keep_tail=True)
            parts.append(f"【当前卷】\n{text}")
            used += len(text)
        
        # 3. 活跃角色（按活跃度加载）
        chars = self.memory.get_characters()
        if chars and used < max_chars:
            active_names = self.memory.get_active_characters(chapter_num, window=50)
            budget = int(max_chars * 0.15)
            text = self._compress_active_characters(chars, active_names, budget)
            if text:
                parts.append(f"【活跃角色】\n{text}")
                used += len(text)
        
        # 4. 最近章节摘要（根据小说长度动态调整）
        if used < max_chars:
            # 5000章小说看最近5章，500章看最近3章
            recent_count = 5 if chapter_num > 1000 else 3
            budget = int(max_chars * 0.40)
            recent = self.memory.get_recent_summaries(recent_count)
            if recent:
                text = self._compress_text(recent, budget, keep_tail=True)
                parts.append(f"【近期章节】\n{text}")
                used += len(text)
        
        # 5. RAG检索结果（如果有额外上下文）
        if extra_context and used < max_chars:
            budget = int(max_chars * 0.10)
            relevant = self.memory.retrieve_relevant(extra_context, top_k=3)
            if relevant:
                rag_text = "\n".join([f"- {r.get('content', '')[:100]}" for r in relevant])
                text = self._compress_text(rag_text, budget, keep_tail=False)
                parts.append(f"【相关记忆】\n{text}")
                used += len(text)
        
        # 6. 补充上下文
        if extra_context and used < max_chars:
            parts.append(f"【补充】\n{extra_context[:300]}")
        
        result = "\n\n".join(parts)
        if len(result) > max_chars:
            return result[:max_chars] + "\n...(已压缩)"
        return result
    
    def _compress_active_characters(self, chars: dict, active_names: List[str], budget: int) -> str:
        """压缩活跃角色信息"""
        result = []
        used = 0
        
        # 优先显示活跃角色
        for name in active_names:
            if used >= budget:
                break
            if name in chars:
                info = chars[name]
                if isinstance(info, dict):
                    personality = info.get("personality", "")[:30]
                    line = f"- {name}: {personality}"
                else:
                    line = f"- {name}: {str(info)[:50]}"
                if used + len(line) <= budget:
                    result.append(line)
                    used += len(line)
        
        # 如果还有空间，添加其他重要角色
        if used < budget:
            for name, info in list(chars.items())[:5]:
                if name not in active_names and used < budget:
                    if isinstance(info, dict):
                        personality = info.get("personality", "")[:20]
                        line = f"- {name}: {personality}"
                    else:
                        line = f"- {name}: {str(info)[:30]}"
                    if used + len(line) <= budget:
                        result.append(line)
                        used += len(line)
        
        return "\n".join(result)
    
    # ===== 压缩方法 =====
    
    def _compress_settings(self, settings: dict, budget: int) -> str:
        priority_keys = ["world", "rules", "factions", "technology", "history", "geography", "culture"]
        result = []
        used = 0
        for key in priority_keys:
            if key in settings and used < budget:
                val = str(settings[key])[:budget - used - len(key) - 3]
                result.append(f"{key}: {val}")
                used += len(val) + len(key) + 2
        return "\n".join(result)
    
    def _compress_characters(self, chars: dict, budget: int) -> str:
        core = ["name", "personality", "motivation"]
        result = []
        used = 0
        for name, info in list(chars.items())[:8]:
            if used >= budget: break
            if isinstance(info, dict):
                extra = "; ".join(f"{f}:{str(info.get(f,''))[:50]}" for f in core if f in info)
                line = f"- {name}: {extra}"[:budget - used]
            else:
                line = f"- {name}: {str(info)[:100]}"[:budget - used]
            result.append(line)
            used += len(line) + 1
        return "\n".join(result)
    
    def _compress_text(self, text: str, budget: int, keep_tail: bool = True) -> str:
        if len(text) <= budget: return text
        if budget < 50: return text[:budget] + "..."
        if keep_tail:
            head = int(budget * 0.3)
            return text[:head] + "...\n\n" + text[-(budget - head - 5):]
        else:
            head = int(budget * 0.7)
            return text[:head] + "...\n\n" + text[-(budget - head - 5):]
    
    def _compress_recent_chapters(self, recent_text: str, budget: int, chapter_num: int) -> str:
        chapters = recent_text.split("\n\n")
        if len(chapters) <= 1: return self._compress_text(recent_text, budget, True)
        result = []
        used = 0
        latest = chapters[-1] if chapters else ""
        lb = min(int(budget * 0.4), len(latest))
        if latest: result.append(latest[:lb]); used += lb
        for ch in reversed(chapters[:-1]):
            if used >= budget: break
            cb = min(int((budget - used) * 0.3), len(ch))
            if cb > 50: result.insert(0, self._compress_text(ch, cb, True)); used += cb
        return "\n\n".join(result)
    
    # ===== 多智能体协作核心 =====
    
    def generate_with_collaboration(self, chapter_num: int, chapter_title: str,
                                     chapter_outline: str, word_count: int = 3000) -> str:
        """多智能体协作生成章节 - 核心编排方法
        
        参考AutoGen的GroupChat：Writer→Reviewer→Editor 循环
        """
        self._conversation_log = []
        self.log(f"[编排器] 启动多智能体协作：第{chapter_num}章「{chapter_title}」")
        
        # 第1轮：Writer生成初稿
        self.log(f"[Writer] 正在创作第{chapter_num}章初稿...")
        self._record_conversation("Writer", "generate", f"开始创作第{chapter_num}章")
        content = self._writer_generate(chapter_num, chapter_title, chapter_outline, word_count)
        
        # 迭代修订循环（参考AutoGen的反馈环）
        for round_num in range(1, self.MAX_REVISION_ROUNDS + 1):
            # Reviewer审校
            self.log(f"[Reviewer] 正在审校第{chapter_num}章（第{round_num}轮）...")
            self._record_conversation("Reviewer", "review", f"第{round_num}轮审校")
            review = self._reviewer_evaluate(chapter_num, content)
            
            # Editor裁定（质量门）
            self.log(f"[Editor] 质量裁定：{review.get('overall_score', 0)}分")
            self._record_conversation("Editor", "judge", 
                f"评分{review.get('overall_score', 0)}，阈值{self.QUALITY_THRESHOLD}")
            
            if review.get("overall_score", 0) >= self.QUALITY_THRESHOLD:
                self.log(f"[Editor] ✅ 通过！质量达标。")
                self._record_conversation("Editor", "approve", "质量达标，通过")
                break
            
            # 不达标，修订
            suggestions = review.get("suggestions", [])
            issues = review.get("issues", [])
            self.log(f"[Editor] ⚠️ 质量不达标（{review.get('overall_score', 0)}/{self.QUALITY_THRESHOLD}），"
                    f"触发第{round_num}轮修订...")
            
            # 记录修订记忆
            self._revision_memory.append({
                "chapter": chapter_num,
                "round": round_num,
                "issues": issues,
                "suggestions": suggestions,
            })
            
            # Writer修订
            self.log(f"[Writer] 正在根据审校意见修订...")
            self._record_conversation("Writer", "revise", f"第{round_num}轮修订")
            content = self._writer_revise(chapter_num, content, review, chapter_outline)
        
        self.log(f"[编排器] 第{chapter_num}章协作完成")
        return content
    
    def _writer_generate(self, chapter_num: int, chapter_title: str, 
                         chapter_outline: str, word_count: int) -> str:
        """Writer智能体：生成章节内容"""
        context = self._build_context(chapter_num)
        
        system = f"""你是一位专业的小说作家（Writer Agent）。
请根据以下上下文信息创作小说章节。

{context}

创作要求：
1. 保持与前文的连贯性
2. 角色行为符合其性格设定
3. 情节推进自然流畅
4. 语言生动，有画面感
5. 目标字数约{word_count}字
6. 直接输出正文内容，不要添加额外说明
7. 注意设置伏笔和悬念"""
        
        prompt = f"请创作第{chapter_num}章：{chapter_title}\n\n章节大纲：{chapter_outline}\n\n目标字数：{word_count}字\n\n请直接输出正文："
        
        if word_count > 3000:
            return self._generate_long_chapter(chapter_num, chapter_title, chapter_outline, word_count, context)
        
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4096)
        self.log(f"[Writer] 第{chapter_num}章初稿完成，字数：{len(response)}")
        return response
    
    def _reviewer_evaluate(self, chapter_num: int, content: str, 
                           previous_feedback: str = "") -> dict:
        """Reviewer智能体：审校章节
        
        参考AutoGen的code_reviewer角色，检查质量和一致性
        """
        context = self._build_context(chapter_num)
        
        feedback_section = ""
        if previous_feedback:
            feedback_section = f"\n上次审校反馈（请重点关注）：\n{previous_feedback}"
        
        system = f"""你是一位专业的小说审校编辑（Reviewer Agent）。
请严格检查以下章节内容的各方面质量。

{context}
{feedback_section}

请以JSON格式输出审校结果：
{{
    "character_consistency": 0-100,  // 角色行为一致性
    "plot_logic": 0-100,             // 情节逻辑
    "writing_quality": 0-100,        // 文笔质量
    "emotional_impact": 0-100,       // 情感感染力
    "pacing": 0-100,                 // 节奏把控
    "overall_score": 0-100,          // 综合评分
    "strengths": ["优点1", ...],     // 写得好的地方
    "issues": ["问题1", ...],        // 发现的问题
    "suggestions": ["建议1", ...],   // 修改建议
    "is_acceptable": true/false      // 是否可接受
}}"""
        
        prompt = f"请审校第{chapter_num}章内容：\n\n{content[:4000]}"
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=2000)
        
        try:
            return self._parse_json_response(response, {"overall_score": 70, "issues": [], "suggestions": []})
        except:
            return {"overall_score": 70, "issues": [], "suggestions": [], "raw": response}
    
    def _writer_revise(self, chapter_num: int, original: str, review: dict, 
                       chapter_outline: str) -> str:
        """Writer智能体：根据审校意见修订章节
        
        参考AutoGen的迭代优化循环
        """
        suggestions = review.get("suggestions", [])
        issues = review.get("issues", [])
        strengths = review.get("strengths", [])
        
        context = self._build_context(chapter_num)
        
        system = f"""你是一位专业的小说作家（Writer Agent），正在修订自己的作品。

{context}

修订原则：
1. 根据审校意见进行针对性修改
2. 保留已有的优点和长处
3. 修改时注意不要破坏整体的连贯性
4. 回应每一个具体问题"""
        
        prompt = f"""请修订第{chapter_num}章内容。

审校反馈：
优点（请保持）：{json.dumps(strengths, ensure_ascii=False)}
问题（需修改）：{json.dumps(issues, ensure_ascii=False)}
建议（参考）：{json.dumps(suggestions, ensure_ascii=False)}

原文：
{original[-4000:] if len(original) > 4000 else original}

修订要求：请输出完整的修订后文本，直接输出正文："""
        
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4096)
        self.log(f"[Writer] 修订完成，字数：{len(response)}")
        return response
    
    # ===== 传统方法（兼容旧接口）=====
    
    def generate_chapter(self, chapter_num: int, chapter_title: str, 
                         chapter_outline: str, word_count: int = 3000) -> str:
        """生成章节 - 使用多智能体协作"""
        return self.generate_with_collaboration(chapter_num, chapter_title, 
                                                chapter_outline, word_count)
    
    def review_chapter(self, chapter_num: int, content: str) -> dict:
        """审校章节"""
        return self._reviewer_evaluate(chapter_num, content)
    
    def generate_settings(self, genre: str, title: str, concept: str) -> dict:
        """生成世界观"""
        self.log(f"[智能体] 正在生成世界观...")
        system = """你是一位专业的小说世界观设定师。请生成详细的世界观设定。
以JSON格式输出：world/rules/factions/history/technology/geography/culture"""
        prompt = f"小说类型：{genre}\n标题：{title}\n概念：{concept}"
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=3000)
        settings = self._parse_json_response(response, {"raw": response})
        self.memory.save_settings(settings)
        return settings
    
    def generate_characters(self, genre: str, title: str, count: int = 5) -> dict:
        """生成角色"""
        self.log(f"[智能体] 正在生成{count}个角色...")
        settings = self.memory.get_settings()
        system = f"你是专业角色设计师。世界观：{json.dumps(settings, ensure_ascii=False)[:500]}\n输出JSON：{{'角色名': {{...}}}}"
        prompt = f"小说类型：{genre}\n标题：{title}\n创建{count}个角色"
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=3000)
        chars = self._parse_json_response(response, {"raw": response})
        self.memory.save_characters(chars)
        return chars
    
    def generate_outline(self, genre: str, title: str, chapter_count: int) -> list:
        """生成大纲"""
        self.log(f"[智能体] 正在生成{chapter_count}章大纲...")
        context = self._build_context(0)
        system = f"你是专业小说大纲规划师。\n{context}\n输出JSON数组：[{{'chapter':1,'title':'','summary':'','key_events':[],'characters_involved':[]}}]"
        prompt = f"小说类型：{genre}\n标题：{title}\n章节数：{chapter_count}"
        response = self.ai.chat([{"role": "user", "content": prompt}], system=system, max_tokens=4000)
        outline = self._parse_json_response(response, [], is_list=True)
        if not outline:
            outline = [{"chapter": i+1, "title": f"第{i+1}章", "summary": "待规划"} for i in range(chapter_count)]
        return outline
    
    def finalize_chapter(self, chapter_num: int, content: str):
        """定稿章节 + 更新记忆"""
        # 章节摘要
        summary = self.ai.chat(
            [{"role": "user", "content": f"请生成摘要（100-200字）：\n{content[:2000]}"}],
            system="你是故事摘要助手。", max_tokens=300
        )
        self.memory.save_chapter_summary(chapter_num, summary)
        
        # 全局摘要
        old = self.memory.get_global_summary()
        new = self.ai.chat(
            [{"role": "user", "content": f"更新全局摘要：\n旧：{old}\n新章节：{summary}"}],
            system="你是故事摘要助手。", max_tokens=500
        )
        self.memory.save_global_summary(new)
        
        # 关键词索引
        kw = self.ai.chat([{"role": "user", "content": f"提取10个关键词，逗号分隔：\n{content[:1000]}"}],
                         system="提取关键词。", max_tokens=200)
        self.memory.update_index(chapter_num, [k.strip() for k in kw.split(",") if k.strip()])
        
        # 添加记忆块
        self.memory.add_chunk("plot", summary, importance=8, 
                             tags=kw.split(",")[:5] if kw else [])
        self.memory.add_event(chapter_num, summary, "story")
        
        self.log(f"[智能体] 第{chapter_num}章定稿完成")
    
    # ===== 工具方法 =====
    
    @staticmethod
    def _parse_json_response(response: str, default: Any, is_list: bool = False) -> Any:
        """解析AI返回的JSON"""
        try:
            marker = "[" if is_list else "{"
            end_marker = "]" if is_list else "}"
            start = response.find(marker)
            end = response.rfind(end_marker) + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except:
            pass
        return default
    
    def _generate_long_chapter(self, chapter_num, chapter_title, chapter_outline, word_count, context) -> str:
        """分段生成长章节"""
        parts = []
        part_count = max((word_count + 2999) // 3000, 1)
        for i in range(part_count):
            self.log(f"[Writer] 第{chapter_num}章 第{i+1}/{part_count}段...")
            part_prompt = f"创作第{chapter_num}章：{chapter_title}\n大纲：{chapter_outline}\n已有：{''.join(parts[-2:]) or '（开头）'}\n请创作约3000字："
            response = self.ai.chat([{"role": "user", "content": part_prompt}],
                                   system=f"专业小说作家。\n{context[:1000]}", max_tokens=4096)
            parts.append(response)
        return "\n\n".join(parts)


# ==================== 阅读管理器 ====================

class ReadingManager:
    """阅读管理器 - 支持多种格式的小说阅读"""
    
    SUPPORTED_FORMATS = {
        '.txt': 'TXT文本文件',
        '.epub': 'EPUB电子书',
        '.pdf': 'PDF文档',
        '.docx': 'Word文档',
        '.md': 'Markdown文件',
    }
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.books_dir = config.config_dir / "books"
        self.books_dir.mkdir(exist_ok=True)
        self.bookmarks_file = config.config_dir / "bookmarks.json"
        self.reading_history_file = config.config_dir / "reading_history.json"
        
        # 阅读设置
        self.font_size = 16
        self.font_family = "微软雅黑"
        self.line_spacing = 1.5
        self.bg_color = "#f5f0e8"  # 米白色背景
        self.text_color = "#2c2c2c"
        self.theme = "light"  # light/dark/sepia
        
    def get_supported_formats(self) -> List[str]:
        """获取支持的文件格式"""
        return list(self.SUPPORTED_FORMATS.keys())
    
    def import_book(self, file_path: str) -> Optional[Dict]:
        """导入书籍到书库"""
        path = Path(file_path)
        if not path.exists():
            return None
        
        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_FORMATS:
            return None
        
        # 复制到书库
        dest = self.books_dir / path.name
        import shutil
        shutil.copy2(path, dest)
        
        # 提取元数据
        meta = self._extract_metadata(dest, ext)
        meta['file_path'] = str(dest)
        meta['import_date'] = datetime.now().isoformat()
        meta['last_read'] = None
        meta['progress'] = 0
        
        return meta
    
    def _extract_metadata(self, file_path: Path, ext: str) -> Dict:
        """提取书籍元数据"""
        meta = {
            'title': file_path.stem,
            'author': '未知',
            'format': ext,
            'size': file_path.stat().st_size,
            'pages': 0,
            'chapters': [],
        }
        
        try:
            if ext == '.txt':
                # 尝试读取前几行获取标题
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = [f.readline().strip() for _ in range(10)]
                    # 寻找标题行
                    for line in lines:
                        if line and len(line) < 50 and not line.startswith(('第', '章', '卷')):
                            meta['title'] = line
                            break
            
            elif ext == '.epub' and EPUB_SUPPORT:
                book = epub.read_epub(str(file_path))
                meta['title'] = book.get_metadata('DC', 'title')[0][0] if book.get_metadata('DC', 'title') else file_path.stem
                meta['author'] = book.get_metadata('DC', 'creator')[0][0] if book.get_metadata('DC', 'creator') else '未知'
                # 获取章节列表
                for item in book.get_items():
                    if item.get_type() == 9:  # ITEM_DOCUMENT
                        meta['chapters'].append(item.get_name())
            
            elif ext == '.pdf' and PDF_SUPPORT:
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    meta['pages'] = len(reader.pages)
                    if reader.metadata:
                        meta['title'] = reader.metadata.title or file_path.stem
                        meta['author'] = reader.metadata.author or '未知'
            
            elif ext == '.docx' and DOCX_SUPPORT:
                doc = Document(str(file_path))
                # 获取段落数作为页数估计
                meta['pages'] = len(doc.paragraphs) // 50  # 估计每页50段落
        
        except Exception as e:
            print(f"提取元数据失败: {e}")
        
        return meta
    
    def read_book(self, file_path: str, page: int = 0) -> Optional[str]:
        """读取书籍内容"""
        path = Path(file_path)
        if not path.exists():
            return None
        
        ext = path.suffix.lower()
        
        try:
            if ext == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return content
            
            elif ext == '.epub' and EPUB_SUPPORT:
                import re
                book = epub.read_epub(str(file_path))
                content = []
                for item in book.get_items():
                    if item.get_type() == 9:  # ITEM_DOCUMENT
                        html = item.get_content().decode('utf-8', errors='ignore')
                        text = re.sub(r'<[^>]+>', '', html)
                        text = re.sub(r'\s+', ' ', text).strip()
                        if text:
                            content.append(text)
                return '\n\n'.join(content)
            
            elif ext == '.pdf' and PDF_SUPPORT:
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    content = []
                    for i, page in enumerate(reader.pages):
                        try:
                            text = page.extract_text()
                            if text and text.strip():
                                content.append(text)
                        except:
                            pass
                    return '\n\n'.join(content)
            
            elif ext == '.docx' and DOCX_SUPPORT:
                doc = Document(str(file_path))
                content = []
                for para in doc.paragraphs:
                    if para.text.strip():
                        content.append(para.text)
                return '\n\n'.join(content)
            
            elif ext == '.md':
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
        
        except Exception as e:
            print(f"读取书籍失败: {e}")
            return None
        
        return None
    
    def get_bookmarks(self) -> List[Dict]:
        """获取所有书签"""
        if self.bookmarks_file.exists():
            with open(self.bookmarks_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def add_bookmark(self, file_path: str, position: int, title: str = ""):
        """添加书签"""
        bookmarks = self.get_bookmarks()
        bookmark = {
            'id': int(time.time() * 1000),
            'file_path': file_path,
            'position': position,
            'title': title or f"书签 {len(bookmarks) + 1}",
            'created_at': datetime.now().isoformat(),
        }
        bookmarks.append(bookmark)
        with open(self.bookmarks_file, 'w', encoding='utf-8') as f:
            json.dump(bookmarks, f, indent=2, ensure_ascii=False)
        return bookmark
    
    def delete_bookmark(self, bookmark_id: int):
        """删除书签"""
        bookmarks = self.get_bookmarks()
        bookmarks = [b for b in bookmarks if b.get('id') != bookmark_id]
        with open(self.bookmarks_file, 'w', encoding='utf-8') as f:
            json.dump(bookmarks, f, indent=2, ensure_ascii=False)
    
    def get_reading_history(self) -> List[Dict]:
        """获取阅读历史"""
        if self.reading_history_file.exists():
            with open(self.reading_history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def update_reading_progress(self, file_path: str, position: int, progress: float):
        """更新阅读进度"""
        history = self.get_reading_history()
        
        # 查找现有记录
        found = False
        for record in history:
            if record.get('file_path') == file_path:
                record['position'] = position
                record['progress'] = progress
                record['last_read'] = datetime.now().isoformat()
                found = True
                break
        
        # 添加新记录
        if not found:
            history.append({
                'file_path': file_path,
                'position': position,
                'progress': progress,
                'last_read': datetime.now().isoformat(),
            })
        
        # 保存
        with open(self.reading_history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    
    def get_library_books(self) -> List[Dict]:
        """获取书库中的所有书籍"""
        books = []
        for file in self.books_dir.iterdir():
            if file.is_file() and file.suffix.lower() in self.SUPPORTED_FORMATS:
                meta = self._extract_metadata(file, file.suffix.lower())
                meta['file_path'] = str(file)
                books.append(meta)
        return books
    
    def search_in_book(self, file_path: str, keyword: str) -> List[Dict]:
        """在书籍中搜索关键词"""
        content = self.read_book(file_path)
        if not content:
            return []
        
        results = []
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if keyword.lower() in line.lower():
                results.append({
                    'line_number': i + 1,
                    'content': line.strip(),
                    'context': lines[max(0, i-1):i+2],  # 上下文
                })
        
        return results
    
    def export_bookmarks(self, file_path: str):
        """导出书签到文件"""
        bookmarks = self.get_bookmarks()
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(bookmarks, f, indent=2, ensure_ascii=False)
    
    def import_bookmarks(self, file_path: str):
        """从文件导入书签"""
        with open(file_path, 'r', encoding='utf-8') as f:
            bookmarks = json.load(f)
        
        existing = self.get_bookmarks()
        existing_ids = {b['id'] for b in existing}
        
        # 合并书签，避免重复
        for bookmark in bookmarks:
            if bookmark['id'] not in existing_ids:
                existing.append(bookmark)
        
        with open(self.bookmarks_file, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)


# ==================== UI样式管理 ====================

class UIStyle:
    """现代化UI样式"""
    
    # 颜色方案 - 深色主题
    COLORS = {
        'bg_dark': '#1e1e2e',        # 主背景
        'bg_medium': '#2d2d3f',      # 次背景
        'bg_light': '#3d3d52',       # 浅背景
        'bg_card': '#252538',        # 卡片背景
        'accent': '#7c3aed',         # 主色调（紫色）
        'accent_light': '#a78bfa',   # 浅紫色
        'accent_hover': '#6d28d9',   # 悬停色
        'success': '#10b981',        # 成功绿
        'warning': '#f59e0b',        # 警告黄
        'error': '#ef4444',          # 错误红
        'text_primary': '#f8fafc',   # 主文字
        'text_secondary': '#94a3b8', # 次文字
        'text_muted': '#64748b',     # 弱文字
        'border': '#404055',         # 边框
        'input_bg': '#2d2d3f',       # 输入框背景
        'hover': '#353548',          # 悬停背景
    }
    
    @classmethod
    def apply_theme(cls, root):
        """应用主题到根窗口"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # 配置全局样式
        root.configure(bg=cls.COLORS['bg_dark'])
        
        # Frame样式
        style.configure('Dark.TFrame', background=cls.COLORS['bg_dark'])
        style.configure('Card.TFrame', background=cls.COLORS['bg_card'])
        style.configure('Medium.TFrame', background=cls.COLORS['bg_medium'])
        
        # Label样式
        style.configure('Dark.TLabel', 
                       background=cls.COLORS['bg_dark'],
                       foreground=cls.COLORS['text_primary'],
                       font=('微软雅黑', 10))
        style.configure('Title.TLabel',
                       background=cls.COLORS['bg_dark'],
                       foreground=cls.COLORS['text_primary'],
                       font=('微软雅黑', 14, 'bold'))
        style.configure('Subtitle.TLabel',
                       background=cls.COLORS['bg_dark'],
                       foreground=cls.COLORS['text_secondary'],
                       font=('微软雅黑', 10))
        style.configure('Accent.TLabel',
                       background=cls.COLORS['bg_dark'],
                       foreground=cls.COLORS['accent_light'],
                       font=('微软雅黑', 10))
        
        # Button样式
        style.configure('Accent.TButton',
                       background=cls.COLORS['accent'],
                       foreground=cls.COLORS['text_primary'],
                       font=('微软雅黑', 10),
                       padding=(15, 8))
        style.map('Accent.TButton',
                 background=[('active', cls.COLORS['accent_hover']),
                           ('pressed', cls.COLORS['accent_hover'])])
        
        style.configure('Secondary.TButton',
                       background=cls.COLORS['bg_light'],
                       foreground=cls.COLORS['text_primary'],
                       font=('微软雅黑', 10),
                       padding=(12, 6))
        style.map('Secondary.TButton',
                 background=[('active', cls.COLORS['hover'])])
        
        style.configure('Success.TButton',
                       background=cls.COLORS['success'],
                       foreground='white',
                       font=('微软雅黑', 10, 'bold'),
                       padding=(15, 8))
        
        # Notebook样式
        style.configure('Dark.TNotebook',
                       background=cls.COLORS['bg_dark'],
                       borderwidth=0)
        style.configure('Dark.TNotebook.Tab',
                       background=cls.COLORS['bg_medium'],
                       foreground=cls.COLORS['text_secondary'],
                       padding=[15, 8],
                       font=('微软雅黑', 10))
        style.map('Dark.TNotebook.Tab',
                 background=[('selected', cls.COLORS['accent']),
                           ('active', cls.COLORS['hover'])],
                 foreground=[('selected', 'white'),
                           ('active', cls.COLORS['text_primary'])])
        
        # Entry样式
        style.configure('Dark.TEntry',
                       fieldbackground=cls.COLORS['input_bg'],
                       foreground=cls.COLORS['text_primary'],
                       insertcolor=cls.COLORS['text_primary'],
                       font=('微软雅黑', 10))
        
        # Combobox样式
        style.configure('Dark.TCombobox',
                       fieldbackground=cls.COLORS['input_bg'],
                       foreground=cls.COLORS['text_primary'],
                       font=('微软雅黑', 10))
        
        # Checkbutton样式
        style.configure('Dark.TCheckbutton',
                       background=cls.COLORS['bg_dark'],
                       foreground=cls.COLORS['text_primary'],
                       font=('微软雅黑', 10))
        
        # Radiobutton样式
        style.configure('Dark.TRadiobutton',
                       background=cls.COLORS['bg_dark'],
                       foreground=cls.COLORS['text_primary'],
                       font=('微软雅黑', 10))
        
        # LabelFrame样式
        style.configure('Card.TLabelframe',
                       background=cls.COLORS['bg_card'],
                       foreground=cls.COLORS['text_primary'],
                       font=('微软雅黑', 10, 'bold'))
        style.configure('Card.TLabelframe.Label',
                       background=cls.COLORS['bg_card'],
                       foreground=cls.COLORS['accent_light'],
                       font=('微软雅黑', 10, 'bold'))
        
        # Separator样式
        style.configure('Dark.TSeparator',
                       background=cls.COLORS['border'])
        
        # Scrollbar样式
        style.configure('Dark.Vertical.TScrollbar',
                       background=cls.COLORS['bg_medium'],
                       troughcolor=cls.COLORS['bg_dark'],
                       arrowcolor=cls.COLORS['text_muted'])
        
        return style


# ==================== 主应用程序 ====================

class NovelWriterApp:
    """AI自动写小说主应用"""
    
    def __init__(self):
        self.config = AppConfig()
        self.ai_client = AIClient(self.config)
        self.image_gen = ImageGenerator(self.config)
        self.note_manager = NoteManager(config=self.config)
        self.reading_manager = ReadingManager(self.config)
        
        # 工具集
        self.element_lib = ElementLibrary()
        self.bridge_lib = BridgeLibrary()
        self.desc_lib = DescriptionLibrary()
        self.dialogue_engine = None
        self.story_flow_engine = None
        self.style_engine = None
        self.adapt_engine = None
        self.web_search_engine = None
        self.character_system = None
        self.format_converter = None
        self.image_manager = None
        self.cloud_storage = CloudStorageManager()
        
        self.current_novel_dir = None
        self.memory = None
        self.agent = None
        self.outline = []
        self.current_chapter = 0
        self.is_modified = False  # 文档是否已修改
        
        # 创建GUI
        self.root = tk.Tk()
        self.root.title("AI小说创作工坊 v2.0")
        self.root.geometry("1400x900")
        self.root.minsize(1100, 700)
        
        # 设置图标
        try:
            icon_path = Path(__file__).parent / "icon.ico"
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except:
            pass
        
        # 应用主题
        UIStyle.apply_theme(self.root)
        
        self._create_menu()
        self._create_widgets()
        self._update_status()
        
        # 绑定快捷键
        self.root.bind('<Control-s>', lambda e: self._save_chapter())
        self.root.bind('<Control-n>', lambda e: self._new_novel())
        self.root.bind('<Control-o>', lambda e: self._open_novel())
        self.root.bind('<F11>', lambda e: self._open_fullscreen_writer())
    
    def _create_menu(self):
        """创建菜单栏"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="新建小说", command=self._new_novel)
        file_menu.add_command(label="打开小说", command=self._open_novel)
        file_menu.add_separator()
        file_menu.add_command(label="导出TXT", command=self._export_txt)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        
        # 设置菜单
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设置", menu=settings_menu)
        settings_menu.add_command(label="AI配置", command=self._show_settings)
        
        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="使用说明", command=self._show_help)
        help_menu.add_command(label="关于", command=self._show_about)
    
    def _create_widgets(self):
        """创建主界面 - 深色主题美化版"""
        C = UIStyle.COLORS
        
        # ===== 顶部标题栏 =====
        header = tk.Frame(self.root, bg=C['accent'], height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        # Logo和标题
        title_frame = tk.Frame(header, bg=C['accent'])
        title_frame.pack(side=tk.LEFT, padx=20, fill=tk.Y)
        
        tk.Label(title_frame, text="AI", font=('Arial', 18, 'bold'), 
                bg=C['accent'], fg='white').pack(side=tk.LEFT)
        tk.Label(title_frame, text=" 小说创作工坊", font=('微软雅黑', 14), 
                bg=C['accent'], fg='white').pack(side=tk.LEFT, padx=(5, 0))
        
        # 顶部按钮
        btn_frame = tk.Frame(header, bg=C['accent'])
        btn_frame.pack(side=tk.RIGHT, padx=20, fill=tk.Y)
        
        for text, cmd in [("新建", self._new_novel), ("打开", self._open_novel), 
                         ("导出", self._export_txt), ("格式转换", self._show_format_converter),
                         ("插入图片", self._insert_image), ("云端同步", self._cloud_sync),
                         ("设置", self._show_settings)]:
            tk.Button(btn_frame, text=text, font=('微软雅黑', 10),
                     bg=C['accent_hover'], fg='white', relief=tk.FLAT,
                     padx=15, pady=5, cursor='hand2',
                     activebackground=C['accent_light'],
                     command=cmd).pack(side=tk.LEFT, padx=3)
        
        # 状态指示
        self.status_indicator = tk.Label(btn_frame, text="未配置", 
                                        font=('微软雅黑', 9), bg=C['accent'], fg='#ffd700')
        self.status_indicator.pack(side=tk.RIGHT, padx=10)
        
        # ===== 主内容区 =====
        main_container = tk.Frame(self.root, bg=C['bg_dark'])
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # 左侧面板
        left_panel = tk.Frame(main_container, bg=C['bg_medium'], width=280)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=0, pady=0)
        left_panel.pack_propagate(False)
        
        # 左侧 - 小说信息卡片
        info_card = tk.Frame(left_panel, bg=C['bg_card'], padx=15, pady=15)
        info_card.pack(fill=tk.X, padx=10, pady=10)
        
        self.title_var = tk.StringVar(value="未创建小说")
        tk.Label(info_card, textvariable=self.title_var, font=('微软雅黑', 12, 'bold'),
                bg=C['bg_card'], fg=C['text_primary']).pack(anchor=tk.W)
        
        info_grid = tk.Frame(info_card, bg=C['bg_card'])
        info_grid.pack(fill=tk.X, pady=(10, 0))
        
        self.genre_var = tk.StringVar(value="-")
        self.chapter_var = tk.StringVar(value="0/0")
        self.word_count_var = tk.StringVar(value="0")
        
        for i, (label, var) in enumerate([("类型", self.genre_var), ("进度", self.chapter_var), ("字数", self.word_count_var)]):
            tk.Label(info_grid, text=label, font=('微软雅黑', 9), bg=C['bg_card'], fg=C['text_muted']).grid(row=i, column=0, sticky=tk.W, pady=2)
            tk.Label(info_grid, textvariable=var, font=('微软雅黑', 9), bg=C['bg_card'], fg=C['text_secondary']).grid(row=i, column=1, sticky=tk.W, padx=(10, 0), pady=2)
        
        # 左侧 - 模式切换
        mode_frame = tk.Frame(left_panel, bg=C['bg_medium'], padx=10, pady=5)
        mode_frame.pack(fill=tk.X, padx=10)
        
        tk.Label(mode_frame, text="创作模式", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_medium'], fg=C['accent_light']).pack(anchor=tk.W, pady=(0, 5))
        
        # 自动创作按钮
        self.auto_btn = tk.Button(mode_frame, text="自动创作", font=('微软雅黑', 10),
                                 bg=C['accent'], fg='white', relief=tk.FLAT,
                                 padx=10, pady=8, cursor='hand2', width=20,
                                 activebackground=C['accent_hover'],
                                 command=self._auto_generate)
        self.auto_btn.pack(fill=tk.X, pady=2)
        
        # AI辅助写作按钮
        self.assist_btn = tk.Button(mode_frame, text="AI辅助写作 (F11)", font=('微软雅黑', 10),
                                   bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT,
                                   padx=10, pady=8, cursor='hand2', width=20,
                                   activebackground=C['hover'],
                                   command=self._open_fullscreen_writer)
        self.assist_btn.pack(fill=tk.X, pady=2)
        
        # 左侧 - 智能体步骤
        agent_frame = tk.Frame(left_panel, bg=C['bg_medium'], padx=10, pady=5)
        agent_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        
        tk.Label(agent_frame, text="智能体步骤", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_medium'], fg=C['accent_light']).pack(anchor=tk.W, pady=(0, 5))
        
        steps = [
            ("1. 世界观", self._gen_settings),
            ("2. 角色", self._gen_characters),
            ("3. 大纲", self._gen_outline),
            ("4. 生成章节", self._gen_chapter),
            ("5. 审校", self._review_chapter),
        ]
        
        for text, cmd in steps:
            btn = tk.Button(agent_frame, text=text, font=('微软雅黑', 9),
                          bg=C['bg_light'], fg=C['text_secondary'], relief=tk.FLAT,
                          padx=8, pady=5, cursor='hand2', anchor=tk.W,
                          activebackground=C['hover'],
                          command=cmd)
            btn.pack(fill=tk.X, pady=1)
        
        # 左侧 - 角色面板
        char_frame = tk.Frame(left_panel, bg=C['bg_medium'], padx=10, pady=5)
        char_frame.pack(fill=tk.X, padx=10, pady=(5, 0))
        
        tk.Label(char_frame, text="角色面板", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_medium'], fg=C['accent_light']).pack(anchor=tk.W, pady=(0, 3))
        
        # 角色选择下拉框
        char_select_frame = tk.Frame(char_frame, bg=C['bg_medium'])
        char_select_frame.pack(fill=tk.X, pady=2)
        self.char_select_var = tk.StringVar(value="无角色")
        self.char_select_combo = ttk.Combobox(char_select_frame, textvariable=self.char_select_var, 
                                              state="readonly", width=15)
        self.char_select_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.char_select_combo.bind('<<ComboboxSelected>>', self._on_char_select)
        
        # 角色信息显示
        self.char_summary = tk.Label(char_frame, text="未创建角色", font=('微软雅黑', 8),
                                    bg=C['bg_medium'], fg=C['text_secondary'], justify=tk.LEFT, anchor=tk.W)
        self.char_summary.pack(fill=tk.X, pady=3)
        
        # 角色操作按钮
        char_btn_frame = tk.Frame(char_frame, bg=C['bg_medium'])
        char_btn_frame.pack(fill=tk.X, pady=3)
        tk.Button(char_btn_frame, text="新建", font=('微软雅黑', 8),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=4,
                 command=self._create_character_dialog).pack(side=tk.LEFT, padx=1)
        tk.Button(char_btn_frame, text="AI创建", font=('微软雅黑', 8),
                 bg=C['success'], fg='white', relief=tk.FLAT, padx=4,
                 command=self._ai_create_character).pack(side=tk.LEFT, padx=1)
        tk.Button(char_btn_frame, text="武器", font=('微软雅黑', 8),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=4,
                 command=self._equip_weapon).pack(side=tk.LEFT, padx=1)
        tk.Button(char_btn_frame, text="技能", font=('微软雅黑', 8),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=4,
                 command=self._learn_skill).pack(side=tk.LEFT, padx=1)
        tk.Button(char_btn_frame, text="详情", font=('微软雅黑', 8),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=4,
                 command=self._show_char_detail).pack(side=tk.RIGHT, padx=1)
        
        # 左侧 - 大纲列表
        outline_frame = tk.Frame(left_panel, bg=C['bg_medium'], padx=10, pady=5)
        outline_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 10))
        
        tk.Label(outline_frame, text="章节大纲", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_medium'], fg=C['accent_light']).pack(anchor=tk.W, pady=(0, 5))
        
        # 大纲列表框
        list_frame = tk.Frame(outline_frame, bg=C['bg_dark'])
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.outline_list = tk.Listbox(list_frame, bg=C['bg_dark'], fg=C['text_secondary'],
                                      font=('微软雅黑', 9), selectbackground=C['accent'],
                                      selectforeground='white', relief=tk.FLAT,
                                      highlightthickness=0, borderwidth=0)
        scrollbar = tk.Scrollbar(list_frame, command=self.outline_list.yview)
        self.outline_list.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.outline_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.outline_list.bind('<<ListboxSelect>>', self._on_outline_select)
        
        # ===== 右侧主内容区 =====
        right_panel = tk.Frame(main_container, bg=C['bg_dark'])
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 右侧 - 标签页
        self.notebook = ttk.Notebook(right_panel, style='Dark.TNotebook')
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # === 章节内容页 ===
        chapter_frame = tk.Frame(self.notebook, bg=C['bg_dark'])
        self.notebook.add(chapter_frame, text=" 章节内容 ")
        
        # 章节标题
        self.chapter_title_var = tk.StringVar(value="选择或生成章节")
        tk.Label(chapter_frame, textvariable=self.chapter_title_var, 
                font=('微软雅黑', 13, 'bold'), bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=15, pady=(10, 5))
        
        # 写作区域
        text_frame = tk.Frame(chapter_frame, bg=C['bg_dark'])
        text_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))
        
        self.content_text = tk.Text(text_frame, wrap=tk.WORD, font=('微软雅黑', 11),
                                   bg=C['bg_card'], fg=C['text_primary'],
                                   insertbackground=C['accent_light'],
                                   selectbackground=C['accent'],
                                   relief=tk.FLAT, padx=15, pady=15,
                                   spacing1=3, spacing3=3, undo=True)
        
        content_scrollbar = tk.Scrollbar(text_frame, command=self.content_text.yview)
        self.content_text.configure(yscrollcommand=content_scrollbar.set)
        content_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.content_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 绑定文本变化事件
        self.content_text.bind('<KeyRelease>', self._on_text_change)
        
        # === 日志页 ===
        log_frame = tk.Frame(self.notebook, bg=C['bg_dark'])
        self.notebook.add(log_frame, text=" 运行日志 ")
        
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, font=('Consolas', 10),
                               bg=C['bg_card'], fg=C['text_muted'],
                               relief=tk.FLAT, padx=15, pady=15, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # === 审校结果页 ===
        review_frame = tk.Frame(self.notebook, bg=C['bg_dark'])
        self.notebook.add(review_frame, text=" 审校结果 ")
        
        self.review_text = tk.Text(review_frame, wrap=tk.WORD, font=('微软雅黑', 11),
                                  bg=C['bg_card'], fg=C['text_primary'],
                                  relief=tk.FLAT, padx=15, pady=15)
        self.review_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # === 笔记页 ===
        notes_frame = tk.Frame(self.notebook, bg=C['bg_dark'])
        self.notebook.add(notes_frame, text=" 笔记 ")
        
        # 笔记类型选择
        note_type_frame = tk.Frame(notes_frame, bg=C['bg_dark'])
        note_type_frame.pack(fill=tk.X, padx=15, pady=(15, 5))
        
        self.note_type_var = tk.StringVar(value="project")
        for val, label in [("project", "工程笔记"), ("doc", "文档笔记"), ("sticky", "便笺本")]:
            tk.Radiobutton(note_type_frame, text=label, variable=self.note_type_var, value=val,
                          font=('微软雅黑', 9), bg=C['bg_dark'], fg=C['text_secondary'],
                          selectcolor=C['accent'], activebackground=C['bg_dark'],
                          command=self._refresh_notes).pack(side=tk.LEFT, padx=10)
        
        tk.Button(note_type_frame, text="+ 新建", font=('微软雅黑', 9),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._add_note).pack(side=tk.RIGHT)
        
        # 笔记列表和内容
        note_content_frame = tk.Frame(notes_frame, bg=C['bg_dark'])
        note_content_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        self.notes_list = tk.Listbox(note_content_frame, bg=C['bg_card'], fg=C['text_secondary'],
                                    font=('微软雅黑', 9), selectbackground=C['accent'],
                                    relief=tk.FLAT, highlightthickness=0, width=30)
        self.notes_list.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        self.notes_list.bind('<<ListboxSelect>>', self._on_note_select)
        
        self.note_content = tk.Text(note_content_frame, wrap=tk.WORD, font=('微软雅黑', 11),
                                   bg=C['bg_card'], fg=C['text_primary'],
                                   relief=tk.FLAT, padx=15, pady=15)
        self.note_content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 笔记操作按钮
        note_btn_frame = tk.Frame(notes_frame, bg=C['bg_dark'])
        note_btn_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        tk.Button(note_btn_frame, text="保存笔记", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._save_note).pack(side=tk.LEFT, padx=5)
        tk.Button(note_btn_frame, text="删除笔记", font=('微软雅黑', 9),
                 bg=C['error'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._delete_note).pack(side=tk.LEFT, padx=5)
        tk.Button(note_btn_frame, text="发送到工程", font=('微软雅黑', 9),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=10,
                 command=self._send_sticky_to_project).pack(side=tk.RIGHT, padx=5)
        
        # === 创作工具页 ===
        toolkit_frame = tk.Frame(self.notebook, bg=C['bg_dark'])
        self.notebook.add(toolkit_frame, text=" 创作工具 ")
        
        # 工具选择
        tool_select_frame = tk.Frame(toolkit_frame, bg=C['bg_dark'])
        tool_select_frame.pack(fill=tk.X, padx=15, pady=(15, 5))
        
        self.tool_type_var = tk.StringVar(value="elements")
        tools = [("elements", "元素库"), ("bridges", "桥段库"), ("descriptions", "描写库"),
                 ("dialogue", "对话推演"), ("story_flow", "故事流"), ("style", "风格转换"),
                 ("adapt", "智能改编"), ("websearch", "热点改编"), ("chapters", "章节分析")]
        
        for val, label in tools:
            tk.Radiobutton(tool_select_frame, text=label, variable=self.tool_type_var, value=val,
                          font=('微软雅黑', 9), bg=C['bg_dark'], fg=C['text_secondary'],
                          selectcolor=C['accent'], activebackground=C['bg_dark'],
                          command=self._refresh_toolkit).pack(side=tk.LEFT, padx=8)
        
        # 工具内容区
        self.tool_content_frame = tk.Frame(toolkit_frame, bg=C['bg_dark'])
        self.tool_content_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        # 初始化工具集界面
        self._refresh_toolkit()
        
        # === 阅读管理器页 ===
        reader_frame = tk.Frame(self.notebook, bg=C['bg_dark'])
        self.notebook.add(reader_frame, text=" 阅读管理器 ")
        
        # 阅读管理器内容
        self._build_reader_ui(reader_frame)
    
    def _build_reader_ui(self, parent):
        """构建阅读管理器界面"""
        C = UIStyle.COLORS
        
        # 工具栏
        toolbar = tk.Frame(parent, bg=C['bg_medium'])
        toolbar.pack(fill=tk.X, padx=15, pady=(15, 5))
        
        tk.Button(toolbar, text="导入书籍", font=('微软雅黑', 9),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._import_book).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="刷新书库", font=('微软雅黑', 9),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=10,
                 command=self._refresh_library).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="搜索", font=('微软雅黑', 9),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=10,
                 command=self._search_in_book).pack(side=tk.LEFT, padx=5)
        
        # 搜索框
        self.search_var = tk.StringVar()
        search_entry = tk.Entry(toolbar, textvariable=self.search_var, 
                               font=('微软雅黑', 9), width=20,
                               bg=C['input_bg'], fg=C['text_primary'])
        search_entry.pack(side=tk.LEFT, padx=5)
        
        # 书库列表和阅读区域
        main_frame = tk.Frame(parent, bg=C['bg_dark'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 15))
        
        # 左侧书库列表
        left_frame = tk.Frame(main_frame, bg=C['bg_dark'], width=250)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_frame.pack_propagate(False)
        
        tk.Label(left_frame, text="书库", font=('微软雅黑', 11, 'bold'),
                bg=C['bg_dark'], fg=C['accent_light']).pack(anchor=tk.W, pady=(0, 10))
        
        # 书库列表框
        list_frame = tk.Frame(left_frame, bg=C['bg_dark'])
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.library_list = tk.Listbox(list_frame, bg=C['bg_card'], fg=C['text_secondary'],
                                      font=('微软雅黑', 9), selectbackground=C['accent'],
                                      relief=tk.FLAT, highlightthickness=0)
        scrollbar = tk.Scrollbar(list_frame, command=self.library_list.yview)
        self.library_list.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.library_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.library_list.bind('<<ListboxSelect>>', self._on_book_select)
        
        # 书签列表
        bookmark_frame = tk.Frame(left_frame, bg=C['bg_dark'])
        bookmark_frame.pack(fill=tk.X, pady=(10, 0))
        
        tk.Label(bookmark_frame, text="书签", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_dark'], fg=C['accent_light']).pack(anchor=tk.W, pady=(0, 5))
        
        self.bookmark_list = tk.Listbox(bookmark_frame, bg=C['bg_card'], fg=C['text_secondary'],
                                       font=('微软雅黑', 8), height=4,
                                       relief=tk.FLAT, highlightthickness=0)
        self.bookmark_list.pack(fill=tk.X)
        self.bookmark_list.bind('<<ListboxSelect>>', self._on_bookmark_select)
        
        # 书签操作按钮
        bookmark_btn_frame = tk.Frame(bookmark_frame, bg=C['bg_dark'])
        bookmark_btn_frame.pack(fill=tk.X, pady=(5, 0))
        tk.Button(bookmark_btn_frame, text="导入书签", font=('微软雅黑', 8),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=5,
                 command=self._import_bookmarks).pack(side=tk.LEFT, padx=2)
        tk.Button(bookmark_btn_frame, text="导出书签", font=('微软雅黑', 8),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=5,
                 command=self._export_bookmarks).pack(side=tk.LEFT, padx=2)
        
        # 右侧阅读区域
        right_frame = tk.Frame(main_frame, bg=C['bg_dark'])
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 阅读工具栏
        read_toolbar = tk.Frame(right_frame, bg=C['bg_medium'])
        read_toolbar.pack(fill=tk.X, pady=(0, 10))
        
        # 字体大小
        tk.Label(read_toolbar, text="字体:", font=('微软雅黑', 9),
                bg=C['bg_medium'], fg=C['text_secondary']).pack(side=tk.LEFT, padx=5)
        self.font_size_var = tk.StringVar(value="16")
        font_size_spin = tk.Spinbox(read_toolbar, from_=10, to=36, width=5,
                                   textvariable=self.font_size_var,
                                   command=self._update_reader_font)
        font_size_spin.pack(side=tk.LEFT, padx=5)
        
        # 主题选择
        tk.Label(read_toolbar, text="主题:", font=('微软雅黑', 9),
                bg=C['bg_medium'], fg=C['text_secondary']).pack(side=tk.LEFT, padx=5)
        self.reader_theme_var = tk.StringVar(value="light")
        themes = [("浅色", "light"), ("深色", "dark"), ("护眼", "sepia")]
        for text, value in themes:
            tk.Radiobutton(read_toolbar, text=text, variable=self.reader_theme_var, value=value,
                          font=('微软雅黑', 8), bg=C['bg_medium'], fg=C['text_secondary'],
                          selectcolor=C['accent'], command=self._change_reader_theme).pack(side=tk.LEFT, padx=2)
        
        # 添加书签按钮
        tk.Button(read_toolbar, text="添加书签", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._add_bookmark).pack(side=tk.RIGHT, padx=5)
        
        # 阅读内容区域
        self.reader_text = tk.Text(right_frame, wrap=tk.WORD, font=('微软雅黑', 16),
                                  bg='#f5f0e8', fg='#2c2c2c',
                                  padx=20, pady=20, spacing1=3, spacing3=3,
                                  relief=tk.FLAT, state=tk.DISABLED)
        
        reader_scrollbar = tk.Scrollbar(right_frame, command=self.reader_text.yview)
        self.reader_text.configure(yscrollcommand=reader_scrollbar.set)
        reader_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.reader_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 当前书籍信息
        self.current_book_path = None
        self.current_book_content = None
        
        # 初始化书库
        self._refresh_library()
        self._refresh_bookmarks()
    
    def _import_book(self):
        """导入书籍"""
        file_path = filedialog.askopenfilename(
            title="选择书籍文件",
            filetypes=[
                ("所有支持格式", "*.txt *.epub *.pdf *.docx *.md"),
                ("TXT文件", "*.txt"),
                ("EPUB文件", "*.epub"),
                ("PDF文件", "*.pdf"),
                ("Word文档", "*.docx"),
                ("Markdown文件", "*.md"),
                ("所有文件", "*.*"),
            ]
        )
        
        if file_path:
            meta = self.reading_manager.import_book(file_path)
            if meta:
                self._log(f"已导入书籍: {meta['title']}")
                self._refresh_library()
                messagebox.showinfo("成功", f"已导入《{meta['title']}》")
            else:
                messagebox.showerror("错误", "导入失败，不支持该文件格式")
    
    def _refresh_library(self):
        """刷新书库列表"""
        self.library_list.delete(0, tk.END)
        books = self.reading_manager.get_library_books()
        for book in books:
            self.library_list.insert(tk.END, f"{book['title']} ({book['format']})")
    
    def _refresh_bookmarks(self):
        """刷新书签列表"""
        self.bookmark_list.delete(0, tk.END)
        bookmarks = self.reading_manager.get_bookmarks()
        for bm in bookmarks:
            self.bookmark_list.insert(tk.END, f"{bm['title']} - {bm.get('position', 0)}%")
    
    def _on_book_select(self, event):
        """书籍选中事件"""
        selection = self.library_list.curselection()
        if not selection:
            return
        
        books = self.reading_manager.get_library_books()
        idx = selection[0]
        if idx < len(books):
            book = books[idx]
            self._load_book(book['file_path'])
    
    def _on_bookmark_select(self, event):
        """书签选中事件"""
        selection = self.bookmark_list.curselection()
        if not selection:
            return
        
        bookmarks = self.reading_manager.get_bookmarks()
        idx = selection[0]
        if idx < len(bookmarks):
            bookmark = bookmarks[idx]
            # 加载对应的书籍并跳转到位置
            if bookmark.get('file_path'):
                self._load_book(bookmark['file_path'], bookmark.get('position', 0))
    
    def _load_book(self, file_path: str, position: int = 0):
        """加载书籍内容"""
        content = self.reading_manager.read_book(file_path)
        if content:
            self.current_book_path = file_path
            self.current_book_content = content
            
            # 显示内容
            self.reader_text.config(state=tk.NORMAL)
            self.reader_text.delete("1.0", tk.END)
            self.reader_text.insert("1.0", content)
            self.reader_text.config(state=tk.DISABLED)
            
            # 跳转到指定位置
            if position > 0:
                # 计算字符位置
                char_pos = int(len(content) * position / 100)
                self.reader_text.see(f"1.0+{char_pos}c")
            
            self._log(f"已加载书籍: {Path(file_path).name}")
        else:
            messagebox.showerror("错误", "无法读取书籍内容")
    
    def _update_reader_font(self):
        """更新阅读字体大小"""
        try:
            size = int(self.font_size_var.get())
            self.reader_text.configure(font=('微软雅黑', size))
        except ValueError:
            pass
    
    def _change_reader_theme(self):
        """改变阅读主题"""
        theme = self.reader_theme_var.get()
        themes = {
            'light': {'bg': '#f5f0e8', 'fg': '#2c2c2c'},
            'dark': {'bg': '#1e1e2e', 'fg': '#f8fafc'},
            'sepia': {'bg': '#f4f0e8', 'fg': '#5c4b37'},
        }
        
        if theme in themes:
            self.reader_text.configure(bg=themes[theme]['bg'], fg=themes[theme]['fg'])
    
    def _add_bookmark(self):
        """添加书签"""
        if not self.current_book_path:
            messagebox.showinfo("提示", "请先打开一本书")
            return
        
        # 获取当前位置（百分比）
        content = self.current_book_content or ""
        # 简单估算：基于滚动位置
        try:
            first_visible = self.reader_text.index("@0,0")
            # 解析行号
            line_num = int(first_visible.split('.')[0])
            total_lines = int(self.reader_text.index(tk.END).split('.')[0])
            position = int(line_num / total_lines * 100) if total_lines > 0 else 0
        except:
            position = 0
        
        title = f"书签 - {Path(self.current_book_path).stem} - {position}%"
        self.reading_manager.add_bookmark(self.current_book_path, position, title)
        self._refresh_bookmarks()
        self._log(f"已添加书签: {title}")
    
    def _import_bookmarks(self):
        """导入书签"""
        file_path = filedialog.askopenfilename(
            title="导入书签",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                bookmarks = json.load(f)
            
            if isinstance(bookmarks, list):
                for bm in bookmarks:
                    if 'book_path' in bm and 'position' in bm:
                        self.reading_manager.add_bookmark(
                            bm['book_path'],
                            bm['position'],
                            bm.get('title', '导入的书签')
                        )
                self._refresh_bookmarks()
                self._log(f"已导入 {len(bookmarks)} 个书签")
                messagebox.showinfo("成功", f"已导入 {len(bookmarks)} 个书签")
            else:
                messagebox.showerror("错误", "无效的书签文件格式")
        except Exception as e:
            messagebox.showerror("错误", f"导入失败: {str(e)}")
    
    def _export_bookmarks(self):
        """导出书签"""
        if not self.reading_manager.bookmarks:
            messagebox.showinfo("提示", "没有可导出的书签")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="导出书签",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json")]
        )
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.reading_manager.bookmarks, f, indent=2, ensure_ascii=False)
            self._log(f"已导出 {len(self.reading_manager.bookmarks)} 个书签")
            messagebox.showinfo("成功", f"已导出 {len(self.reading_manager.bookmarks)} 个书签")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {str(e)}")
    
    def _search_in_book(self):
        """在当前书籍中搜索"""
        if not self.current_book_path:
            messagebox.showinfo("提示", "请先打开一本书")
            return
        
        keyword = self.search_var.get().strip()
        if not keyword:
            messagebox.showinfo("提示", "请输入搜索关键词")
            return
        
        results = self.reading_manager.search_in_book(self.current_book_path, keyword)
        if results:
            # 高亮显示搜索结果
            self.reader_text.tag_remove('search_highlight', '1.0', tk.END)
            self.reader_text.tag_configure('search_highlight', background='#ffff00', foreground='#000000')
            
            for result in results[:10]:  # 最多显示10个结果
                line_num = result['line_number']
                # 高亮该行中的关键词
                start = f"{line_num}.0"
                end = f"{line_num}.end"
                self.reader_text.tag_add('search_highlight', start, end)
            
            # 跳转到第一个结果
            self.reader_text.see(f"{results[0]['line_number']}.0")
            self._log(f"找到 {len(results)} 个匹配结果")
        else:
            messagebox.showinfo("搜索", "未找到匹配内容")
    
    def _on_text_change(self, event=None):
        """文本变化事件 - 更新字数统计"""
        content = self.content_text.get("1.0", tk.END).strip()
        self.word_count_var.set(str(len(content)))
        self.is_modified = True
    
    def _log(self, message: str):
        """添加日志（线程安全）"""
        def _do_log():
            self.log_text.config(state=tk.NORMAL)
            timestamp = time.strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        try:
            self.root.after(0, _do_log)
        except:
            pass
    
    def _update_status(self):
        """更新状态栏"""
        if self.ai_client.is_configured():
            provider = self.config.get("api_provider", "ollama")
            model = self.config.get("model", "")
            img_status = " + 文生图" if self.image_gen.is_configured() else ""
            self.status_indicator.config(text=f"{provider}/{model}{img_status}", fg='#10b981')
        else:
            self.status_indicator.config(text="未配置AI", fg='#ffd700')
    
    def _new_novel(self):
        """新建小说"""
        dialog = tk.Toplevel(self.root)
        dialog.title("新建小说")
        # 窗口大小适配屏幕
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(700, sw - 80), min(650, sh - 80)
        x, y = (sw - w) // 2, (sh - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.resizable(True, True)
        dialog.minsize(550, 450)
        dialog.transient(self.root)
        dialog.grab_set()
        
        C = UIStyle.COLORS
        
        # ===== 底部固定区域（先pack，确保始终可见）=====
        bottom = tk.Frame(dialog, bg=C['bg_dark'])
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=8)
        
        # 核心概念
        concept_row = tk.Frame(bottom, bg=C['bg_dark'])
        concept_row.pack(fill=tk.X, pady=(0, 5))
        tk.Label(concept_row, text="核心概念:", bg=C['bg_dark'], fg=C['text_primary'], font=('微软雅黑', 9)).pack(side=tk.LEFT)
        concept_entry = tk.Entry(concept_row, font=('微软雅黑', 9), bg=C['bg_card'], fg=C['text_primary'],
                                insertbackground=C['text_primary'], relief=tk.FLAT)
        concept_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # 章节数 + 创建按钮
        action_row = tk.Frame(bottom, bg=C['bg_dark'])
        action_row.pack(fill=tk.X)
        tk.Label(action_row, text="章节数:", bg=C['bg_dark'], fg=C['text_primary'], font=('微软雅黑', 9)).pack(side=tk.LEFT)
        chapters_var = tk.StringVar(value="20")
        tk.Spinbox(action_row, from_=1, to=500, textvariable=chapters_var, width=6,
                  font=('微软雅黑', 9), bg=C['bg_card'], fg=C['text_primary']).pack(side=tk.LEFT, padx=5)
        
        # ===== 顶部固定区域 =====
        top = tk.Frame(dialog, bg=C['bg_dark'])
        top.pack(side=tk.TOP, fill=tk.X, padx=15, pady=(10, 0))
        
        tk.Label(top, text="小说标题:", bg=C['bg_dark'], fg=C['text_primary'], font=('微软雅黑', 9)).grid(row=0, column=0, sticky=tk.W, pady=3)
        title_entry = tk.Entry(top, font=('微软雅黑', 10), bg=C['bg_card'], fg=C['text_primary'], insertbackground=C['text_primary'], relief=tk.FLAT, width=40)
        title_entry.grid(row=0, column=1, sticky=tk.EW, padx=(5, 0), pady=3)
        
        tk.Label(top, text="小说频道:", bg=C['bg_dark'], fg=C['text_primary'], font=('微软雅黑', 9)).grid(row=1, column=0, sticky=tk.W, pady=3)
        channel_var = tk.StringVar(value="male")
        ch_frame = tk.Frame(top, bg=C['bg_dark'])
        ch_frame.grid(row=1, column=1, sticky=tk.W, padx=(5, 0), pady=3)
        
        # 男女频类型列表
        MALE_GENRES = [
            "玄幻-东方玄幻", "玄幻-异世大陆", "玄幻-高武世界",
            "仙侠-古典仙侠", "仙侠-现代修真", "仙侠-洪荒封神",
            "都市-都市生活", "都市-都市异能", "都市-青春校园",
            "历史-架空历史", "历史-两宋元明", "历史-三国争霸",
            "科幻-星际文明", "科幻-末世危机", "科幻-时空穿梭",
            "悬疑-灵异恐怖", "悬疑-侦探推理", "悬疑-探险揭秘",
            "游戏-电子竞技", "游戏-虚拟网游", "游戏-游戏异界",
            "军事-抗战烽火", "军事-谍战特工", "军事-战争幻想",
            "武侠-传统武侠", "武侠-国术古武", "武侠-武侠幻想",
            "体育-篮球风云", "体育-足球天下", "体育-综合竞技",
            "轻小说-原生幻想", "轻小说-搞笑吐槽", "轻小说-恋爱日常",
            "二次元-青春日常", "二次元-变身入替", "二次元-同人衍生",
        ]
        FEMALE_GENRES = [
            "古代言情-女尊王朝", "古代言情-宫闱宅斗", "古代言情-穿越奇情",
            "现代言情-豪门总裁", "现代言情-都市婚恋", "现代言情-职场丽人",
            "幻想言情-异世恋歌", "幻想言情-快穿攻略", "幻想言情-魔法幻情",
            "纯爱-古代纯爱", "纯爱-现代纯爱", "纯爱-幻想纯爱",
            "浪漫青春-青春校园", "浪漫青春-疼痛成长", "浪漫青春-纯爱唯美",
            "仙侠奇缘-古典仙缘", "仙侠奇缘-修仙情劫", "仙侠奇缘-洪荒情缘",
            "悬疑灵异-推理侦探", "悬疑灵异-恐怖惊悚", "悬疑灵异-灵异鬼怪",
            "游戏竞技-电子竞技", "游戏竞技-全息网游", "游戏竞技-电竞爱情",
            "短篇-短篇言情", "短篇-微小说", "短篇-轻小说",
        ]
        
        tk.Label(top, text="小说类型:", bg=C['bg_dark'], fg=C['text_primary'], font=('微软雅黑', 9)).grid(row=2, column=0, sticky=tk.W, pady=3)
        genre_var = tk.StringVar(value=MALE_GENRES[0])
        genre_combo = ttk.Combobox(top, textvariable=genre_var, values=MALE_GENRES, state="readonly", width=35)
        genre_combo.grid(row=2, column=1, sticky=tk.EW, padx=(5, 0), pady=3)
        top.columnconfigure(1, weight=1)
        
        # 男生标签（8类 80+标签）
        MALE_TAGS = {
            "角色设定": ["废材崛起", "扮猪吃虎", "杀伐果断", "智商在线", "低调男主", "独行侠", "狠人大帝", "稳健型", "腹黑型", "热血少年", "冷面高手", "逍遥自在", "护短", "不圣母", "有底线", "重生者"],
            "情节元素": ["系统流", "穿越大军", "重生复仇", "无敌流", "升级流", "种田流", "争霸流", "诸天流", "无限流", "签到流", "数据化", "聊天群", "直播流", "召唤流", "转生流", "模拟器"],
            "世界观": ["异界大陆", "王朝争霸", "宗门林立", "末世废土", "星空宇宙", "灵气复苏", "赛博朋克", "求生冒险", "东方神话", "洪荒封神", "修真文明", "巫师世界"],
            "爽点标签": ["越级挑战", "越阶杀敌", "装逼打脸", "逆天改命", "一人成军", "万古不朽", "超神之路", "武道巅峰", "碾压全场", "秀翻天", "骚操作", "神级操作"],
            "成长路线": ["废柴逆袭", "天才陨落再起", "散修崛起", "赘婿翻身", "上门女婿", "退婚打脸", "回归都市", "隐世归来", "退役兵王", "回归豪门"],
            "战斗风格": ["肉身成圣", "剑道独尊", "拳拳到肉", "法术流", "武技流", "炼丹大师", "阵法宗师", "器道大师", "驭兽师", "暗杀流", "群战之王"],
            "感情线": ["单女主", "多女主", "后宫流", "无女主", "暧昧流", "青梅竹马", "天降系", "傲娇女主", "御姐型", "萝莉型", "病娇女主"],
            "特殊设定": ["万界穿梭", "时间回溯", "读心术", "透视眼", "隐身术", "空间戒指", "金手指", "老爷爷", "神级血脉", "远古传承", "神器认主", "神兽伙伴"],
        }
        FEMALE_TAGS = {
            "角色设定": ["甜宠女主", "女强逆袭", "马甲大佬", "团宠担当", "万人迷", "病娇偏执", "霸总老公", "白月光", "替身前妻", "软萌娇妻", "女王御姐", "萌宝来袭", "戏精女主", "佛系女主", "毒舌女主", "学霸女主"],
            "情节元素": ["先婚后爱", "追妻火葬场", "带球跑", "契约婚姻", "养成系", "宅斗宫斗", "真假千金", "失忆重逢", "假戏真做", "隐婚密爱", "替身文学", "重生虐渣", "闪婚闪离", "破镜重圆", "日久生情", "强取豪夺"],
            "气氛风格": ["虐恋情深", "欢喜冤家", "温馨治愈", "爆笑甜宠", "暗恋成真", "虐渣打脸", "逆袭爽文", "甜到齁", "虐到哭", "轻松欢脱", "高甜无虐", "玻璃渣里找糖"],
            "甜宠类型": ["一见钟情", "日久生情", "暗恋成真", "宠妻狂魔", "双向奔赴", "青梅竹马", "师生恋", "姐弟恋", "大叔宠", "萌宝助攻", "豪门恩怨", "总裁文"],
            "身份设定": ["豪门千金", "落魄千金", "穿越女主", "重生女主", "系统女主", "异能女主", "修仙女主", "古代女主", "现代女主", "末世女主", "娱乐圈女主", "军嫂文"],
            "男主人设": ["霸道总裁", "冷面军少", "腹黑王爷", "温柔竹马", "傲娇少爷", "冰山校草", "禁欲系", "病娇男主", "忠犬男主", "渣男回头", "高冷学长", "阳光少年"],
            "感情模式": ["甜宠", "先虐后甜", "先甜后虐", "甜虐交织", "高甜", "暗恋", "明恋", "单箭头", "双箭头", "三角恋", "四角恋", "骨科"],
            "特殊元素": ["萌宝", "双胞胎", "龙凤胎", "穿越", "重生", "系统", "空间", "异能", "修仙", "娱乐圈", "豪门", "校园"],
        }
        
        # ===== 中间可滚动标签区域 =====
        tag_outer = tk.LabelFrame(dialog, text=" 附加标签（可多选，鼠标滚轮滚动） ", padx=5, pady=5,
                                  bg=C['bg_dark'], fg=C['accent_light'], font=('微软雅黑', 9))
        tag_outer.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        tag_canvas = tk.Canvas(tag_outer, bg=C['bg_dark'], highlightthickness=0, bd=0)
        tag_scrollbar = tk.Scrollbar(tag_outer, orient=tk.VERTICAL, command=tag_canvas.yview)
        tag_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tag_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tag_canvas.configure(yscrollcommand=tag_scrollbar.set)
        
        tags_container = tk.Frame(tag_canvas, bg=C['bg_dark'])
        tag_canvas_window = tag_canvas.create_window((0, 0), window=tags_container, anchor=tk.NW)
        
        # 鼠标滚轮滚动标签（仅在标签区域生效）
        def on_mousewheel(event):
            tag_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        tag_canvas.bind("<MouseWheel>", on_mousewheel)
        tags_container.bind("<MouseWheel>", on_mousewheel)
        
        # 使tags_container宽度跟随canvas
        def on_canvas_configure(event):
            tag_canvas.itemconfig(tag_canvas_window, width=event.width)
        tag_canvas.bind("<Configure>", on_canvas_configure)
        
        self.tag_vars = {}
        
        def update_tags(channel):
            """更新标签显示"""
            genre_combo['values'] = MALE_GENRES if channel == "male" else FEMALE_GENRES
            genre_var.set(MALE_GENRES[0] if channel == "male" else FEMALE_GENRES[0])
            for w in tags_container.winfo_children():
                w.destroy()
            self.tag_vars.clear()
            tags = MALE_TAGS if channel == "male" else FEMALE_TAGS
            for cat_name, cat_tags in tags.items():
                cat_label = tk.Label(tags_container, text=cat_name, font=("微软雅黑", 9, "bold"),
                                    bg=C['bg_dark'], fg=C['accent_light'], anchor=tk.W)
                cat_label.pack(fill=tk.X, pady=(6, 1), padx=5)
                tag_line = tk.Frame(tags_container, bg=C['bg_dark'])
                tag_line.pack(fill=tk.X, padx=5)
                for tag in cat_tags:
                    var = tk.BooleanVar(value=False)
                    self.tag_vars[tag] = var
                    cb = tk.Checkbutton(tag_line, text=tag, variable=var, font=("微软雅黑", 8),
                                       bg=C['bg_dark'], fg=C['text_secondary'],
                                       selectcolor=C['bg_card'],
                                       activebackground=C['bg_dark'],
                                       activeforeground=C['accent_light'],
                                       relief=tk.FLAT, padx=1, pady=0)
                    cb.pack(side=tk.LEFT, padx=2, pady=1)
            tags_container.update_idletasks()
            tag_canvas.configure(scrollregion=tag_canvas.bbox("all"))
            tag_canvas.yview_moveto(0)
        
        # 频道选择
        for text, val in [("男生频道", "male"), ("女生频道", "female")]:
            rb = tk.Radiobutton(ch_frame, text=text, variable=channel_var, value=val,
                               command=lambda v=val: update_tags(v),
                               bg=C['bg_dark'], fg=C['text_primary'],
                               selectcolor=C['bg_card'],
                               activebackground=C['bg_dark'],
                               activeforeground=C['accent_light'],
                               font=('微软雅黑', 9))
            rb.pack(side=tk.LEFT, padx=8)
        
        # 初始化标签
        update_tags("male")
        
        # 自定义标签输入
        custom_frame = tk.Frame(tag_outer, bg=C['bg_dark'])
        custom_frame.pack(fill=tk.X, padx=5, pady=(3, 0))
        tk.Label(custom_frame, text="自定义:", bg=C['bg_dark'], fg=C['text_secondary'], font=('微软雅黑', 8)).pack(side=tk.LEFT)
        custom_tag_entry = tk.Entry(custom_frame, font=('微软雅黑', 9), bg=C['bg_card'], fg=C['text_primary'],
                                    insertbackground=C['text_primary'], relief=tk.FLAT, width=20)
        custom_tag_entry.pack(side=tk.LEFT, padx=3)
        
        def add_custom_tag():
            tag = custom_tag_entry.get().strip()
            if not tag:
                return
            if tag in self.tag_vars:
                messagebox.showinfo("提示", f"标签 '{tag}' 已存在")
                return
            var = tk.BooleanVar(value=True)
            self.tag_vars[tag] = var
            # 添加到最后一行
            last_line = None
            for w in tags_container.winfo_children():
                if isinstance(w, tk.Frame):
                    last_line = w
            if last_line is None:
                last_line = tk.Frame(tags_container, bg=C['bg_dark'])
                last_line.pack(fill=tk.X, padx=5)
            cb = tk.Checkbutton(last_line, text=tag, variable=var, font=("微软雅黑", 8),
                               bg=C['bg_card'], fg=C['accent_light'],
                               selectcolor=C['bg_dark'],
                               activebackground=C['bg_card'],
                               activeforeground=C['accent_light'],
                               relief=tk.RAISED, padx=3, pady=1)
            cb.pack(side=tk.LEFT, padx=2, pady=1)
            custom_tag_entry.delete(0, tk.END)
            self._log(f"添加自定义标签: {tag}")
        
        tk.Button(custom_frame, text="添加", command=add_custom_tag, font=('微软雅黑', 8),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=5).pack(side=tk.LEFT, padx=3)
        custom_tag_entry.bind("<Return>", lambda e: add_custom_tag())
        
        # ===== 底部固定区域（紧凑布局）=====
        bottom = tk.Frame(dialog, bg=C['bg_dark'])
        bottom.pack(fill=tk.X, padx=15, pady=(0, 5), side=tk.BOTTOM)
        
        # 核心概念（单行输入）
        concept_row = tk.Frame(bottom, bg=C['bg_dark'])
        concept_row.pack(fill=tk.X, pady=2)
        tk.Label(concept_row, text="核心概念:", bg=C['bg_dark'], fg=C['text_primary'], font=('微软雅黑', 9)).pack(side=tk.LEFT)
        concept_text = tk.Entry(concept_row, font=('微软雅黑', 9), bg=C['bg_card'], fg=C['text_primary'],
                               insertbackground=C['text_primary'], relief=tk.FLAT)
        concept_text.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # 章节数 + 创建按钮（同一行）
        action_row = tk.Frame(bottom, bg=C['bg_dark'])
        action_row.pack(fill=tk.X, pady=3)
        tk.Label(action_row, text="章节数:", bg=C['bg_dark'], fg=C['text_primary'], font=('微软雅黑', 9)).pack(side=tk.LEFT)
        chapters_var = tk.StringVar(value="20")
        tk.Spinbox(action_row, from_=1, to=500, textvariable=chapters_var, width=6,
                  font=('微软雅黑', 9), bg=C['bg_card'], fg=C['text_primary']).pack(side=tk.LEFT, padx=5)
        
        def confirm():
            title = title_entry.get().strip()
            if not title:
                messagebox.showwarning("提示", "请输入小说标题")
                return
            
            genre_full = genre_var.get().split("-")
            genre = genre_full[0] if len(genre_full) > 0 else ""
            sub_genre = genre_full[1] if len(genre_full) > 1 else ""
            concept = concept_entry.get().strip()
            chapters = int(chapters_var.get())
            
            # 收集选中的标签
            selected_tags = [tag for tag, var in self.tag_vars.items() if var.get()]
            
            # 创建小说目录
            safe_name = "".join(c for c in title if c.isalnum() or c in "_ -")[:30]
            novel_dir = self.config.novels_dir / f"{safe_name}_{int(time.time())}"
            novel_dir.mkdir(exist_ok=True)
            
            # 保存小说元数据
            meta = {
                "title": title,
                "genre": genre,
                "sub_genre": sub_genre,
                "channel": channel_var.get(),
                "tags": selected_tags,
                "concept": concept,
                "chapter_count": chapters,
                "created_at": datetime.now().isoformat(),
            }
            with open(novel_dir / "meta.json", 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
            
            # 初始化
            self.current_novel_dir = novel_dir
            self.memory = MemoryManager(novel_dir)
            self.agent = NovelAgent(self.ai_client, self.memory, log_callback=self._log, config=self.config)
            self.note_manager = NoteManager(novel_dir=novel_dir, config=self.config)
            self.outline = []
            self.current_chapter = 0
            self._init_character_system()
            
            self.title_var.set(title)
            self.genre_var.set(f"{genre}-{sub_genre}")
            self.chapter_var.set(f"0/{chapters}")
            
            dialog.destroy()
            self._log(f"新建小说《{title}》({sub_genre}) 创建成功，标签: {', '.join(selected_tags)}")
        
        tk.Button(action_row, text="创建小说", command=confirm, font=('微软雅黑', 10, 'bold'),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=20, pady=3).pack(side=tk.RIGHT)
    
    def _open_novel(self):
        """打开小说"""
        novel_dir = filedialog.askdirectory(
            title="选择小说目录",
            initialdir=str(self.config.novels_dir)
        )
        if not novel_dir:
            return
        
        novel_dir = Path(novel_dir)
        meta_file = novel_dir / "meta.json"
        
        if not meta_file.exists():
            messagebox.showerror("错误", "该目录不是有效的小说目录")
            return
        
        with open(meta_file, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        
        self.current_novel_dir = novel_dir
        self.memory = MemoryManager(novel_dir)
        self.agent = NovelAgent(self.ai_client, self.memory, log_callback=self._log, config=self.config)
        self.note_manager = NoteManager(novel_dir=novel_dir, config=self.config)
        self._init_character_system()
        self.title_var.set(meta.get("title", "未知"))
        self.genre_var.set(meta.get("genre", "未知"))
        
        # 加载大纲
        outline_file = novel_dir / "outline.json"
        if outline_file.exists():
            with open(outline_file, 'r', encoding='utf-8') as f:
                self.outline = json.load(f)
            self._refresh_outline_list()
        
        # 计算进度
        chapters_dir = novel_dir / "chapters"
        if chapters_dir.exists():
            chapter_files = list(chapters_dir.glob("chapter_*.txt"))
            self.current_chapter = len(chapter_files)
            self.chapter_var.set(f"{self.current_chapter}/{meta.get('chapter_count', '?')}")
        
        self._log(f"已打开小说《{meta.get('title', '未知')}》")
    
    def _show_settings(self):
        """显示设置对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("系统配置")
        dialog.geometry("550x650")
        dialog.transient(self.root)
        dialog.grab_set()
        
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # ===== Tab 1: AI模型配置 =====
        ai_frame = ttk.Frame(notebook)
        notebook.add(ai_frame, text="AI模型")
        
        ttk.Label(ai_frame, text="AI服务商:").pack(anchor=tk.W, padx=20, pady=(15,3))
        provider_var = tk.StringVar(value=self.config.get("api_provider", "ollama"))
        provider_combo = ttk.Combobox(ai_frame, textvariable=provider_var, 
            values=["ollama", "openai", "deepseek", "claude", "custom"], state="readonly", width=50)
        provider_combo.pack(padx=20, pady=3)
        
        ttk.Label(ai_frame, text="API地址 (Ollama默认 http://localhost:11434):").pack(anchor=tk.W, padx=20, pady=(10,3))
        base_entry = ttk.Entry(ai_frame, width=52)
        base_entry.insert(0, self.config.get("api_base", "http://localhost:11434"))
        base_entry.pack(padx=20, pady=3)
        
        ttk.Label(ai_frame, text="API密钥 (Ollama不需要):").pack(anchor=tk.W, padx=20, pady=(10,3))
        key_entry = ttk.Entry(ai_frame, width=52, show="*")
        key_entry.insert(0, self.config.get("api_key", ""))
        key_entry.pack(padx=20, pady=3)
        
        ttk.Label(ai_frame, text="模型名称:").pack(anchor=tk.W, padx=20, pady=(10,3))
        model_frame = ttk.Frame(ai_frame)
        model_frame.pack(fill=tk.X, padx=20, pady=3)
        model_entry = ttk.Entry(model_frame, width=40)
        model_entry.insert(0, self.config.get("model", "qwen2.5:14b"))
        model_entry.pack(side=tk.LEFT)
        
        def refresh_ollama():
            models = self.ai_client.get_ollama_models()
            if models:
                model_entry.delete(0, tk.END)
                model_entry.insert(0, models[0])
                messagebox.showinfo("Ollama模型", f"发现 {len(models)} 个模型:\n" + "\n".join(models[:10]))
            else:
                messagebox.showwarning("提示", "未检测到Ollama模型，请确保Ollama已启动")
        ttk.Button(model_frame, text="检测Ollama", command=refresh_ollama).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(ai_frame, text="温度 (0-1):").pack(anchor=tk.W, padx=20, pady=(10,3))
        temp_var = tk.StringVar(value=str(self.config.get("temperature", 0.8)))
        ttk.Spinbox(ai_frame, from_=0, to=1, increment=0.1, textvariable=temp_var, width=10).pack(anchor=tk.W, padx=20, pady=3)
        
        ttk.Label(ai_frame, text="上下文窗口 (字符数，影响长记忆):").pack(anchor=tk.W, padx=20, pady=(10,3))
        ctx_var = tk.StringVar(value=str(self.config.get("context_window", 32000)))
        ctx_combo = ttk.Combobox(ai_frame, textvariable=ctx_var, 
            values=["8000", "16000", "32000", "64000", "128000"], width=10)
        ctx_combo.pack(anchor=tk.W, padx=20, pady=3)
        ttk.Label(ai_frame, text="Ollama模型取决于显存，建议8K-32K；云端API可用更大窗口", 
                  foreground="gray").pack(anchor=tk.W, padx=20)
        
        # ===== Tab 2: 文生图配置 =====
        img_frame = ttk.Frame(notebook)
        notebook.add(img_frame, text="文生图")
        
        ttk.Label(img_frame, text="文生图后端:").pack(anchor=tk.W, padx=20, pady=(15,3))
        img_provider_var = tk.StringVar(value=self.config.get("img_provider", "comfyui"))
        ttk.Combobox(img_frame, textvariable=img_provider_var, 
            values=["comfyui", "sdapi", "disabled"], state="readonly", width=50).pack(padx=20, pady=3)
        
        ttk.Label(img_frame, text="API地址:").pack(anchor=tk.W, padx=20, pady=(10,3))
        img_base_entry = ttk.Entry(img_frame, width=52)
        img_base_entry.insert(0, self.config.get("img_api_base", "http://127.0.0.1:8188"))
        img_base_entry.pack(padx=20, pady=3)
        
        ttk.Label(img_frame, text="ComfyUI默认端口: 8188, SD WebUI默认端口: 7860").pack(anchor=tk.W, padx=20, pady=(3,10))
        
        ttk.Label(img_frame, text="模型文件名:").pack(anchor=tk.W, padx=20, pady=(5,3))
        img_model_entry = ttk.Entry(img_frame, width=52)
        img_model_entry.insert(0, self.config.get("img_model", "sd_xl_base_1.0.safetensors"))
        img_model_entry.pack(padx=20, pady=3)
        
        auto_detect_var = tk.BooleanVar(value=self.config.get("auto_detect_scene", True))
        ttk.Checkbutton(img_frame, text="生成章节后自动检测名场面并提醒生成插图", variable=auto_detect_var).pack(anchor=tk.W, padx=20, pady=15)
        
        ttk.Label(img_frame, text="支持的后端:\n- ComfyUI: 本地部署的ComfyUI，需启动API模式\n- SD API: Stable Diffusion WebUI的API模式\n- Disabled: 不使用文生图", 
                  justify=tk.LEFT).pack(anchor=tk.W, padx=20, pady=10)
        
        # ===== Tab 3: 云端存储配置 =====
        cloud_frame = ttk.Frame(notebook)
        notebook.add(cloud_frame, text="云端存储")
        
        ttk.Label(cloud_frame, text="云端存储配置", font=("", 11, "bold")).pack(anchor=tk.W, padx=20, pady=(15,10))
        ttk.Label(cloud_frame, text="支持: WebDAV（坚果云）、百度网盘、夸克网盘、迅雷网盘、阿里云盘").pack(anchor=tk.W, padx=20, pady=(0,10))
        
        # 云存储提供商选择
        cloud_provider_var = tk.StringVar(value="webdav")
        providers = self.cloud_storage.get_available_providers()
        provider_names = [p["name"] for p in providers]
        provider_ids = [p["id"] for p in providers]
        
        ttk.Label(cloud_frame, text="选择云存储:").pack(anchor=tk.W, padx=20, pady=(5,3))
        cloud_combo = ttk.Combobox(cloud_frame, textvariable=cloud_provider_var, 
                                   values=provider_names, state="readonly", width=50)
        cloud_combo.pack(padx=20, pady=3)
        cloud_combo.set(provider_names[0] if provider_names else "")
        
        # 配置区域
        config_frame = ttk.LabelFrame(cloud_frame, text="配置信息", padding=10)
        config_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # WebDAV配置
        webdav_frame = ttk.Frame(config_frame)
        ttk.Label(webdav_frame, text="WebDAV地址:").grid(row=0, column=0, sticky=tk.W, pady=2)
        webdav_url_entry = ttk.Entry(webdav_frame, width=40)
        webdav_url_entry.insert(0, self.cloud_storage.config.get("webdav", {}).get("url", "https://dav.jianguoyun.com/dav/"))
        webdav_url_entry.grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(webdav_frame, text="用户名:").grid(row=1, column=0, sticky=tk.W, pady=2)
        webdav_user_entry = ttk.Entry(webdav_frame, width=40)
        webdav_user_entry.insert(0, self.cloud_storage.config.get("webdav", {}).get("username", ""))
        webdav_user_entry.grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Label(webdav_frame, text="密码/应用密钥:").grid(row=2, column=0, sticky=tk.W, pady=2)
        webdav_pass_entry = ttk.Entry(webdav_frame, width=40, show="*")
        webdav_pass_entry.insert(0, self.cloud_storage.config.get("webdav", {}).get("password", ""))
        webdav_pass_entry.grid(row=2, column=1, padx=5, pady=2)
        webdav_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 百度网盘配置
        baidu_frame = ttk.Frame(config_frame)
        ttk.Label(baidu_frame, text="Access Token:").grid(row=0, column=0, sticky=tk.W, pady=2)
        baidu_token_entry = ttk.Entry(baidu_frame, width=40)
        baidu_token_entry.insert(0, self.cloud_storage.config.get("baidu", {}).get("access_token", ""))
        baidu_token_entry.grid(row=0, column=1, padx=5, pady=2)
        baidu_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 夸克网盘配置
        quark_frame = ttk.Frame(config_frame)
        ttk.Label(quark_frame, text="Cookie:").grid(row=0, column=0, sticky=tk.W, pady=2)
        quark_cookie_entry = ttk.Entry(quark_frame, width=40)
        quark_cookie_entry.insert(0, self.cloud_storage.config.get("quark", {}).get("cookie", ""))
        quark_cookie_entry.grid(row=0, column=1, padx=5, pady=2)
        quark_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 迅雷网盘配置
        xunlei_frame = ttk.Frame(config_frame)
        ttk.Label(xunlei_frame, text="Access Token:").grid(row=0, column=0, sticky=tk.W, pady=2)
        xunlei_token_entry = ttk.Entry(xunlei_frame, width=40)
        xunlei_token_entry.insert(0, self.cloud_storage.config.get("xunlei", {}).get("access_token", ""))
        xunlei_token_entry.grid(row=0, column=1, padx=5, pady=2)
        xunlei_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 阿里云盘配置
        aliyun_frame = ttk.Frame(config_frame)
        ttk.Label(aliyun_frame, text="Access Token:").grid(row=0, column=0, sticky=tk.W, pady=2)
        aliyun_token_entry = ttk.Entry(aliyun_frame, width=40)
        aliyun_token_entry.insert(0, self.cloud_storage.config.get("aliyun", {}).get("access_token", ""))
        aliyun_token_entry.grid(row=0, column=1, padx=5, pady=2)
        aliyun_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 测试连接按钮
        def test_cloud_connection():
            provider_name = cloud_combo.get()
            provider_id = provider_ids[provider_names.index(provider_name)] if provider_name in provider_names else "webdav"
            
            # 保存配置
            if provider_id == "webdav":
                self.cloud_storage.configure_provider("webdav", {
                    "url": webdav_url_entry.get(),
                    "username": webdav_user_entry.get(),
                    "password": webdav_pass_entry.get()
                })
            elif provider_id == "baidu":
                self.cloud_storage.configure_provider("baidu", {
                    "access_token": baidu_token_entry.get()
                })
            elif provider_id == "quark":
                self.cloud_storage.configure_provider("quark", {
                    "cookie": quark_cookie_entry.get()
                })
            elif provider_id == "xunlei":
                self.cloud_storage.configure_provider("xunlei", {
                    "access_token": xunlei_token_entry.get()
                })
            elif provider_id == "aliyun":
                self.cloud_storage.configure_provider("aliyun", {
                    "access_token": aliyun_token_entry.get()
                })
            
            # 测试连接
            if self.cloud_storage.connect_provider(provider_id):
                messagebox.showinfo("成功", f"{provider_name} 连接成功！")
            else:
                messagebox.showwarning("失败", f"{provider_name} 连接失败，请检查配置")
        
        ttk.Button(cloud_frame, text="测试连接", command=test_cloud_connection).pack(pady=10)
        
        # ===== 保存 =====
        def save():
            self.config.set("api_provider", provider_var.get())
            self.config.set("api_key", key_entry.get().strip())
            self.config.set("api_base", base_entry.get().strip())
            self.config.set("model", model_entry.get().strip())
            self.config.set("temperature", float(temp_var.get()))
            self.config.set("context_window", int(ctx_var.get()))
            self.config.set("img_provider", img_provider_var.get())
            self.config.set("img_api_base", img_base_entry.get().strip())
            self.config.set("img_model", img_model_entry.get().strip())
            self.config.set("auto_detect_scene", auto_detect_var.get())
            
            self.ai_client = AIClient(self.config)
            self.image_gen = ImageGenerator(self.config)
            if self.memory:
                self.agent = NovelAgent(self.ai_client, self.memory, log_callback=self._log, config=self.config)
            
            self._update_status()
            dialog.destroy()
            self._log("配置已保存")
        
        ttk.Button(dialog, text="保存配置", command=save).pack(pady=10)
    
    def _gen_settings(self):
        """生成世界观"""
        if not self._check_ready():
            return
        
        def run():
            try:
                meta = self._get_meta()
                self.agent.generate_settings(meta["genre"], meta["title"], meta.get("concept", ""))
                self._log("世界观设定已保存到 memory/settings.json")
            except Exception as e:
                self._log(f"生成失败: {e}")
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _gen_characters(self):
        """生成角色"""
        if not self._check_ready():
            return
        
        def run():
            try:
                meta = self._get_meta()
                self.agent.generate_characters(meta["genre"], meta["title"])
                self._log("角色档案已保存到 memory/characters.json")
            except Exception as e:
                self._log(f"生成失败: {e}")
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _gen_outline(self):
        """生成大纲"""
        if not self._check_ready():
            return
        
        def run():
            try:
                meta = self._get_meta()
                self.outline = self.agent.generate_outline(
                    meta["genre"], meta["title"], meta["chapter_count"]
                )
                
                # 保存大纲
                with open(self.current_novel_dir / "outline.json", 'w', encoding='utf-8') as f:
                    json.dump(self.outline, f, indent=2, ensure_ascii=False)
                
                # GUI操作在主线程
                self.root.after(0, self._refresh_outline_list)
                self._log("大纲已保存到 outline.json")
            except Exception as e:
                self._log(f"生成失败: {e}")
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _gen_chapter(self):
        """生成下一章"""
        if not self._check_ready():
            return
        if not self.outline:
            messagebox.showwarning("提示", "请先生成大纲")
            return
        
        self.current_chapter += 1
        if self.current_chapter > len(self.outline):
            messagebox.showinfo("提示", "所有章节已生成完毕")
            self.current_chapter = len(self.outline)
            return
        
        chapter_info = self.outline[self.current_chapter - 1]
        
        def run():
            try:
                ch_num = self.current_chapter  # 捕获当前值，避免竞态
                content = self.agent.generate_chapter(
                    ch_num,
                    chapter_info.get("title", f"第{ch_num}章"),
                    chapter_info.get("summary", ""),
                    word_count=3000
                )
                
                # 保存章节
                chapters_dir = self.current_novel_dir / "chapters"
                chapters_dir.mkdir(exist_ok=True)
                with open(chapters_dir / f"chapter_{ch_num:04d}.txt", 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # GUI操作必须在主线程
                self.root.after(0, lambda: self._display_chapter(
                    ch_num, chapter_info.get("title", ""), content))
                
                # 自动定稿
                self.agent.finalize_chapter(ch_num, content)
                
                # 名场面检测
                if self.config.get("auto_detect_scene", True):
                    self._detect_and_prompt_image(content, ch_num)
                
                self._log(f"第{ch_num}章已保存并定稿")
            except Exception as e:
                self._log(f"生成失败: {e}")
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _review_chapter(self):
        """审校当前章节"""
        if not self._check_ready():
            return
        
        content = self.content_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("提示", "没有可审校的内容")
            return
        
        def run():
            try:
                review = self.agent.review_chapter(self.current_chapter, content)
                review_json = json.dumps(review, indent=2, ensure_ascii=False)
                self.root.after(0, lambda: self._display_review(review_json))
                self._log(f"审校完成，评分：{review.get('overall_score', 'N/A')}")
            except Exception as e:
                self._log(f"审校失败: {e}")
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _auto_generate(self):
        """自动创作全流程"""
        if not self._check_ready():
            return
        
        meta = self._get_meta()
        
        def run():
            try:
                # 1. 生成世界观
                self._log("=== 开始自动创作 ===")
                self.agent.generate_settings(meta["genre"], meta["title"], meta.get("concept", ""))
                
                # 2. 生成角色
                self.agent.generate_characters(meta["genre"], meta["title"])
                
                # 3. 生成大纲
                self.outline = self.agent.generate_outline(meta["genre"], meta["title"], meta["chapter_count"])
                with open(self.current_novel_dir / "outline.json", 'w', encoding='utf-8') as f:
                    json.dump(self.outline, f, indent=2, ensure_ascii=False)
                self.root.after(0, self._refresh_outline_list)
                
                # 4. 逐章生成
                for i, chapter_info in enumerate(self.outline):
                    self.current_chapter = i + 1
                    content = self.agent.generate_chapter(
                        self.current_chapter,
                        chapter_info.get("title", f"第{self.current_chapter}章"),
                        chapter_info.get("summary", ""),
                        word_count=3000
                    )
                    
                    # 保存
                    chapters_dir = self.current_novel_dir / "chapters"
                    chapters_dir.mkdir(exist_ok=True)
                    with open(chapters_dir / f"chapter_{self.current_chapter:04d}.txt", 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    # 定稿
                    self.agent.finalize_chapter(self.current_chapter, content)
                    
                    # 更新UI
                    self.root.after(0, lambda c=content, n=self.current_chapter, t=chapter_info.get("title", ""): self._display_chapter(n, t, c))
                
                self._log("=== 自动创作完成 ===")
                self.root.after(0, lambda: messagebox.showinfo("完成", f"《{meta['title']}》创作完成！"))
            except Exception as e:
                self._log(f"自动创作失败: {e}")
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _display_chapter(self, num, title, content):
        """显示章节内容（线程安全）"""
        self.content_text.delete("1.0", tk.END)
        self.content_text.insert("1.0", content)
        self.chapter_title_var.set(f"第{num}章: {title}")
        self.word_count_var.set(f"字数: {len(content)}")
        meta = self._get_meta()
        self.chapter_var.set(f"{self.current_chapter}/{meta.get('chapter_count', '?')}")
    
    def _save_chapter(self):
        """保存当前章节"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先创建或打开小说")
            return
        
        content = self.content_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("提示", "没有可保存的内容")
            return
        
        chapters_dir = self.current_novel_dir / "chapters"
        chapters_dir.mkdir(exist_ok=True)
        with open(chapters_dir / f"chapter_{self.current_chapter:04d}.txt", 'w', encoding='utf-8') as f:
            f.write(content)
        
        self._log(f"第{self.current_chapter}章已保存")
        messagebox.showinfo("成功", "章节已保存")
    
    def _export_txt(self):
        """导出全文TXT"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先创建或打开小说")
            return
        
        meta = self._get_meta()
        save_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt")],
            initialfile=f"{meta.get('title', '小说')}.txt"
        )
        
        if not save_path:
            return
        
        chapters_dir = self.current_novel_dir / "chapters"
        chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))
        
        with open(save_path, 'w', encoding='utf-8') as out:
            out.write(f"《{meta.get('title', '小说')}》\n\n")
            for cf in chapter_files:
                content = cf.read_text(encoding='utf-8')
                out.write(content + "\n\n")
        
        self._log(f"全文已导出到: {save_path}")
        messagebox.showinfo("成功", f"全文已导出到:\n{save_path}")
    
    def _refresh_outline_list(self):
        """刷新大纲列表"""
        self.outline_list.delete(0, tk.END)
        for item in self.outline:
            ch = item.get("chapter", "?")
            title = item.get("title", "未命名")
            self.outline_list.insert(tk.END, f"第{ch}章: {title}")
    
    # ===== 云端同步 =====
    
    def _cloud_sync(self):
        """云端同步对话框"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先新建或打开小说")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("云端同步")
        dialog.geometry("400x300")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        tk.Label(dialog, text="云端同步", font=('微软雅黑', 12, 'bold'),
                bg=C['bg_dark'], fg=C['text_primary']).pack(pady=(15, 10))
        
        # 获取可用的云存储
        providers = self.cloud_storage.get_available_providers()
        configured = [p for p in providers if p.get("configured")]
        
        if not configured:
            tk.Label(dialog, text="未配置云存储\n\n请在 设置 → 云端存储 中配置",
                    font=('微软雅黑', 10), bg=C['bg_dark'], fg=C['text_muted']).pack(pady=20)
        else:
            provider_var = tk.StringVar(value=configured[0]["name"])
            for p in configured:
                tk.Radiobutton(dialog, text=p["name"], variable=provider_var, value=p["name"],
                              font=('微软雅黑', 10), bg=C['bg_dark'], fg=C['text_primary'],
                              selectcolor=C['accent']).pack(anchor=tk.W, padx=30, pady=3)
            
            def do_upload():
                provider_name = provider_var.get()
                provider_id = next((p["id"] for p in configured if p["name"] == provider_name), None)
                if provider_id:
                    def run():
                        try:
                            self._log(f"开始上传到 {provider_name}...")
                            success = self.cloud_storage.upload_novel(self.current_novel_dir, provider_id)
                            if success:
                                self._log(f"上传成功！")
                                self.root.after(0, lambda: messagebox.showinfo("成功", f"小说已上传到 {provider_name}"))
                            else:
                                self._log(f"上传失败")
                                self.root.after(0, lambda: messagebox.showerror("失败", f"上传失败，请检查网络和配置"))
                        except Exception as e:
                            self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
                    threading.Thread(target=run, daemon=True).start()
            
            def do_download():
                provider_name = provider_var.get()
                provider_id = next((p["id"] for p in configured if p["name"] == provider_name), None)
                if provider_id:
                    def run():
                        try:
                            self._log(f"开始从 {provider_name} 下载...")
                            success = self.cloud_storage.download_novel("/AI_NovelWriter", self.current_novel_dir, provider_id)
                            if success:
                                self._log(f"下载成功！")
                                self.root.after(0, lambda: messagebox.showinfo("成功", f"小说已从 {provider_name} 下载"))
                            else:
                                self._log(f"下载失败")
                                self.root.after(0, lambda: messagebox.showerror("失败", f"下载失败"))
                        except Exception as e:
                            self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
                    threading.Thread(target=run, daemon=True).start()
            
            btn_frame = tk.Frame(dialog, bg=C['bg_dark'])
            btn_frame.pack(fill=tk.X, padx=30, pady=15)
            
            tk.Button(btn_frame, text="上传到云端", font=('微软雅黑', 10),
                     bg=C['accent'], fg='white', relief=tk.FLAT, padx=15,
                     command=do_upload).pack(side=tk.LEFT, padx=5)
            tk.Button(btn_frame, text="从云端下载", font=('微软雅黑', 10),
                     bg=C['success'], fg='white', relief=tk.FLAT, padx=15,
                     command=do_download).pack(side=tk.LEFT, padx=5)
        
        tk.Button(dialog, text="关闭", font=('微软雅黑', 10),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=15,
                 command=dialog.destroy).pack(pady=10)
    
    # ===== 格式转换 =====
    
    def _show_format_converter(self):
        """显示格式转换对话框"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先新建或打开小说")
            return
        
        if not self.format_converter:
            self.format_converter = FormatConverter(self.current_novel_dir)
        
        dialog = tk.Toplevel(self.root)
        dialog.title("格式转换")
        dialog.geometry("450x400")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        tk.Label(dialog, text="选择导出格式:", font=('微软雅黑', 12, 'bold'),
                bg=C['bg_dark'], fg=C['text_primary']).pack(pady=(15, 10))
        
        # 格式列表
        formats = self.format_converter.get_formats()
        format_var = tk.StringVar(value="html")
        
        for fmt_key, fmt_info in formats.items():
            frame = tk.Frame(dialog, bg=C['bg_dark'])
            frame.pack(fill=tk.X, padx=20, pady=3)
            
            tk.Radiobutton(frame, text=f"{fmt_info['name']} ({fmt_info['ext']})", 
                          variable=format_var, value=fmt_key,
                          font=('微软雅黑', 10), bg=C['bg_dark'], fg=C['text_primary'],
                          selectcolor=C['accent']).pack(side=tk.LEFT)
            tk.Label(frame, text=fmt_info['desc'], font=('微软雅黑', 8),
                    bg=C['bg_dark'], fg=C['text_muted']).pack(side=tk.RIGHT)
        
        # 包含图片选项
        include_images_var = tk.BooleanVar(value=True)
        tk.Checkbutton(dialog, text="包含插图（如有）", variable=include_images_var,
                      font=('微软雅黑', 10), bg=C['bg_dark'], fg=C['text_primary'],
                      selectcolor=C['accent']).pack(pady=10)
        
        def do_convert():
            fmt = format_var.get()
            
            # 收集所有章节
            chapters_dir = self.current_novel_dir / "chapters"
            chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))
            chapters = []
            
            for cf in chapter_files:
                num = int(cf.stem.split("_")[1])
                content = cf.read_text(encoding='utf-8')
                # 从大纲获取标题
                title = f"第{num}章"
                if self.outline and num <= len(self.outline):
                    title = self.outline[num-1].get("title", title)
                chapters.append({"num": num, "title": title, "content": content})
            
            if not chapters:
                # 如果没有章节文件，使用编辑区内容
                content = self.content_text.get("1.0", tk.END).strip()
                if not content:
                    messagebox.showwarning("提示", "没有可导出的内容")
                    return
            else:
                content = "\n\n".join(ch["content"] for ch in chapters)
            
            meta = self._get_meta() if self.current_novel_dir else {}
            
            # 获取图片数据
            images = None
            if include_images_var.get() and self.image_manager:
                images = self.image_manager.get_images_data()
            
            # 转换
            result = self.format_converter.convert(
                content=content,
                title=meta.get("title", "小说"),
                format_type=fmt,
                chapters=chapters if chapters else None,
                metadata=meta,
                images=images,
            )
            
            if result:
                self._log(f"格式转换完成: {result}")
                dialog.destroy()
                
                # 询问是否打开
                if messagebox.askyesno("成功", f"已导出为{formats[fmt]['name']}格式\n\n{result}\n\n是否打开文件？"):
                    import subprocess
                    subprocess.Popen(['start', result], shell=True)
            else:
                messagebox.showerror("错误", "格式转换失败")
        
        tk.Button(dialog, text="开始转换", font=('微软雅黑', 11, 'bold'),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=20, pady=8,
                 command=do_convert).pack(pady=15)
    
    # ===== 图片插入 =====
    
    def _insert_image(self):
        """插入图片到编辑区"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先新建或打开小说")
            return
        
        if not self.image_manager:
            self.image_manager = ImageManager(self.current_novel_dir)
        
        # 选择图片文件
        file_path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("所有文件", "*.*"),
            ]
        )
        
        if not file_path:
            return
        
        # 导入图片
        img_path = self.image_manager.import_image(file_path)
        if not img_path:
            messagebox.showerror("错误", "导入图片失败")
            return
        
        # 在编辑区插入图片标记
        cursor_pos = self.content_text.index(tk.INSERT)
        img_name = Path(img_path).name
        
        # 插入Markdown格式的图片标记
        marker = f"\n![插图]({img_name})\n"
        self.content_text.insert(tk.INSERT, marker)
        
        # 尝试在Text widget中显示图片预览
        try:
            from PIL import Image, ImageTk
            img = Image.open(img_path)
            # 缩放图片
            max_width = 400
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            
            # 转换为Tkinter可用的格式
            photo = ImageTk.PhotoImage(img)
            
            # 先获取当前内容（不含标记）
            current = self.content_text.get("1.0", tk.END)
            current = current.replace(f"\n![插图]({img_name})\n", "")
            
            # 清空并重新插入内容
            self.content_text.delete("1.0", tk.END)
            self.content_text.insert("1.0", current)
            
            # 在Text widget中插入图片预览
            self.content_text.image_create(tk.INSERT, image=photo)
            self.content_text.insert(tk.INSERT, "\n")
            
            # 保持引用防止被垃圾回收
            if not hasattr(self, '_photo_refs'):
                self._photo_refs = []
            self._photo_refs.append(photo)
            
        except ImportError:
            # 如果没有PIL，只保留文本标记（已插入）
            pass
        except Exception as e:
            self._log(f"图片预览加载失败: {e}")
        
        self._log(f"已插入图片: {img_name}")
        
        # 更新字数
        content = self.content_text.get("1.0", tk.END).strip()
        self.word_count_var.set(str(len(content)))
    
    def _on_outline_select(self, event):
        """大纲选中事件"""
        if not self.current_novel_dir or not self.outline:
            return
        
        selection = self.outline_list.curselection()
        if not selection:
            return
        
        idx = selection[0]
        if idx < len(self.outline):
            chapter_info = self.outline[idx]
            self.current_chapter = chapter_info.get("chapter", idx + 1)
            
            # 尝试加载已生成的章节
            chapters_dir = self.current_novel_dir / "chapters"
            chapter_file = chapters_dir / f"chapter_{self.current_chapter:04d}.txt"
            
            if chapter_file.exists():
                content = chapter_file.read_text(encoding='utf-8')
                self.content_text.delete("1.0", tk.END)
                self.content_text.insert("1.0", content)
                self.chapter_title_var.set(f"第{self.current_chapter}章: {chapter_info.get('title', '')}")
                self.word_count_var.set(f"字数: {len(content)}")
            else:
                self.chapter_title_var.set(f"第{self.current_chapter}章: {chapter_info.get('title', '')} (未生成)")
                self.content_text.delete("1.0", tk.END)
                self.content_text.insert("1.0", f"章节大纲：\n{chapter_info.get('summary', '无')}")
    
    def _detect_and_prompt_image(self, content: str, chapter_num: int):
        """检测名场面并提醒生成图片"""
        if not self.image_gen.is_configured():
            return
        
        scenes = SceneDetector.detect(content)
        if not scenes:
            return
        
        self._log(f"[名场面检测] 发现 {len(scenes)} 个适合生成插图的场景")
        scene_type_cn = {"battle": "战斗场面", "beauty": "人物特写", "emotion": "情感场景", "epic": "震撼场面"}
        
        # 在主线程中弹出提醒
        def prompt():
            for i, scene in enumerate(scenes):
                type_name = scene_type_cn.get(scene["type"], "名场面")
                
                result = messagebox.askyesno(
                    "名场面检测",
                    f"第{chapter_num}章发现【{type_name}】：\n\n{scene['text'][:100]}...\n\n是否生成插图？"
                )
                
                if result:
                    # 图片生成放到后台线程
                    def gen_img(s=scene, idx=i):
                        self._log(f"[文生图] 正在生成插图: {type_name}...")
                        img_data = self.image_gen.generate(
                            prompt=s["prompt"],
                            negative_prompt="low quality, blurry, deformed, ugly",
                            width=self.config.get("img_width", 1024),
                            height=self.config.get("img_height", 1024),
                        )
                        if img_data:
                            filepath = self.image_gen.save_image(
                                img_data, self.current_novel_dir,
                                f"chapter_{chapter_num:04d}_scene_{idx+1}"
                            )
                            self._log(f"[文生图] 插图已保存: {filepath}")
                            self.root.after(0, lambda: messagebox.showinfo("成功", f"插图已保存到:\n{filepath}"))
                        else:
                            self._log("[文生图] 插图生成失败，请检查文生图服务是否启动")
                            self.root.after(0, lambda: messagebox.showwarning("失败", "插图生成失败\n请检查ComfyUI或SD WebUI是否已启动"))
                    threading.Thread(target=gen_img, daemon=True).start()
        
        self.root.after(0, prompt)
    
    def _open_fullscreen_writer(self):
        """打开全屏写作模式 - 与自动写作共享上下文"""
        # 获取当前章节内容
        current_text = self.content_text.get("1.0", tk.END).strip()
        
        # 构建共享上下文（世界观、角色、大纲等）
        shared_context = ""
        if self.memory:
            settings = self.memory.get_settings()
            if settings:
                shared_context += f"世界观: {json.dumps(settings, ensure_ascii=False)[:500]}\n"
            characters = self.memory.get_characters()
            if characters:
                shared_context += f"角色: {json.dumps(characters, ensure_ascii=False)[:500]}\n"
            global_summary = self.memory.get_global_summary()
            if global_summary:
                shared_context += f"故事进展: {global_summary[:300]}\n"
        
        # 如果有大纲，添加当前章节大纲
        if self.outline and self.current_chapter > 0 and self.current_chapter <= len(self.outline):
            ch_info = self.outline[self.current_chapter - 1]
            shared_context += f"当前章节大纲: {ch_info.get('summary', '')}\n"
        
        def save_callback(content):
            # 保存到当前章节
            self.content_text.delete("1.0", tk.END)
            self.content_text.insert("1.0", content)
            self.word_count_var.set(str(len(content)))
            self._save_chapter()
            
            # 自动更新记忆
            if self.memory and self.agent:
                threading.Thread(target=lambda: self.agent.finalize_chapter(
                    self.current_chapter, content), daemon=True).start()
                self._log(f"[联动] 全屏写作内容已保存并更新记忆")
        
        FullscreenWriter(
            parent=self.root,
            ai_client=self.ai_client,
            config=self.config,
            initial_text=current_text,
            save_callback=save_callback,
            shared_context=shared_context  # 传递共享上下文
        )
    
    # ===== 笔记功能 =====
    
    # ===== 角色系统 =====
    
    def _init_character_system(self):
        """初始化角色系统"""
        if self.current_novel_dir:
            self.character_system = CharacterSystem(self.current_novel_dir)
            self.character_system.load()
            self._update_char_display()
            self.format_converter = FormatConverter(self.current_novel_dir)
            self.image_manager = ImageManager(self.current_novel_dir)
    
    def _update_char_display(self):
        """更新角色面板显示"""
        if not self.character_system:
            self.char_summary.config(text="未创建角色")
            self.char_select_combo['values'] = []
            return
        
        names = self.character_system.get_character_names()
        self.char_select_combo['values'] = names
        
        if self.character_system.character:
            char = self.character_system.character
            self.char_select_var.set(char.name)
            summary = f"【{char.title}】Lv.{char.level}\n"
            summary += f"HP:{char.hp}/{char.max_hp} MP:{char.mp}/{char.max_mp}\n"
            summary += f"EXP:{char.exp}/{char.exp_to_next}\n"
            w = char.weapon.get('name', '无') if char.weapon else '无'
            summary += f"武器:{w} | 技能:{len(char.skills)}个"
            self.char_summary.config(text=summary)
        else:
            self.char_select_var.set("无角色")
            self.char_summary.config(text="未创建角色")
    
    def _on_char_select(self, event=None):
        """切换活跃角色"""
        name = self.char_select_var.get()
        if self.character_system and name:
            self.character_system.set_active(name)
            self._update_char_display()
            self._log(f"切换到角色: {name}")
    
    def _create_character_dialog(self):
        """创建角色对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("创建角色")
        dialog.geometry("400x350")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        fields = {}
        for label, key, default in [("角色名称:", "name", "主角"), ("性格特点:", "personality", ""), 
                                    ("外貌描述:", "appearance", ""), ("背景故事:", "backstory", "")]:
            tk.Label(dialog, text=label, font=('微软雅黑', 10),
                    bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=20, pady=(10, 2))
            entry = tk.Entry(dialog, width=40, font=('微软雅黑', 10))
            entry.insert(0, default)
            entry.pack(padx=20)
            fields[key] = entry
        
        def create():
            name = fields["name"].get().strip()
            if not name:
                messagebox.showwarning("提示", "请输入角色名称")
                return
            if not self.character_system:
                self.character_system = CharacterSystem(self.current_novel_dir)
            
            if name in self.character_system.get_character_names():
                messagebox.showwarning("提示", "角色名已存在")
                return
            
            self.character_system.create_character(
                name=name,
                backstory=fields["backstory"].get().strip(),
                personality=fields["personality"].get().strip(),
                appearance=fields["appearance"].get().strip(),
            )
            self._update_char_display()
            self._log(f"角色「{name}」创建成功")
            dialog.destroy()
        
        tk.Button(dialog, text="创建", font=('微软雅黑', 11),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=20, pady=5,
                 command=create).pack(pady=15)
    
    def _ai_create_character(self):
        """AI自动创建角色"""
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        # 获取小说上下文
        context = ""
        if self.memory:
            settings = self.memory.get_settings()
            if settings:
                context = json.dumps(settings, ensure_ascii=False)[:300]
        
        def run():
            try:
                if not self.character_system:
                    self.character_system = CharacterSystem(self.current_novel_dir)
                
                result = self.character_system.ai_create_character(self.ai_client, context)
                
                if result["success"]:
                    char = result["character"]
                    self.root.after(0, lambda: self._update_char_display())
                    self._log(f"AI创建角色「{char.name}」成功")
                    
                    # 如果有武器/技能建议，显示给用户
                    suggestions = f"角色「{char.name}」创建成功！\n\n"
                    if result.get("weapon_suggestion"):
                        suggestions += f"建议武器: {result['weapon_suggestion']}\n"
                    if result.get("skill_suggestions"):
                        suggestions += f"建议技能: {', '.join(result['skill_suggestions'])}\n"
                    self.root.after(0, lambda: messagebox.showinfo("AI创建成功", suggestions))
                else:
                    self.root.after(0, lambda: messagebox.showerror("创建失败", result.get("error", "未知错误")))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        self._log("AI正在创建角色...")
        threading.Thread(target=run, daemon=True).start()
    
    def _show_char_detail(self):
        """显示角色详情"""
        if not self.character_system or not self.character_system.character:
            messagebox.showinfo("提示", "请先创建角色")
            return
        
        char = self.character_system.character
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"角色详情 - {char.name}")
        dialog.geometry("500x600")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        # 使用Notebook组织信息
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 属性页
        attr_frame = tk.Frame(notebook, bg=C['bg_dark'])
        notebook.add(attr_frame, text=" 属性 ")
        
        attr_text = tk.Text(attr_frame, wrap=tk.WORD, font=('微软雅黑', 10),
                           bg=C['bg_card'], fg=C['text_primary'], relief=tk.FLAT, padx=15, pady=15)
        attr_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        attr_text.insert("1.0", char.get_summary())
        attr_text.config(state=tk.DISABLED)
        
        # 武器/技能页
        equip_frame = tk.Frame(notebook, bg=C['bg_dark'])
        notebook.add(equip_frame, text=" 装备/技能 ")
        
        equip_text = tk.Text(equip_frame, wrap=tk.WORD, font=('微软雅黑', 10),
                            bg=C['bg_card'], fg=C['text_primary'], relief=tk.FLAT, padx=15, pady=15)
        equip_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        equip_info = "═══ 装备 ═══\n"
        equip_info += f"武器: {char.weapon.get('name', '无') if char.weapon else '无'}\n"
        equip_info += f"防具: {char.armor.get('name', '无') if char.armor else '无'}\n"
        equip_info += f"饰品: {char.accessory.get('name', '无') if char.accessory else '无'}\n\n"
        equip_info += "═══ 技能 ═══\n"
        for skill in char.skills:
            equip_info += f"• {skill.get('name', '')} ({skill.get('type', '')}) - {skill.get('desc', '')}\n"
        if not char.skills:
            equip_info += "暂无技能\n"
        
        equip_text.insert("1.0", equip_info)
        equip_text.config(state=tk.DISABLED)
        
        # 统计页
        stats_frame = tk.Frame(notebook, bg=C['bg_dark'])
        notebook.add(stats_frame, text=" 统计 ")
        
        stats_text = tk.Text(stats_frame, wrap=tk.WORD, font=('微软雅黑', 10),
                            bg=C['bg_card'], fg=C['text_primary'], relief=tk.FLAT, padx=15, pady=15)
        stats_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        stats_text.insert("1.0", self.character_system.get_stats_display())
        stats_text.config(state=tk.DISABLED)
        
        # 操作按钮
        btn_frame = tk.Frame(dialog, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Button(btn_frame, text="重命名", font=('微软雅黑', 9),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=8,
                 command=lambda: self._rename_character(dialog)).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_frame, text="删除角色", font=('微软雅黑', 9),
                 bg=C['error'], fg='white', relief=tk.FLAT, padx=8,
                 command=lambda: self._delete_character(dialog)).pack(side=tk.LEFT, padx=3)
        tk.Button(btn_frame, text="休息恢复", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT, padx=8,
                 command=lambda: self._rest_character()).pack(side=tk.RIGHT, padx=3)
    
    def _rename_character(self, dialog):
        """重命名角色"""
        if not self.character_system or not self.character_system.character:
            return
        old_name = self.character_system.character.name
        new_name = tk.simpledialog.askstring("重命名", "输入新名称:", initialvalue=old_name)
        if new_name and new_name != old_name:
            if self.character_system.rename_character(old_name, new_name):
                self._update_char_display()
                self._log(f"角色已重命名: {old_name} → {new_name}")
                dialog.destroy()
            else:
                messagebox.showwarning("提示", "名称已存在或无效")
    
    def _delete_character(self, dialog):
        """删除角色"""
        if not self.character_system or not self.character_system.character:
            return
        name = self.character_system.character.name
        if messagebox.askyesno("确认", f"确定删除角色「{name}」？"):
            self.character_system.delete_character(name)
            self._update_char_display()
            self._log(f"已删除角色: {name}")
            dialog.destroy()
    
    def _rest_character(self):
        """角色休息恢复"""
        if self.character_system and self.character_system.character:
            self.character_system.character.rest()
            self.character_system.save_character()
            self._update_char_display()
            self._log(f"{self.character_system.character.name} 休息恢复，HP/MP已满")
    
    def _equip_weapon(self):
        """装备武器"""
        if not self.character_system or not self.character_system.character:
            messagebox.showinfo("提示", "请先创建角色")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("选择武器")
        dialog.geometry("500x450")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        tk.Label(dialog, text="选择武器:", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_dark'], fg=C['text_primary']).pack(pady=(10, 5))
        
        cat_var = tk.StringVar()
        cats = self.character_system.get_weapon_categories()
        cat_combo = ttk.Combobox(dialog, textvariable=cat_var, values=cats, state="readonly", width=20)
        cat_combo.pack(pady=5)
        cat_combo.set(cats[0] if cats else "")
        
        weapon_listbox = tk.Listbox(dialog, bg=C['bg_card'], fg=C['text_primary'],
                                   font=('微软雅黑', 9), selectbackground=C['accent'], height=10)
        weapon_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        def update_list(*args):
            weapon_listbox.delete(0, tk.END)
            weapons = self.character_system.get_weapons(cat_var.get())
            for w in weapons:
                q = w.get('quality', '')
                custom = " [自定义]" if w.get('custom') else ""
                attrs = ", ".join(f"{k}:{v}" for k, v in w.get('attributes', {}).items())
                weapon_listbox.insert(tk.END, f"[{q}]{custom} {w.get('name', '')} - {attrs}")
        
        cat_combo.bind('<<ComboboxSelected>>', update_list)
        update_list()
        
        def equip():
            sel = weapon_listbox.curselection()
            if sel:
                weapons = self.character_system.get_weapons(cat_var.get())
                if sel[0] < len(weapons):
                    weapon = weapons[sel[0]]
                    self.character_system.character.equip_weapon(weapon)
                    self.character_system.save_character()
                    self._update_char_display()
                    self._log(f"装备武器: {weapon.get('name', '')}")
                    dialog.destroy()
        
        def add_custom():
            """添加自定义武器"""
            sub = tk.Toplevel(dialog)
            sub.title("自定义武器")
            sub.geometry("350x300")
            sub.configure(bg=C['bg_dark'])
            
            fields = {}
            for label, default in [("名称:", ""), ("品质:", "凡品"), ("描述:", ""), ("力量加成:", "10"), 
                                   ("敏捷加成:", "0"), ("体质加成:", "0"), ("智力加成:", "0")]:
                tk.Label(sub, text=label, bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=20, pady=(5,0))
                e = tk.Entry(sub, width=30)
                e.insert(0, default)
                e.pack(padx=20)
                fields[label] = e
            
            def save_custom():
                name = fields["名称:"].get().strip()
                if not name:
                    return
                attrs = {}
                for attr_name, field_key in [("力量", "力量加成:"), ("敏捷", "敏捷加成:"), 
                                              ("体质", "体质加成:"), ("智力", "智力加成:")]:
                    try:
                        val = int(fields[field_key].get())
                        if val > 0:
                            attrs[attr_name] = val
                    except:
                        pass
                
                self.character_system.add_custom_weapon(
                    name=name, category=cat_var.get(), quality=fields["品质:"].get(),
                    desc=fields["描述:"].get(), attributes=attrs
                )
                update_list()
                self._log(f"添加自定义武器: {name}")
                sub.destroy()
            
            tk.Button(sub, text="保存", bg=C['accent'], fg='white', command=save_custom).pack(pady=10)
        
        btn_frame = tk.Frame(dialog, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        tk.Button(btn_frame, text="装备", font=('微软雅黑', 10),
                 bg=C['accent'], fg='white', relief=tk.FLAT, command=equip).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="+ 自定义武器", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT, command=add_custom).pack(side=tk.RIGHT, padx=5)
    
    def _learn_skill(self):
        """学习技能"""
        if not self.character_system or not self.character_system.character:
            messagebox.showinfo("提示", "请先创建角色")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("学习技能")
        dialog.geometry("500x450")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        tk.Label(dialog, text="选择技能:", font=('微软雅黑', 10, 'bold'),
                bg=C['bg_dark'], fg=C['text_primary']).pack(pady=(10, 5))
        
        cat_var = tk.StringVar()
        cats = self.character_system.get_skill_categories()
        cat_combo = ttk.Combobox(dialog, textvariable=cat_var, values=cats, state="readonly", width=20)
        cat_combo.pack(pady=5)
        cat_combo.set(cats[0] if cats else "")
        
        skill_listbox = tk.Listbox(dialog, bg=C['bg_card'], fg=C['text_primary'],
                                  font=('微软雅黑', 9), selectbackground=C['accent'], height=10)
        skill_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        def update_list(*args):
            skill_listbox.delete(0, tk.END)
            skills = self.character_system.get_skills(cat_var.get())
            for s in skills:
                custom = " [自定义]" if s.get('custom') else ""
                skill_listbox.insert(tk.END, f"{s.get('name', '')}{custom} - {s.get('desc', '')} (MP:{s.get('mp_cost', 0)})")
        
        cat_combo.bind('<<ComboboxSelected>>', update_list)
        update_list()
        
        def learn():
            sel = skill_listbox.curselection()
            if sel:
                skills = self.character_system.get_skills(cat_var.get())
                if sel[0] < len(skills):
                    skill = skills[sel[0]]
                    if self.character_system.character.learn_skill(skill):
                        self.character_system.save_character()
                        self._update_char_display()
                        self._log(f"学会技能: {skill.get('name', '')}")
                    else:
                        messagebox.showinfo("提示", "已学会该技能")
                    dialog.destroy()
        
        def add_custom():
            sub = tk.Toplevel(dialog)
            sub.title("自定义技能")
            sub.geometry("350x250")
            sub.configure(bg=C['bg_dark'])
            
            fields = {}
            for label, default in [("名称:", ""), ("类型:", cat_var.get() or "攻击"), ("描述:", ""), ("MP消耗:", "10")]:
                tk.Label(sub, text=label, bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, padx=20, pady=(5,0))
                e = tk.Entry(sub, width=30)
                e.insert(0, default)
                e.pack(padx=20)
                fields[label] = e
            
            def save_custom():
                name = fields["名称:"].get().strip()
                if not name:
                    return
                mp = int(fields["MP消耗:"].get() or 0)
                self.character_system.add_custom_skill(
                    name=name, skill_type=fields["类型:"].get(),
                    desc=fields["描述:"].get(), mp_cost=mp
                )
                update_list()
                self._log(f"添加自定义技能: {name}")
                sub.destroy()
            
            tk.Button(sub, text="保存", bg=C['accent'], fg='white', command=save_custom).pack(pady=10)
        
        btn_frame = tk.Frame(dialog, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        tk.Button(btn_frame, text="学习", font=('微软雅黑', 10),
                 bg=C['accent'], fg='white', relief=tk.FLAT, command=learn).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="+ 自定义技能", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT, command=add_custom).pack(side=tk.RIGHT, padx=5)
    
    def _refresh_notes(self):
        """刷新笔记列表"""
        self.notes_list.delete(0, tk.END)
        note_type = self.note_type_var.get()
        
        if note_type == "project":
            notes = self.note_manager.get_project_notes()
            for n in notes:
                self.notes_list.insert(tk.END, f"{n.get('title', '无标题')}")
        elif note_type == "doc":
            notes = self.note_manager.get_doc_notes(self.current_chapter)
            for n in notes:
                self.notes_list.insert(tk.END, f"[位置{n.get('position',0)}] {n.get('content', '')[:30]}")
        elif note_type == "sticky":
            notes = self.note_manager.get_sticky_notes()
            for n in notes:
                self.notes_list.insert(tk.END, f"{n.get('content', '')[:40]}")
    
    def _on_note_select(self, event):
        """笔记选中"""
        selection = self.notes_list.curselection()
        if not selection:
            return
        idx = selection[0]
        note_type = self.note_type_var.get()
        
        notes = []
        if note_type == "project":
            notes = self.note_manager.get_project_notes()
        elif note_type == "doc":
            notes = self.note_manager.get_doc_notes(self.current_chapter)
        elif note_type == "sticky":
            notes = self.note_manager.get_sticky_notes()
        
        if idx < len(notes):
            self.note_content.delete("1.0", tk.END)
            self.note_content.insert("1.0", notes[idx].get("content", ""))
    
    def _add_note(self):
        """新建笔记"""
        note_type = self.note_type_var.get()
        content = "新笔记内容..."
        
        if note_type == "project":
            self.note_manager.add_project_note("新笔记", content)
        elif note_type == "doc":
            self.note_manager.add_doc_note(self.current_chapter, content)
        elif note_type == "sticky":
            self.note_manager.add_sticky_note(content)
        
        self._refresh_notes()
    
    def _save_note(self):
        """保存当前笔记"""
        selection = self.notes_list.curselection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一个笔记")
            return
        
        idx = selection[0]
        note_type = self.note_type_var.get()
        content = self.note_content.get("1.0", tk.END).strip()
        
        if note_type == "project":
            notes = self.note_manager.get_project_notes()
            if idx < len(notes):
                self.note_manager.update_project_note(notes[idx]["id"], content=content)
        elif note_type == "doc":
            notes = self.note_manager.get_doc_notes(self.current_chapter)
            if idx < len(notes):
                notes[idx]["content"] = content
                self.note_manager.save_doc_notes(self.current_chapter, notes)
        elif note_type == "sticky":
            notes = self.note_manager.get_sticky_notes()
            if idx < len(notes):
                notes[idx]["content"] = content
                self.note_manager.save_sticky_notes(notes)
        
        self._log("笔记已保存")
    
    def _delete_note(self):
        """删除笔记"""
        selection = self.notes_list.curselection()
        if not selection:
            return
        
        if not messagebox.askyesno("确认", "确定删除此笔记？"):
            return
        
        idx = selection[0]
        note_type = self.note_type_var.get()
        
        if note_type == "project":
            notes = self.note_manager.get_project_notes()
            if idx < len(notes):
                self.note_manager.delete_project_note(notes[idx]["id"])
        elif note_type == "doc":
            notes = self.note_manager.get_doc_notes(self.current_chapter)
            if idx < len(notes):
                self.note_manager.delete_doc_note(self.current_chapter, notes[idx]["id"])
        elif note_type == "sticky":
            notes = self.note_manager.get_sticky_notes()
            if idx < len(notes):
                self.note_manager.delete_sticky_note(notes[idx]["id"])
        
        self.note_content.delete("1.0", tk.END)
        self._refresh_notes()
    
    def _send_sticky_to_project(self):
        """将便笺发送到工程笔记"""
        selection = self.notes_list.curselection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一个便笺")
            return
        
        idx = selection[0]
        if self.note_type_var.get() != "sticky":
            messagebox.showinfo("提示", "请先切换到便笺本")
            return
        
        notes = self.note_manager.get_sticky_notes()
        if idx < len(notes):
            self.note_manager.send_sticky_to_project(notes[idx]["id"])
            self._log("便笺已发送到工程笔记")
            messagebox.showinfo("成功", "便笺已发送到工程笔记")
    
    # ===== 创作工具集 =====
    
    def _refresh_toolkit(self):
        """刷新工具集界面"""
        for w in self.tool_content_frame.winfo_children():
            w.destroy()
        
        tool_type = self.tool_type_var.get()
        
        if tool_type == "elements":
            self._build_elements_tool()
        elif tool_type == "bridges":
            self._build_bridges_tool()
        elif tool_type == "descriptions":
            self._build_descriptions_tool()
        elif tool_type == "dialogue":
            self._build_dialogue_tool()
        elif tool_type == "story_flow":
            self._build_story_flow_tool()
        elif tool_type == "style":
            self._build_style_tool()
        elif tool_type == "adapt":
            self._build_adapt_tool()
        elif tool_type == "websearch":
            self._build_websearch_tool()
        elif tool_type == "chapters":
            self._build_chapter_analysis_tool()
    
    def _build_elements_tool(self):
        """元素库界面"""
        f = self.tool_content_frame
        
        ttk.Label(f, text="小说元素库 - 选择元素组合生成背景设定", font=("", 11, "bold")).pack(anchor=tk.W, pady=5)
        
        # 类别选择
        cat_frame = ttk.Frame(f)
        cat_frame.pack(fill=tk.X, pady=3)
        ttk.Label(cat_frame, text="类别:").pack(side=tk.LEFT)
        self.elem_cat_var = tk.StringVar()
        cats = [c["name"] for c in self.element_lib.get_categories()]
        cat_combo = ttk.Combobox(cat_frame, textvariable=self.elem_cat_var, values=cats, state="readonly", width=20)
        cat_combo.pack(side=tk.LEFT, padx=5)
        cat_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_element_list())
        
        # 元素列表
        self.elem_listbox = tk.Listbox(f, height=8, selectmode=tk.MULTIPLE)
        self.elem_listbox.pack(fill=tk.X, pady=3)
        
        # 生成按钮 + 自定义元素（同一行）
        btn_frame = ttk.Frame(f)
        btn_frame.pack(fill=tk.X, pady=3)
        ttk.Button(btn_frame, text="组合生成背景设定", command=self._gen_background_from_elements).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="查看元素详情", command=self._view_element_detail).pack(side=tk.LEFT, padx=5)
        ttk.Label(btn_frame, text="|").pack(side=tk.LEFT, padx=5)
        ttk.Label(btn_frame, text="自定义:").pack(side=tk.LEFT)
        self.custom_elem_entry = ttk.Entry(btn_frame, width=12)
        self.custom_elem_entry.pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="添加", command=self._add_custom_element).pack(side=tk.LEFT)
        
        # 结果（填充剩余空间）
        self.elem_result = scrolledtext.ScrolledText(f, height=8, wrap=tk.WORD, font=("微软雅黑", 10))
        self.elem_result.pack(fill=tk.BOTH, expand=True, pady=3)
        
        if cats:
            self.elem_cat_var.set(cats[0])
            self._refresh_element_list()
    
    def _refresh_element_list(self):
        self.elem_listbox.delete(0, tk.END)
        items = self.element_lib.get_items(self.elem_cat_var.get())
        for item in items:
            self.elem_listbox.insert(tk.END, item.get("name", ""))
    
    def _view_element_detail(self):
        sel = self.elem_listbox.curselection()
        if not sel:
            return
        items = self.element_lib.get_items(self.elem_cat_var.get())
        if sel[0] < len(items):
            item = items[sel[0]]
            self.elem_result.delete("1.0", tk.END)
            self.elem_result.insert("1.0", f"名称: {item.get('name', '')}\n\n模板:\n{item.get('template', '')}\n\n标签: {', '.join(item.get('tags', []))}")
    
    def _gen_background_from_elements(self):
        sel = self.elem_listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "请先选择元素")
            return
        
        items = self.element_lib.get_items(self.elem_cat_var.get())
        selected = [items[i] for i in sel if i < len(items)]
        
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        def run():
            try:
                result = self.element_lib.generate_background(
                    self.ai_client, selected, 
                    self.genre_var.get(), self.title_var.get() or "未命名"
                )
                self.root.after(0, lambda: self._show_tool_result(self.elem_result, result))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _add_custom_element(self):
        """添加自定义元素"""
        name = self.custom_elem_entry.get().strip()
        if not name:
            messagebox.showinfo("提示", "请输入元素名称")
            return
        cat = self.elem_cat_var.get()
        if not cat:
            messagebox.showinfo("提示", "请先选择类别")
            return
        self.element_lib.add_custom_item(cat, {"name": name, "template": f"自定义元素: {name}", "tags": ["自定义"]})
        self._refresh_element_list()
        self.custom_elem_entry.delete(0, tk.END)
        self._log(f"添加自定义元素: {name} (类别: {cat})")
        messagebox.showinfo("成功", f"已添加自定义元素: {name}")
    
    def _build_bridges_tool(self):
        """桥段库界面"""
        f = self.tool_content_frame
        
        ttk.Label(f, text="角色桥段库 - 经典网文桥段生成", font=("", 11, "bold")).pack(anchor=tk.W, pady=5)
        
        cat_frame = ttk.Frame(f)
        cat_frame.pack(fill=tk.X, pady=3)
        ttk.Label(cat_frame, text="桥段类型:").pack(side=tk.LEFT)
        self.bridge_cat_var = tk.StringVar()
        cats = [c["name"] for c in self.bridge_lib.get_categories()]
        ttk.Combobox(cat_frame, textvariable=self.bridge_cat_var, values=cats, state="readonly", width=20).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(f, text="场景设定:").pack(anchor=tk.W, pady=2)
        self.bridge_setting = ttk.Entry(f, width=60)
        self.bridge_setting.pack(fill=tk.X, pady=2)
        self.bridge_setting.insert(0, "深夜的修炼室中")
        
        # 按钮行 + 自定义桥段
        btn_frame = ttk.Frame(f)
        btn_frame.pack(fill=tk.X, pady=3)
        ttk.Button(btn_frame, text="查看模板", command=self._view_bridge_template).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="AI生成桥段", command=self._gen_bridge).pack(side=tk.LEFT, padx=5)
        ttk.Label(btn_frame, text="|").pack(side=tk.LEFT, padx=5)
        ttk.Label(btn_frame, text="自定义:").pack(side=tk.LEFT)
        self.custom_bridge_entry = ttk.Entry(btn_frame, width=20)
        self.custom_bridge_entry.pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="添加", command=self._add_custom_bridge).pack(side=tk.LEFT)
        
        self.bridge_result = scrolledtext.ScrolledText(f, height=10, wrap=tk.WORD, font=("微软雅黑", 10))
        self.bridge_result.pack(fill=tk.BOTH, expand=True, pady=3)
        
        if cats:
            self.bridge_cat_var.set(cats[0])
    
    def _view_bridge_template(self):
        templates = self.bridge_lib.get_templates(self.bridge_cat_var.get())
        self.bridge_result.delete("1.0", tk.END)
        self.bridge_result.insert("1.0", "\n\n".join(templates))
    
    def _gen_bridge(self):
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        # 使用角色系统中的实际角色数据
        characters = {}
        if self.character_system and self.character_system.character:
            char = self.character_system.character
            characters = {char.name: char.personality or "性格待定"}
        elif self.memory:
            chars = self.memory.get_characters()
            if chars:
                for name, info in list(chars.items())[:3]:
                    characters[name] = info.get("personality", "") if isinstance(info, dict) else ""
        if not characters:
            characters = {"主角": "待设定"}
        
        def run():
            try:
                result = self.bridge_lib.generate_bridge(
                    self.ai_client, self.bridge_cat_var.get(),
                    characters, self.bridge_setting.get()
                )
                self.root.after(0, lambda: self._show_tool_result(self.bridge_result, result))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _add_custom_bridge(self):
        """添加自定义桥段"""
        template = self.custom_bridge_entry.get().strip()
        if not template:
            messagebox.showinfo("提示", "请输入桥段模板")
            return
        cat = self.bridge_cat_var.get()
        if not cat:
            messagebox.showinfo("提示", "请先选择桥段类型")
            return
        self.bridge_lib.add_custom_item(cat, template)
        self.custom_bridge_entry.delete(0, tk.END)
        self._log(f"添加自定义桥段: {template[:30]}... (类型: {cat})")
        messagebox.showinfo("成功", f"已添加自定义桥段到 {cat}")
    
    def _build_descriptions_tool(self):
        """描写库界面"""
        f = self.tool_content_frame
        
        ttk.Label(f, text="事物描写库 - 生成各类描写", font=("", 11, "bold")).pack(anchor=tk.W, pady=5)
        
        cat_frame = ttk.Frame(f)
        cat_frame.pack(fill=tk.X, pady=3)
        ttk.Label(cat_frame, text="类别:").pack(side=tk.LEFT)
        self.desc_cat_var = tk.StringVar()
        cats = self.desc_lib.get_categories()
        ttk.Combobox(cat_frame, textvariable=self.desc_cat_var, values=cats, state="readonly", width=15).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(cat_frame, text="描写对象:").pack(side=tk.LEFT, padx=(10,0))
        self.desc_subject = ttk.Entry(cat_frame, width=15)
        self.desc_subject.pack(side=tk.LEFT, padx=5)
        ttk.Button(cat_frame, text="生成描写", command=self._gen_description).pack(side=tk.LEFT, padx=5)
        ttk.Label(cat_frame, text="|").pack(side=tk.LEFT, padx=3)
        ttk.Label(cat_frame, text="自定义:").pack(side=tk.LEFT)
        self.custom_desc_entry = ttk.Entry(cat_frame, width=10)
        self.custom_desc_entry.pack(side=tk.LEFT, padx=2)
        ttk.Button(cat_frame, text="添加", command=self._add_custom_description).pack(side=tk.LEFT)
        
        self.desc_result = scrolledtext.ScrolledText(f, height=10, wrap=tk.WORD, font=("微软雅黑", 10))
        self.desc_result.pack(fill=tk.BOTH, expand=True, pady=3)
        
        if cats:
            self.desc_cat_var.set(cats[0])
    
    def _gen_description(self):
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        def run():
            try:
                result = self.desc_lib.generate_description(
                    self.ai_client, self.desc_subject.get() or "日出",
                    self.desc_cat_var.get()
                )
                self.root.after(0, lambda: self._show_tool_result(self.desc_result, result))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _add_custom_description(self):
        """添加自定义描写关键词"""
        keyword = self.custom_desc_entry.get().strip()
        if not keyword:
            messagebox.showinfo("提示", "请输入描写关键词")
            return
        cat = self.desc_cat_var.get()
        if not cat:
            messagebox.showinfo("提示", "请先选择类别")
            return
        self.desc_lib.add_custom_item(cat, keyword)
        self.custom_desc_entry.delete(0, tk.END)
        self._log(f"添加自定义描写关键词: {keyword} (类别: {cat})")
        messagebox.showinfo("成功", f"已添加自定义关键词: {keyword} 到 {cat}")
    
    def _build_dialogue_tool(self):
        """对话推演界面"""
        f = self.tool_content_frame
        
        ttk.Label(f, text="情景对话推演 - 角色互动对话生成", font=("", 11, "bold")).pack(anchor=tk.W, pady=5)
        
        ttk.Label(f, text="场景描述:").pack(anchor=tk.W)
        self.dlg_scenario = ttk.Entry(f, width=60)
        self.dlg_scenario.pack(fill=tk.X, pady=3)
        self.dlg_scenario.insert(0, "两个老友多年后重逢，在咖啡馆聊天")
        
        btn_frame = ttk.Frame(f)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="开始推演", command=self._start_dialogue).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="继续推演", command=self._continue_dialogue).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="插入到章节", command=self._insert_dialogue).pack(side=tk.RIGHT)
        
        self.dlg_result = scrolledtext.ScrolledText(f, height=12, wrap=tk.WORD, font=("微软雅黑", 10))
        self.dlg_result.pack(fill=tk.BOTH, expand=True, pady=5)
    
    def _start_dialogue(self):
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        self.dialogue_engine = DialogueEngine(self.ai_client)
        
        # 使用角色系统中的实际角色
        characters = []
        if self.character_system:
            for name in self.character_system.get_character_names()[:4]:
                char = self.character_system.characters.get(name)
                if char:
                    characters.append({"name": name, "personality": char.personality or "未知"})
        if not characters and self.memory:
            chars = self.memory.get_characters()
            if chars:
                for name, info in list(chars.items())[:4]:
                    p = info.get("personality", "") if isinstance(info, dict) else ""
                    characters.append({"name": name, "personality": p or "未知"})
        if not characters:
            characters = [{"name": "角色A", "personality": "开朗"}, {"name": "角色B", "personality": "内敛"}]
        
        def run():
            try:
                result = self.dialogue_engine.start_dialogue(
                    self.dlg_scenario.get(), characters
                )
                text = self.dialogue_engine.export_text()
                self.root.after(0, lambda: self._show_tool_result(self.dlg_result, text))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _continue_dialogue(self):
        if not self.dialogue_engine:
            messagebox.showinfo("提示", "请先开始推演")
            return
        
        def run():
            try:
                self.dialogue_engine.continue_dialogue()
                text = self.dialogue_engine.export_text()
                self.root.after(0, lambda: self._show_tool_result(self.dlg_result, text))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _insert_dialogue(self):
        content = self.dlg_result.get("1.0", tk.END).strip()
        if content:
            self.content_text.insert(tk.INSERT, "\n\n" + content)
    
    def _build_story_flow_tool(self):
        """故事流推演界面"""
        C = UIStyle.COLORS
        f = self.tool_content_frame
        
        tk.Label(f, text="故事流推演 - 4种模式", font=("", 11, "bold"),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, pady=5)
        
        self.sf_mode_var = tk.IntVar(value=1)
        modes = [
            (1, "正向推演", "背景+事件→推演过程"),
            (2, "桥接推演", "开端+结局→推演中间"),
            (3, "分支推演", "当前故事→多个走向"),
            (4, "冲突升级", "当前局面→逐步升级"),
        ]
        mode_frame = tk.Frame(f, bg=C['bg_dark'])
        mode_frame.pack(fill=tk.X, pady=3)
        for val, name, desc in modes:
            tk.Radiobutton(mode_frame, text=f"{name}", variable=self.sf_mode_var, value=val,
                          font=('微软雅黑', 9), bg=C['bg_dark'], fg=C['text_secondary'],
                          selectcolor=C['accent']).pack(side=tk.LEFT, padx=5)
        
        # 提示文字
        self.sf_hint = tk.Label(f, text="模式1: 输入背景和事件，推演故事发展过程", 
                               font=('微软雅黑', 8), bg=C['bg_dark'], fg=C['text_muted'])
        self.sf_hint.pack(anchor=tk.W, pady=2)
        
        # 模式切换时更新提示
        def update_hint(*args):
            hints = {1: "模式1: 输入背景和事件，推演故事发展过程",
                    2: "模式2: 第一行写开端，最后一行写结局，推演中间过程",
                    3: "模式3: 输入当前故事，生成多个可能走向分支",
                    4: "模式4: 输入当前局面，推演冲突逐步升级的过程"}
            self.sf_hint.config(text=hints.get(self.sf_mode_var.get(), ""))
        
        self.sf_mode_var.trace_add('write', update_hint)
        
        tk.Label(f, text="输入内容:", font=('微软雅黑', 9),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, pady=3)
        self.sf_input = tk.Text(f, height=5, wrap=tk.WORD, font=('微软雅黑', 10),
                               bg=C['input_bg'], fg=C['text_primary'])
        self.sf_input.pack(fill=tk.X, pady=3)
        
        btn_frame = tk.Frame(f, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(btn_frame, text="开始推演", font=('微软雅黑', 9),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._run_story_flow).pack(side=tk.LEFT)
        tk.Button(btn_frame, text="插入到章节", font=('微软雅黑', 9),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=10,
                 command=lambda: self._insert_to_chapter(self.sf_result)).pack(side=tk.RIGHT)
        
        self.sf_result = tk.Text(f, height=10, wrap=tk.WORD, font=('微软雅黑', 10),
                                bg=C['bg_card'], fg=C['text_primary'])
        self.sf_result.pack(fill=tk.BOTH, expand=True, pady=5)
    
    def _run_story_flow(self):
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        self.story_flow_engine = StoryFlowEngine(self.ai_client)
        input_text = self.sf_input.get("1.0", tk.END).strip()
        
        if not input_text:
            messagebox.showinfo("提示", "请输入内容")
            return
        
        mode = self.sf_mode_var.get()
        
        def run():
            try:
                if mode == 1:
                    result = self.story_flow_engine.mode1_forward(input_text, "主角", input_text)
                elif mode == 2:
                    lines = input_text.split("\n")
                    beginning = lines[0] if lines else ""
                    ending = lines[-1] if len(lines) > 1 else "结局待定"
                    result = self.story_flow_engine.mode2_bridge(beginning, ending)
                elif mode == 3:
                    result = self.story_flow_engine.mode3_branch(input_text, 3)
                elif mode == 4:
                    result = self.story_flow_engine.mode4_conflict_escalation(input_text)
                else:
                    result = "请选择推演模式"
                
                self.root.after(0, lambda: self._show_tool_result(self.sf_result, result))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _build_style_tool(self):
        """风格转换界面"""
        f = self.tool_content_frame
        
        ttk.Label(f, text="风格转换 - 仿写、改写、风格调整", font=("", 11, "bold")).pack(anchor=tk.W, pady=5)
        
        style_frame = ttk.Frame(f)
        style_frame.pack(fill=tk.X, pady=3)
        ttk.Label(style_frame, text="目标风格:").pack(side=tk.LEFT)
        self.style_var = tk.StringVar(value="热血爽文")
        styles = list(StyleTransferEngine.STYLES.keys())
        ttk.Combobox(style_frame, textvariable=self.style_var, values=styles, state="readonly", width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(style_frame, text="转换当前章节风格", command=self._convert_style).pack(side=tk.LEFT, padx=10)
        
        self.style_result = scrolledtext.ScrolledText(f, height=12, wrap=tk.WORD, font=("微软雅黑", 10))
        self.style_result.pack(fill=tk.BOTH, expand=True, pady=5)
    
    def _convert_style(self):
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        current_text = self.content_text.get("1.0", tk.END).strip()
        if not current_text:
            messagebox.showinfo("提示", "没有可转换的内容")
            return
        
        self.style_engine = StyleTransferEngine(self.ai_client)
        
        def run():
            try:
                result = self.style_engine.convert_style(current_text, self.style_var.get())
                self.root.after(0, lambda: self._show_tool_result(self.style_result, result))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _build_adapt_tool(self):
        """智能改编界面"""
        f = self.tool_content_frame
        
        ttk.Label(f, text="智能改编 - 圈定截取改编，显示匹配率", font=("", 11, "bold")).pack(anchor=tk.W, pady=5)
        
        ttk.Label(f, text="改编指示:").pack(anchor=tk.W)
        self.adapt_instr = ttk.Entry(f, width=60)
        self.adapt_instr.pack(fill=tk.X, pady=3)
        self.adapt_instr.insert(0, "改写为更紧张的氛围")
        
        btn_frame = ttk.Frame(f)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="改编选中文本", command=self._adapt_selected).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="随机抽取改编", command=self._adapt_random).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="替换原文", command=self._replace_with_adapted).pack(side=tk.RIGHT)
        
        self.adapt_result = scrolledtext.ScrolledText(f, height=10, wrap=tk.WORD, font=("微软雅黑", 10))
        self.adapt_result.pack(fill=tk.BOTH, expand=True, pady=5)
    
    def _adapt_selected(self):
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        try:
            selected = self.content_text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except:
            selected = self.content_text.get("1.0", tk.END).strip()[:500]
        
        if not selected:
            messagebox.showinfo("提示", "请先选择要改编的文本")
            return
        
        self.adapt_engine = AdaptEngine(self.ai_client)
        
        def run():
            try:
                result = self.adapt_engine.adapt_segment(selected, self.adapt_instr.get())
                text = f"【匹配率: {result['match_rate']}%】\n\n{result['adapted']}"
                self.root.after(0, lambda: self._show_tool_result(self.adapt_result, text))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _adapt_random(self):
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        current_text = self.content_text.get("1.0", tk.END).strip()
        if not current_text:
            messagebox.showinfo("提示", "没有可改编的内容")
            return
        
        self.adapt_engine = AdaptEngine(self.ai_client)
        
        def run():
            try:
                results = self.adapt_engine.random_adapt(current_text, 2)
                text = ""
                for i, r in enumerate(results):
                    text += f"=== 片段{i+1} (匹配率: {r['match_rate']}%) ===\n"
                    text += f"{r['adapted']}\n\n"
                self.root.after(0, lambda: self._show_tool_result(self.adapt_result, text))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _replace_with_adapted(self):
        adapted = self.adapt_result.get("1.0", tk.END).strip()
        if adapted:
            # 去掉匹配率行
            lines = adapted.split("\n")
            content = "\n".join(l for l in lines if not l.startswith("【匹配率"))
            try:
                self.content_text.delete(tk.SEL_FIRST, tk.SEL_LAST)
            except:
                pass
            self.content_text.insert(tk.INSERT, content.strip())
    
    def _insert_to_chapter(self, text_widget):
        content = text_widget.get("1.0", tk.END).strip()
        if content:
            self.content_text.insert(tk.INSERT, "\n\n" + content)
    
    def _show_tool_result(self, widget, text):
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
    
    def _build_websearch_tool(self):
        """热点改编界面"""
        C = UIStyle.COLORS
        f = self.tool_content_frame
        
        tk.Label(f, text="联网搜索热点改编 - 将网络热点改编为小说桥段", font=("", 11, "bold"),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, pady=5)
        
        # 分类选择
        cat_frame = tk.Frame(f, bg=C['bg_dark'])
        cat_frame.pack(fill=tk.X, pady=3)
        
        self.ws_category_var = tk.StringVar(value="热梗改编")
        self.web_search_engine = WebSearchAdaptEngine(self.ai_client)
        cats = self.web_search_engine.get_categories()
        
        for i, cat in enumerate(cats):
            tk.Radiobutton(cat_frame, text=cat, variable=self.ws_category_var, value=cat,
                          font=('微软雅黑', 9), bg=C['bg_dark'], fg=C['text_secondary'],
                          selectcolor=C['accent'], command=self._refresh_ws_list).pack(side=tk.LEFT, padx=5)
        
        # 搜索输入
        search_frame = tk.Frame(f, bg=C['bg_dark'])
        search_frame.pack(fill=tk.X, pady=5)
        self.ws_search_entry = tk.Entry(search_frame, font=('微软雅黑', 10), width=40,
                                       bg=C['input_bg'], fg=C['text_primary'])
        self.ws_search_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.ws_search_entry.insert(0, "输入热点关键词或梗，AI自动改编...")
        
        tk.Button(search_frame, text="AI搜索改编", font=('微软雅黑', 9),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._ws_adapt).pack(side=tk.LEFT, padx=5)
        
        # 随机按钮
        tk.Button(f, text="随机来一个热点", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._ws_random).pack(pady=5)
        
        # 内置热点列表
        tk.Label(f, text="内置热点（点击直接生成）：", font=('微软雅黑', 9, 'bold'),
                bg=C['bg_dark'], fg=C['accent_light']).pack(anchor=tk.W, pady=(10, 3))
        
        items = self.web_search_engine.get_items(self.ws_category_var.get())
        list_frame = tk.Frame(f, bg=C['bg_dark'])
        list_frame.pack(fill=tk.X)
        self.ws_listbox = tk.Listbox(list_frame, bg=C['bg_card'], fg=C['text_secondary'],
                                     font=('微软雅黑', 9), height=8,
                                     selectbackground=C['accent'], relief=tk.FLAT)
        for item in items:
            self.ws_listbox.insert(tk.END, f"{item.get('name','')}: {item.get('desc','')}")
        scrollbar = tk.Scrollbar(list_frame, command=self.ws_listbox.yview)
        self.ws_listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.ws_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.ws_listbox.bind('<Double-Button-1>', self._ws_generate_from_list)
        
        # 生成按钮
        tk.Button(f, text="改编选中热点为小说桥段", font=('微软雅黑', 9, 'bold'),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._ws_generate_from_list).pack(pady=5)
        
        # 自定义添加按钮区
        add_btn_frame = tk.Frame(f, bg=C['bg_dark'])
        add_btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(add_btn_frame, text="+ 添加自定义热点", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._ws_add_custom).pack(side=tk.LEFT, padx=5)
        tk.Button(add_btn_frame, text="删除自定义", font=('微软雅黑', 9),
                 bg=C['error'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._ws_delete_custom).pack(side=tk.LEFT, padx=5)
        
        # 结果展示
        self.ws_result = tk.Text(f, height=12, wrap=tk.WORD, font=('微软雅黑', 10),
                                bg=C['bg_card'], fg=C['text_primary'],
                                relief=tk.FLAT, padx=15, pady=15)
        self.ws_result.pack(fill=tk.BOTH, expand=True, pady=5)
        
        tk.Button(f, text="插入到章节", font=('微软雅黑', 9),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=10,
                 command=lambda: self._insert_to_chapter(self.ws_result)).pack(pady=5)
    
    def _ws_random(self):
        """随机获取一个热点改编"""
        if not self.web_search_engine:
            self.web_search_engine = WebSearchAdaptEngine(self.ai_client)
        result = self.web_search_engine.random_meme()
        self._show_tool_result(self.ws_result, result)
    
    def _ws_adapt(self):
        """AI搜索改编"""
        query = self.ws_search_entry.get().strip()
        if not query or query == "输入热点关键词或梗，AI自动改编...":
            messagebox.showinfo("提示", "请输入关键词")
            return
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI")
            return
        
        def run():
            try:
                engine = WebSearchAdaptEngine(self.ai_client)
                result = engine.search_and_adapt(query)
                self.root.after(0, lambda: self._show_tool_result(self.ws_result, result))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _ws_generate_from_list(self, event=None):
        """从列表生成改编"""
        sel = self.ws_listbox.curselection()
        if not sel:
            return
        category = self.ws_category_var.get()
        if not self.web_search_engine:
            self.web_search_engine = WebSearchAdaptEngine(self.ai_client, self.current_novel_dir)
        
        items = self.web_search_engine.get_items(category)
        idx = sel[0]
        if idx < len(items):
            item = items[idx]
            template = item.get("adapt", item.get("template", ""))
            result = self.web_search_engine._fill_template(template)
            self._show_tool_result(self.ws_result, result)
    
    def _ws_add_custom(self):
        """用户添加自定义热点"""
        dialog = tk.Toplevel(self.root)
        dialog.title("添加自定义热点")
        dialog.geometry("500x400")
        dialog.configure(bg=UIStyle.COLORS['bg_dark'])
        C = UIStyle.COLORS
        
        ttk.Label(dialog, text="分类:").pack(anchor=tk.W, padx=20, pady=(15,3))
        cat_var = tk.StringVar(value=self.ws_category_var.get())
        cats = WebSearchAdaptEngine(self.ai_client).get_categories()
        ttk.Combobox(dialog, textvariable=cat_var, values=cats, state="readonly", width=47).pack(padx=20)
        
        ttk.Label(dialog, text="热点名称:").pack(anchor=tk.W, padx=20, pady=(10,3))
        name_entry = ttk.Entry(dialog, width=50)
        name_entry.pack(padx=20)
        
        ttk.Label(dialog, text="描述（一句话说明）:").pack(anchor=tk.W, padx=20, pady=(10,3))
        desc_entry = ttk.Entry(dialog, width=50)
        desc_entry.pack(padx=20)
        
        ttk.Label(dialog, text="改编模板（用{name}等变量）:").pack(anchor=tk.W, padx=20, pady=(10,3))
        template_text = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, height=6)
        template_text.pack(padx=20, fill=tk.X)
        template_text.insert("1.0", "{name}是一个普通{职业}，直到那天{事件}...")
        
        def save():
            name = name_entry.get().strip()
            desc = desc_entry.get().strip()
            tmpl = template_text.get("1.0", tk.END).strip()
            if not name or not tmpl:
                messagebox.showwarning("提示", "请填写名称和模板")
                return
            if not self.web_search_engine:
                self.web_search_engine = WebSearchAdaptEngine(self.ai_client, self.current_novel_dir)
            self.web_search_engine.add_custom_meme(cat_var.get(), name, desc, tmpl)
            self._log(f"已添加自定义热点: {name}")
            dialog.destroy()
            # 刷新列表
            self._refresh_ws_list()
            messagebox.showinfo("成功", f"已保存自定义热点「{name}」")
        
        ttk.Button(dialog, text="保存", command=save).pack(pady=15)
    
    def _ws_delete_custom(self):
        """删除自定义热点"""
        sel = self.ws_listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "请先选择要删除的热点")
            return
        if not self.web_search_engine:
            self.web_search_engine = WebSearchAdaptEngine(self.ai_client, self.current_novel_dir)
        category = self.ws_category_var.get()
        items = self.web_search_engine.get_items(category)
        idx = sel[0]
        if idx < len(items):
            if not items[idx].get("custom"):
                messagebox.showinfo("提示", "只能删除自定义添加的热点")
                return
            if messagebox.askyesno("确认", f"确定删除「{items[idx].get('name','')}」？"):
                # 直接从列表中移除并持久化
                removed = items.pop(idx)
                self.web_search_engine._save_custom(category, items)
                self._refresh_ws_list()
                self._log(f"已删除自定义热点: {removed.get('name','')}")
    
    def _refresh_ws_list(self):
        """刷新热点列表"""
        self.ws_listbox.delete(0, tk.END)
        if not self.web_search_engine:
            self.web_search_engine = WebSearchAdaptEngine(self.ai_client, self.current_novel_dir)
        items = self.web_search_engine.get_items(self.ws_category_var.get())
        for item in items:
            marker = "[自定义]" if item.get("custom") else ""
            self.ws_listbox.insert(tk.END, f"{marker}{item.get('name','')}: {item.get('desc','')}")
    
    # ===== 章节分析工具 =====
    
    def _build_chapter_analysis_tool(self):
        """章节文件浏览+智能推荐"""
        C = UIStyle.COLORS
        f = self.tool_content_frame
        
        tk.Label(f, text="章节文件分析 - 浏览章节并推荐适用工具", font=("", 11, "bold"),
                bg=C['bg_dark'], fg=C['text_primary']).pack(anchor=tk.W, pady=5)
        
        if not self.current_novel_dir:
            tk.Label(f, text="请先新建或打开小说", font=("", 10),
                    bg=C['bg_dark'], fg=C['text_muted']).pack(pady=20)
            return
        
        chapters_dir = self.current_novel_dir / "chapters"
        
        # 章节文件列表
        list_frame = tk.Frame(f, bg=C['bg_dark'])
        list_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(list_frame, text="章节文件:", font=('微软雅黑', 9, 'bold'),
                bg=C['bg_dark'], fg=C['accent_light']).pack(anchor=tk.W)
        
        self.ch_file_listbox = tk.Listbox(list_frame, bg=C['bg_card'], fg=C['text_secondary'],
                                          font=('微软雅黑', 9), height=8,
                                          selectbackground=C['accent'], relief=tk.FLAT)
        self.ch_file_listbox.pack(fill=tk.X, pady=3)
        self.ch_file_listbox.bind('<<ListboxSelect>>', self._on_chapter_file_select)
        
        # 刷新章节列表
        self._refresh_chapter_files()
        
        # 章节内容预览
        tk.Label(f, text="章节内容预览:", font=('微软雅黑', 9, 'bold'),
                bg=C['bg_dark'], fg=C['accent_light']).pack(anchor=tk.W, pady=(10, 3))
        
        self.ch_preview = tk.Text(f, height=6, wrap=tk.WORD, font=('微软雅黑', 9),
                                 bg=C['bg_card'], fg=C['text_primary'],
                                 relief=tk.FLAT, padx=10, pady=10, state=tk.DISABLED)
        self.ch_preview.pack(fill=tk.X, pady=3)
        
        # 智能推荐区
        tk.Label(f, text="智能推荐 - 本章适用的创作工具:", font=('微软雅黑', 9, 'bold'),
                bg=C['bg_dark'], fg=C['accent_light']).pack(anchor=tk.W, pady=(10, 3))
        
        self.ch_recommend = tk.Text(f, height=10, wrap=tk.WORD, font=('微软雅黑', 9),
                                   bg=C['bg_card'], fg=C['text_primary'],
                                   relief=tk.FLAT, padx=10, pady=10, state=tk.DISABLED)
        self.ch_recommend.pack(fill=tk.BOTH, expand=True, pady=3)
        
        # 操作按钮
        btn_frame = tk.Frame(f, bg=C['bg_dark'])
        btn_frame.pack(fill=tk.X, pady=5)
        tk.Button(btn_frame, text="刷新列表", font=('微软雅黑', 9),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=10,
                 command=self._refresh_chapter_files).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="导入章节文件", font=('微软雅黑', 9),
                 bg=C['warning'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._import_chapter_files).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="选择文件夹", font=('微软雅黑', 9),
                 bg=C['bg_light'], fg=C['text_primary'], relief=tk.FLAT, padx=10,
                 command=self._browse_chapter_folder).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="分析当前章节", font=('微软雅黑', 9),
                 bg=C['accent'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._analyze_current_chapter).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="加载到编辑区", font=('微软雅黑', 9),
                 bg=C['success'], fg='white', relief=tk.FLAT, padx=10,
                 command=self._load_chapter_to_editor).pack(side=tk.RIGHT, padx=5)
    
    def _refresh_chapter_files(self):
        """刷新章节文件列表"""
        self.ch_file_listbox.delete(0, tk.END)
        if not self.current_novel_dir:
            return
        
        chapters_dir = self.current_novel_dir / "chapters"
        if not chapters_dir.exists():
            return
        
        chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))
        for f in chapter_files:
            size = f.stat().st_size
            size_kb = size / 1024
            name = f.stem.replace("chapter_", "第") + "章"
            self.ch_file_listbox.insert(tk.END, f"{name} ({size_kb:.1f}KB)")
    
    def _import_chapter_files(self):
        """从任意文件夹导入章节文件"""
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先新建或打开小说")
            return
        
        file_paths = filedialog.askopenfilenames(
            title="选择章节文件",
            filetypes=[
                ("文本文件", "*.txt"),
                ("Markdown文件", "*.md"),
                ("所有文件", "*.*")
            ]
        )
        
        if not file_paths:
            return
        
        chapters_dir = self.current_novel_dir / "chapters"
        chapters_dir.mkdir(exist_ok=True)
        
        # 获取当前最大章节号
        existing = sorted(chapters_dir.glob("chapter_*.txt"))
        next_num = len(existing) + 1
        
        imported = 0
        for src in file_paths:
            src_path = Path(src)
            # 读取源文件
            try:
                with open(src_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                try:
                    with open(src_path, 'r', encoding='gbk') as f:
                        content = f.read()
                except:
                    self._log(f"无法读取文件: {src_path.name}")
                    continue
            
            # 保存到章节目录
            dest = chapters_dir / f"chapter_{next_num:04d}.txt"
            with open(dest, 'w', encoding='utf-8') as f:
                f.write(content)
            
            next_num += 1
            imported += 1
        
        self._refresh_chapter_files()
        self._log(f"成功导入 {imported} 个章节文件")
        messagebox.showinfo("成功", f"已导入 {imported} 个章节文件")
    
    def _browse_chapter_folder(self):
        """选择文件夹浏览章节"""
        folder_path = filedialog.askdirectory(title="选择包含章节文件的文件夹")
        
        if not folder_path:
            return
        
        folder = Path(folder_path)
        
        # 扫描文件夹中的文本文件
        text_files = []
        for ext in ['*.txt', '*.md']:
            text_files.extend(folder.glob(ext))
        
        if not text_files:
            messagebox.showinfo("提示", "该文件夹中没有找到文本文件")
            return
        
        # 显示找到的文件
        text_files = sorted(text_files)
        
        # 创建选择对话框
        dialog = tk.Toplevel(self.root)
        dialog.title(f"选择章节 - {folder.name}")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text=f"找到 {len(text_files)} 个文本文件:", 
                font=('微软雅黑', 10, 'bold')).pack(pady=10)
        
        # 文件列表（可多选）
        listbox = tk.Listbox(dialog, selectmode=tk.MULTIPLE, font=('微软雅黑', 9))
        listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        for f in text_files:
            size_kb = f.stat().st_size / 1024
            listbox.insert(tk.END, f"{f.name} ({size_kb:.1f}KB)")
        
        def import_selected():
            selected = listbox.curselection()
            if not selected:
                messagebox.showwarning("提示", "请选择要导入的文件")
                return
            
            if not self.current_novel_dir:
                messagebox.showwarning("提示", "请先新建或打开小说")
                dialog.destroy()
                return
            
            chapters_dir = self.current_novel_dir / "chapters"
            chapters_dir.mkdir(exist_ok=True)
            
            existing = sorted(chapters_dir.glob("chapter_*.txt"))
            next_num = len(existing) + 1
            
            imported = 0
            for idx in selected:
                src_path = text_files[idx]
                try:
                    with open(src_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    try:
                        with open(src_path, 'r', encoding='gbk') as f:
                            content = f.read()
                    except:
                        continue
                
                dest = chapters_dir / f"chapter_{next_num:04d}.txt"
                with open(dest, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                next_num += 1
                imported += 1
            
            self._refresh_chapter_files()
            self._log(f"从文件夹导入 {imported} 个章节文件")
            messagebox.showinfo("成功", f"已导入 {imported} 个章节文件")
            dialog.destroy()
        
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="全选", command=lambda: listbox.select_set(0, tk.END)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="导入选中", command=import_selected, bg='#10b981', fg='white').pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def _on_chapter_file_select(self, event=None):
        """章节文件选中"""
        sel = self.ch_file_listbox.curselection()
        if not sel or not self.current_novel_dir:
            return
        
        chapters_dir = self.current_novel_dir / "chapters"
        chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))
        idx = sel[0]
        
        if idx < len(chapter_files):
            filepath = chapter_files[idx]
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 显示预览（前500字）
                preview = content[:500] + ("..." if len(content) > 500 else "")
                self.ch_preview.config(state=tk.NORMAL)
                self.ch_preview.delete("1.0", tk.END)
                self.ch_preview.insert("1.0", preview)
                self.ch_preview.config(state=tk.DISABLED)
                
                # 智能分析并推荐
                recommendations = self._analyze_chapter_content(content)
                self.ch_recommend.config(state=tk.NORMAL)
                self.ch_recommend.delete("1.0", tk.END)
                self.ch_recommend.insert("1.0", recommendations)
                self.ch_recommend.config(state=tk.DISABLED)
                
            except Exception as e:
                self._log(f"读取章节失败: {e}")
    
    def _analyze_chapter_content(self, content: str) -> str:
        """分析章节内容，推荐适用的创作工具"""
        recommendations = []
        
        # 战斗场景检测
        battle_keywords = ["战", "斗", "杀", "剑", "刀", "拳", "攻", "击", "斩", "劈", "刺"]
        battle_count = sum(1 for kw in battle_keywords if kw in content)
        if battle_count >= 3:
            recommendations.append("【桥段库 → 角色对战】检测到战斗场景，可使用「角色对战」桥段模板优化战斗描写。")
            recommendations.append("【描写库 → 战斗场景】建议使用「战斗场景」描写增强画面感。")
        
        # 情感场景检测
        emotion_keywords = ["爱", "恨", "泪", "笑", "心", "情", "思念", "牵挂", "拥抱", "吻"]
        emotion_count = sum(1 for kw in emotion_keywords if kw in content)
        if emotion_count >= 3:
            recommendations.append("【桥段库 → 情侣互动】检测到情感描写，可使用「情侣互动」「情侣对话」模板。")
            recommendations.append("【描写库 → 情感心理】建议使用「情感心理」描写增强感染力。")
        
        # 修炼/突破检测
        cultivate_keywords = ["修炼", "突破", "境界", "灵气", "丹田", "功法", "渡劫", "元婴"]
        cultivate_count = sum(1 for kw in cultivate_keywords if kw in content)
        if cultivate_count >= 2:
            recommendations.append("【桥段库 → 角色修炼】检测到修炼场景，可使用「角色修炼」桥段模板。")
            recommendations.append("【元素库 → 修炼体系】可参考「修炼体系」元素丰富设定。")
        
        # 登场/退场检测
        entrance_keywords = ["登场", "出场", "降临", "出现", "走来", "降临", "离开", "消失", "死去"]
        entrance_count = sum(1 for kw in entrance_keywords if kw in content)
        if entrance_count >= 2:
            recommendations.append("【桥段库 → 角色登场/退场】检测到角色出场或离场，可使用对应桥段模板。")
        
        # 对话检测
        dialogue_count = content.count('"') + content.count('"') + content.count('「') + content.count('」')
        if dialogue_count >= 10:
            recommendations.append("【对话推演】本章对话较多，可使用「情景对话推演」继续扩展对话。")
        
        # 描写场景检测
        scene_keywords = ["山", "水", "城", "宫", "殿", "天空", "大地", "森林", "海洋", "星空"]
        scene_count = sum(1 for kw in scene_keywords if kw in content)
        if scene_count >= 3:
            recommendations.append("【描写库 → 自然景观/建筑描写】检测到场景描写，可使用「自然景观」或「建筑描写」增强氛围。")
        
        # 角色外貌检测
        appearance_keywords = ["容貌", "美貌", "英俊", "潇洒", "绝美", "倾城", "飘逸", "冷峻"]
        appearance_count = sum(1 for kw in appearance_keywords if kw in content)
        if appearance_count >= 2:
            recommendations.append("【描写库 → 人物外貌】检测到外貌描写，可使用「人物外貌」描写模板。")
        
        # 追逐检测
        chase_keywords = ["追", "逃", "跑", "奔", "闪", "躲", "避"]
        chase_count = sum(1 for kw in chase_keywords if kw in content)
        if chase_count >= 3:
            recommendations.append("【桥段库 → 角色追逐】检测到追逐场景，可使用「角色追逐」桥段模板。")
        
        # 风格建议
        word_count = len(content)
        if word_count < 1500:
            recommendations.append("【风格转换】本章较短（{0}字），可使用「AI扩写」或「风格转换」丰富内容。".format(word_count))
        elif word_count > 5000:
            recommendations.append("【智能改编】本章较长（{0}字），可使用「AI简写」精简或「智能改编」优化节奏。".format(word_count))
        
        # 热点改编建议
        if "搞笑" in content or "幽默" in content or "哈哈" in content:
            recommendations.append("【热点改编】本章有幽默元素，可使用「热点改编→冷笑话」增加笑点。")
        
        if not recommendations:
            recommendations.append("本章暂无明显特征，可尝试使用以下工具：")
            recommendations.append("• 风格转换 - 调整文风")
            recommendations.append("• AI润色 - 优化语言表达")
            recommendations.append("• 描写库 - 增加细节描写")
            recommendations.append("• 桥段库 - 添加经典桥段")
        
        return "\n\n".join(recommendations)
    
    def _analyze_current_chapter(self):
        """分析当前编辑区的章节"""
        content = self.content_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("提示", "编辑区没有内容")
            return
        
        recommendations = self._analyze_chapter_content(content)
        self.ch_recommend.config(state=tk.NORMAL)
        self.ch_recommend.delete("1.0", tk.END)
        self.ch_recommend.insert("1.0", recommendations)
        self.ch_recommend.config(state=tk.DISABLED)
    
    def _load_chapter_to_editor(self):
        """加载选中章节到编辑区"""
        sel = self.ch_file_listbox.curselection()
        if not sel or not self.current_novel_dir:
            messagebox.showinfo("提示", "请先选择一个章节文件")
            return
        
        chapters_dir = self.current_novel_dir / "chapters"
        chapter_files = sorted(chapters_dir.glob("chapter_*.txt"))
        idx = sel[0]
        
        if idx < len(chapter_files):
            filepath = chapter_files[idx]
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                self.content_text.delete("1.0", tk.END)
                self.content_text.insert("1.0", content)
                self.word_count_var.set(str(len(content)))
                
                # 更新当前章节号
                chapter_num = int(filepath.stem.split("_")[1])
                self.current_chapter = chapter_num
                self.chapter_title_var.set(f"第{chapter_num}章")
                
                self._log(f"已加载第{chapter_num}章到编辑区")
            except Exception as e:
                self._log(f"加载章节失败: {e}")
    
    def _display_review(self, review_json: str):
        """显示审校结果（主线程调用）"""
        self.review_text.delete("1.0", tk.END)
        self.review_text.insert("1.0", review_json)
        self.notebook.select(2)
    
    def _check_ready(self) -> bool:
        """检查是否就绪"""
        if not self.ai_client.is_configured():
            messagebox.showwarning("提示", "请先配置AI API（设置 → AI配置）")
            return False
        if not self.current_novel_dir:
            messagebox.showwarning("提示", "请先创建或打开小说")
            return False
        return True
    
    def _get_meta(self) -> dict:
        """获取小说元数据"""
        with open(self.current_novel_dir / "meta.json", 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _show_help(self):
        """显示帮助"""
        help_text = """AI自动写小说系统 v2.0 使用说明

═══ 1. 配置AI模型 ═══
菜单 → 设置 → AI模型

支持的AI后端：
- Ollama（本地免费）: 默认 http://localhost:11434
- OpenAI: 需要API密钥
- DeepSeek: 需要API密钥
- Claude: 需要API密钥
- 自定义API: 兼容OpenAI格式

点击"检测Ollama"可自动发现本地模型。

═══ 2. 配置文生图（可选）═══
菜单 → 设置 → 文生图

支持的后端：
- ComfyUI: 默认端口 8188
- SD WebUI API: 默认端口 7860
- Disabled: 不使用文生图

勾选"自动检测名场面"后，每章生成完毕会自动
检测适合插图的场景并提醒生成图片。

═══ 3. 新建小说 ═══
点击"新建小说"，填写：
- 标题、类型、核心概念
- 目标章节数

═══ 4. 创作流程 ═══
分步模式：
  1. 生成世界观 → 创建世界设定
  2. 生成角色 → 创建角色档案
  3. 生成大纲 → 规划故事结构
  4. 生成下一章 → 逐章创作
  5. 审校当前章 → 检查质量

自动模式：
  点击"自动创作"一键完成全流程

═══ 5. 长上下文记忆 ═══
系统自动维护：
- 世界观设定
- 角色档案
- 全局故事摘要
- 最近5章摘要
- 关键词索引

确保长篇小说的连贯性。

═══ 6. 导出 ═══
点击"导出全文"生成TXT文件
"""
        dialog = tk.Toplevel(self.root)
        dialog.title("使用说明")
        dialog.geometry("500x600")
        text = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, font=("微软雅黑", 11))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text.insert("1.0", help_text)
        text.config(state=tk.DISABLED)
    
    def _show_about(self):
        """显示关于"""
        messagebox.showinfo("关于", "AI自动写小说系统 v2.0\n\n功能：\n- AI API（Ollama/OpenAI/DeepSeek/Claude）\n- 长上下文记忆\n- 智能体自动创作\n- 文生图（ComfyUI/SD WebUI）\n- 名场面自动检测")
    
    def _on_close(self):
        """关闭应用"""
        if messagebox.askyesno("确认", "确定要退出吗？"):
            self.root.destroy()
    
    def run(self):
        """运行应用"""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()


# ==================== 入口 ====================

if __name__ == "__main__":
    app = NovelWriterApp()
    app.run()
