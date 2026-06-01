"""
模型管理器
负责管理本地模型和云端API的加载、卸载和调用
"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import json
import os
from pathlib import Path

from .config import settings

class ModelStatus(str, Enum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"

class ModelInfo:
    """模型信息类"""
    def __init__(self, model_type: str, model_name: str, status: ModelStatus = ModelStatus.UNLOADED):
        self.model_type = model_type
        self.model_name = model_name
        self.status = status
        self.loaded_at: Optional[datetime] = None
        self.last_used: Optional[datetime] = None
        self.usage_count: int = 0
        self.error_message: Optional[str] = None
        self.metadata: Dict[str, Any] = {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_type": self.model_type,
            "model_name": self.model_name,
            "status": self.status.value,
            "loaded_at": self.loaded_at.isoformat() if self.loaded_at else None,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "usage_count": self.usage_count,
            "error_message": self.error_message,
            "metadata": self.metadata
        }

class ModelManager:
    """模型管理器"""
    
    def __init__(self):
        self.models: Dict[str, ModelInfo] = {}
        self.local_model = None
        self.openai_client = None
        self.claude_client = None
        self._lock = asyncio.Lock()
        
    async def initialize(self):
        """初始化模型管理器"""
        print("初始化模型管理器...")
        
        # 初始化云端客户端
        await self._init_cloud_clients()
        
        # 扫描本地模型
        await self._scan_local_models()
        
        print(f"模型管理器初始化完成，发现 {len(self.models)} 个模型")
    
    async def _init_cloud_clients(self):
        """初始化云端客户端"""
        try:
            # OpenAI客户端
            if settings.OPENAI_API_KEY:
                import openai
                self.openai_client = openai.AsyncOpenAI(
                    api_key=settings.OPENAI_API_KEY,
                    base_url=settings.OPENAI_API_BASE
                )
                print("OpenAI客户端初始化成功")
            
            # Claude客户端
            if settings.CLAUDE_API_KEY:
                import anthropic
                self.claude_client = anthropic.AsyncAnthropic(
                    api_key=settings.CLAUDE_API_KEY
                )
                print("Claude客户端初始化成功")
                
        except ImportError as e:
            print(f"云端客户端初始化失败: {e}")
        except Exception as e:
            print(f"云端客户端初始化错误: {e}")
    
    async def _scan_local_models(self):
        """扫描本地模型目录"""
        model_path = Path(settings.LOCAL_MODEL_PATH)
        if not model_path.exists():
            print(f"本地模型目录不存在: {model_path}")
            return
        
        # 扫描模型文件
        model_extensions = ['.gguf', '.ggml', '.bin', '.pt', '.pth']
        for model_file in model_path.rglob('*'):
            if model_file.suffix.lower() in model_extensions:
                model_name = model_file.stem
                model_key = f"local_{model_name}"
                
                if model_key not in self.models:
                    self.models[model_key] = ModelInfo(
                        model_type="local",
                        model_name=model_name,
                        status=ModelStatus.UNLOADED
                    )
                    self.models[model_key].metadata = {
                        "file_path": str(model_file),
                        "file_size": model_file.stat().st_size,
                        "file_extension": model_file.suffix
                    }
                    print(f"发现本地模型: {model_name}")
    
    async def get_available_models(self) -> List[str]:
        """获取所有可用模型名称"""
        available = []
        
        # 本地模型
        for key, model in self.models.items():
            if model.model_type == "local":
                available.append(key)
        
        # 云端模型
        if self.openai_client:
            available.extend(["openai_gpt-4", "openai_gpt-3.5-turbo"])
        if self.claude_client:
            available.extend(["claude_claude-3-sonnet", "claude_claude-3-haiku"])
        
        return available
    
    async def get_all_models(self) -> List[Dict[str, Any]]:
        """获取所有模型详细信息"""
        models_info = []
        
        for key, model in self.models.items():
            models_info.append(model.to_dict())
        
        # 添加云端模型信息
        if self.openai_client:
            models_info.append({
                "model_type": "openai",
                "model_name": "gpt-4",
                "status": "available",
                "metadata": {"provider": "OpenAI"}
            })
            models_info.append({
                "model_type": "openai",
                "model_name": "gpt-3.5-turbo",
                "status": "available",
                "metadata": {"provider": "OpenAI"}
            })
        
        if self.claude_client:
            models_info.append({
                "model_type": "claude",
                "model_name": "claude-3-sonnet-20240229",
                "status": "available",
                "metadata": {"provider": "Anthropic"}
            })
            models_info.append({
                "model_type": "claude",
                "model_name": "claude-3-haiku-20240307",
                "status": "available",
                "metadata": {"provider": "Anthropic"}
            })
        
        return models_info
    
    async def load_model(self, model_type: str, model_name: Optional[str] = None) -> Dict[str, Any]:
        """加载指定模型"""
        async with self._lock:
            if model_type == "local":
                return await self._load_local_model(model_name)
            elif model_type == "openai":
                return await self._load_openai_model(model_name)
            elif model_type == "claude":
                return await self._load_claude_model(model_name)
            else:
                raise ValueError(f"不支持的模型类型: {model_type}")
    
    async def _load_local_model(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """加载本地模型"""
        try:
            # 查找模型
            model_key = None
            if model_name:
                model_key = f"local_{model_name}"
            else:
                # 查找第一个本地模型
                for key, model in self.models.items():
                    if model.model_type == "local":
                        model_key = key
                        break
            
            if not model_key or model_key not in self.models:
                raise ValueError(f"未找到本地模型: {model_name}")
            
            model_info = self.models[model_key]
            
            # 检查是否已加载
            if model_info.status == ModelStatus.LOADED:
                return {"message": "模型已加载", "model_key": model_key}
            
            # 更新状态
            model_info.status = ModelStatus.LOADING
            
            # 尝试导入llama_cpp
            try:
                from llama_cpp import Llama
                
                # 加载模型
                model_path = model_info.metadata.get("file_path")
                if not model_path:
                    raise ValueError("模型文件路径不存在")
                
                self.local_model = Llama(
                    model_path=model_path,
                    n_ctx=settings.LOCAL_MODEL_CONTEXT_SIZE,
                    n_gpu_layers=settings.LOCAL_MODEL_GPU_LAYERS,
                    verbose=False
                )
                
                # 更新状态
                model_info.status = ModelStatus.LOADED
                model_info.loaded_at = datetime.now()
                model_info.error_message = None
                
                return {
                    "message": "本地模型加载成功",
                    "model_key": model_key,
                    "model_path": model_path
                }
                
            except ImportError:
                raise ValueError("llama_cpp未安装，无法加载本地模型")
            except Exception as e:
                model_info.status = ModelStatus.ERROR
                model_info.error_message = str(e)
                raise ValueError(f"本地模型加载失败: {e}")
                
        except Exception as e:
            raise ValueError(f"加载本地模型失败: {e}")
    
    async def _load_openai_model(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """加载OpenAI模型"""
        if not self.openai_client:
            raise ValueError("OpenAI客户端未初始化，请检查API密钥配置")
        
        # OpenAI模型不需要预加载，只需验证连接
        try:
            # 简单测试连接
            models = await self.openai_client.models.list()
            return {
                "message": "OpenAI模型可用",
                "available_models": [m.id for m in models.data[:5]]
            }
        except Exception as e:
            raise ValueError(f"OpenAI连接失败: {e}")
    
    async def _load_claude_model(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """加载Claude模型"""
        if not self.claude_client:
            raise ValueError("Claude客户端未初始化，请检查API密钥配置")
        
        # Claude模型不需要预加载，只需验证连接
        try:
            # 简单测试连接
            message = await self.claude_client.messages.create(
                model=model_name or "claude-3-sonnet-20240229",
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}]
            )
            return {
                "message": "Claude模型可用",
                "model": model_name or "claude-3-sonnet-20240229"
            }
        except Exception as e:
            raise ValueError(f"Claude连接失败: {e}")
    
    async def unload_model(self, model_type: str, model_name: Optional[str] = None) -> Dict[str, Any]:
        """卸载指定模型"""
        async with self._lock:
            if model_type == "local":
                return await self._unload_local_model(model_name)
            elif model_type in ["openai", "claude"]:
                return {"message": f"{model_type}模型无需卸载"}
            else:
                raise ValueError(f"不支持的模型类型: {model_type}")
    
    async def _unload_local_model(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """卸载本地模型"""
        try:
            # 查找模型
            model_key = None
            if model_name:
                model_key = f"local_{model_name}"
            else:
                # 查找第一个已加载的本地模型
                for key, model in self.models.items():
                    if model.model_type == "local" and model.status == ModelStatus.LOADED:
                        model_key = key
                        break
            
            if not model_key or model_key not in self.models:
                return {"message": "没有需要卸载的本地模型"}
            
            model_info = self.models[model_key]
            
            # 卸载模型
            if self.local_model:
                del self.local_model
                self.local_model = None
            
            # 更新状态
            model_info.status = ModelStatus.UNLOADED
            model_info.loaded_at = None
            
            return {
                "message": "本地模型卸载成功",
                "model_key": model_key
            }
            
        except Exception as e:
            raise ValueError(f"卸载本地模型失败: {e}")
    
    async def unload_all_models(self) -> Dict[str, Any]:
        """卸载所有模型"""
        unloaded = []
        
        # 卸载本地模型
        if self.local_model:
            del self.local_model
            self.local_model = None
            unloaded.append("local_model")
        
        # 更新所有模型状态
        for key, model in self.models.items():
            if model.status == ModelStatus.LOADED:
                model.status = ModelStatus.UNLOADED
                model.loaded_at = None
                unloaded.append(key)
        
        return {
            "message": "所有模型已卸载",
            "unloaded_models": unloaded
        }
    
    async def get_model_status(self, model_type: str, model_name: Optional[str] = None) -> Dict[str, Any]:
        """获取模型状态"""
        if model_type == "local":
            # 查找本地模型
            model_key = None
            if model_name:
                model_key = f"local_{model_name}"
            else:
                for key, model in self.models.items():
                    if model.model_type == "local":
                        model_key = key
                        break
            
            if model_key and model_key in self.models:
                return self.models[model_key].to_dict()
            else:
                return {"status": "not_found"}
        
        elif model_type == "openai":
            return {
                "status": "available" if self.openai_client else "not_configured",
                "client_initialized": self.openai_client is not None
            }
        
        elif model_type == "claude":
            return {
                "status": "available" if self.claude_client else "not_configured",
                "client_initialized": self.claude_client is not None
            }
        
        else:
            raise ValueError(f"不支持的模型类型: {model_type}")
    
    async def load_default_models(self):
        """加载默认模型"""
        try:
            # 尝试加载默认本地模型
            default_model = settings.LOCAL_MODEL_NAME
            if default_model:
                try:
                    await self.load_model("local", default_model)
                    print(f"默认本地模型加载成功: {default_model}")
                except Exception as e:
                    print(f"默认本地模型加载失败: {e}")
            
            # 检查云端模型可用性
            if self.openai_client:
                try:
                    await self.load_model("openai")
                    print("OpenAI模型可用")
                except Exception as e:
                    print(f"OpenAI模型检查失败: {e}")
            
            if self.claude_client:
                try:
                    await self.load_model("claude")
                    print("Claude模型可用")
                except Exception as e:
                    print(f"Claude模型检查失败: {e}")
                    
        except Exception as e:
            print(f"加载默认模型失败: {e}")
    
    def get_local_model(self):
        """获取本地模型实例"""
        return self.local_model
    
    def get_openai_client(self):
        """获取OpenAI客户端"""
        return self.openai_client
    
    def get_claude_client(self):
        """获取Claude客户端"""
        return self.claude_client
    
    async def update_model_usage(self, model_type: str, model_name: Optional[str] = None):
        """更新模型使用统计"""
        model_key = None
        if model_type == "local":
            if model_name:
                model_key = f"local_{model_name}"
            else:
                for key, model in self.models.items():
                    if model.model_type == "local" and model.status == ModelStatus.LOADED:
                        model_key = key
                        break
        
        if model_key and model_key in self.models:
            model_info = self.models[model_key]
            model_info.usage_count += 1
            model_info.last_used = datetime.now()