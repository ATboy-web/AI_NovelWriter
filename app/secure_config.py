"""
安全配置管理模块 - 加密存储敏感配置

密钥托管策略：
- Windows：使用 DPAPI（CryptProtectData）保护 Fernet 密钥，密钥不落明文磁盘
- 其他平台：回退到文件权限（chmod 0600）
"""

import json
import os
import base64
import sys
import ctypes
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)


class _WindowsDPAPI:
    """Windows 数据保护 API（DPAPI）封装。

    使用当前用户登录凭据加密数据，即使文件被复制到其他机器/账户也无法解密。
    """

    _AVAILABLE = False

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.c_uint32),
            ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    def __init__(self):
        self._available = False
        if sys.platform != "win32":
            return
        try:
            self._crypt32 = ctypes.windll.crypt32
            self._kernel32 = ctypes.windll.kernel32
            self._crypt32.CryptProtectData.argtypes = [
                ctypes.POINTER(self._DATA_BLOB), ctypes.c_wchar_p,
                ctypes.POINTER(self._DATA_BLOB), ctypes.c_void_p,
                ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(self._DATA_BLOB),
            ]
            self._crypt32.CryptUnprotectData.argtypes = [
                ctypes.POINTER(self._DATA_BLOB), ctypes.POINTER(ctypes.c_wchar_p),
                ctypes.POINTER(self._DATA_BLOB), ctypes.c_void_p,
                ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(self._DATA_BLOB),
            ]
            self._kernel32.LocalFree.argtypes = [ctypes.c_void_p]
            self._available = True
        except (AttributeError, OSError):
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def _to_blob(self, data: bytes):
        buf = ctypes.create_string_buffer(data, len(data))
        return self._DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))

    def protect(self, data: bytes) -> bytes:
        """加密数据，返回 DPAPI 密文"""
        in_blob = self._to_blob(data)
        out_blob = self._DATA_BLOB()
        if not self._crypt32.CryptProtectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            raise OSError("DPAPI CryptProtectData 失败")
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            self._kernel32.LocalFree(out_blob.pbData)

    def unprotect(self, data: bytes) -> bytes:
        """解密 DPAPI 密文，返回明文"""
        in_blob = self._to_blob(data)
        out_blob = self._DATA_BLOB()
        desc = ctypes.c_wchar_p()
        if not self._crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), ctypes.byref(desc), None, None, None, 0, ctypes.byref(out_blob)
        ):
            raise OSError("DPAPI CryptUnprotectData 失败")
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            self._kernel32.LocalFree(out_blob.pbData)


class SecureConfig:
    """安全配置管理器 - 使用Fernet加密保护敏感数据"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path.home() / ".ai_novel_writer"
        self.config_dir.mkdir(exist_ok=True)
        self.config_file = self.config_dir / "config.json"
        self.key_file = self.config_dir / ".config_key"
        self._dpapi = _WindowsDPAPI()
        self.fernet = self._init_encryption()
        self.config = self._load()
    
    def _init_encryption(self) -> Fernet:
        """初始化加密引擎，密钥通过 DPAPI 或文件权限保护"""
        if self.key_file.exists():
            raw = self.key_file.read_bytes()
            key = self._protect_key_load(raw)
        else:
            key = Fernet.generate_key()
            self.key_file.write_bytes(self._protect_key_save(key))
            try:
                os.chmod(self.key_file, 0o600)
            except (OSError, AttributeError):
                pass
        return Fernet(key)
    
    def _protect_key_save(self, key: bytes) -> bytes:
        """保存密钥前进行保护（Windows 用 DPAPI 加密）"""
        if self._dpapi.available:
            return self._dpapi.protect(key)
        return key  # 非 Windows 平台回退为明文（靠文件权限 0600）
    
    def _protect_key_load(self, raw: bytes) -> bytes:
        """读取密钥时进行解保护"""
        if self._dpapi.available:
            try:
                return self._dpapi.unprotect(raw)
            except OSError as e:
                logger.error(f"DPAPI 解保护密钥失败，密钥可能来自其他账户/机器: {e}")
                raise
        return raw
    
    def _encrypt(self, value: str) -> str:
        """加密字符串"""
        if not value:
            return ""
        return self.fernet.encrypt(value.encode()).decode()
    
    def _decrypt(self, encrypted_value: str) -> str:
        """解密字符串。仅接受 Fernet 加密值（gAAAAA 前缀），
        拒绝并清空未加密的明文值（移除降级路径，防止明文敏感数据被静默接受）。
        """
        if not encrypted_value:
            return ""
        if not encrypted_value.startswith('gAAAAA'):
            # 未加密的旧格式/被篡改值：不再降级接受明文，返回空并强制重新加密
            logger.warning("检测到未加密的敏感字段，已清空。请重新保存配置以加密。")
            return ""
        try:
            return self.fernet.decrypt(encrypted_value.encode()).decode()
        except Exception as e:
            logger.error(f"解密失败，密钥可能已损坏: {e}")
            return ""
    
    def _load(self) -> dict:
        """加载配置"""
        if not self.config_file.exists():
            return self._default_config()
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 解密敏感字段
            sensitive_fields = ['api_key', 'img_api_key', 'secret_key']
            for field in sensitive_fields:
                if field in config and config[field]:
                    config[field] = self._decrypt(config[field])
            
            return config
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return self._default_config()
    
    def _default_config(self) -> dict:
        """默认配置"""
        return {
            "api_provider": "ollama",
            "api_key": "",
            "api_base": "http://localhost:11434",
            "model": "qwen2.5:14b",
            "max_tokens": 4096,
            "temperature": 0.8,
            "context_window": 32000,
            "auto_save": True,
            "theme": "light",
            "adult_content": False,
            "edge_content": False,
            "img_provider": "comfyui",
            "img_api_base": "http://127.0.0.1:8188",
            "img_api_key": "",
            "img_model": "sd_xl_base_1.0.safetensors",
            "img_width": 1024,
            "img_height": 1024,
            "auto_detect_scene": True,
        }
    
    def save(self):
        """保存配置（加密敏感字段）"""
        config_to_save = self.config.copy()
        
        # 加密敏感字段
        sensitive_fields = ['api_key', 'img_api_key', 'secret_key']
        for field in sensitive_fields:
            if field in config_to_save and config_to_save[field]:
                config_to_save[field] = self._encrypt(config_to_save[field])
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config_to_save, f, indent=2, ensure_ascii=False)
        
        # 设置文件权限（仅当前用户可读写）
        try:
            os.chmod(self.config_file, 0o600)
        except (OSError, AttributeError):
            pass
    
    def get(self, key: str, default=None):
        """获取配置值"""
        return self.config.get(key, default)
    
    def set(self, key: str, value):
        """设置配置值"""
        self.config[key] = value
        self.save()
    
    def get_api_key(self) -> str:
        """获取API密钥"""
        return self.get("api_key", "")
    
    def set_api_key(self, api_key: str):
        """设置API密钥"""
        self.set("api_key", api_key)


# 全局实例
_secure_config: Optional[SecureConfig] = None


def get_secure_config() -> SecureConfig:
    """获取安全配置管理器单例"""
    global _secure_config
    if _secure_config is None:
        _secure_config = SecureConfig()
    return _secure_config
