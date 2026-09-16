"""
安全配置管理模块 - 加密存储敏感配置

密钥托管策略：
- Windows：使用 DPAPI（CryptProtectData）保护 Fernet 密钥，密钥不落明文磁盘
- 其他平台：回退到文件权限（chmod 0600）

与 `AppConfig` 的分工（v3 明确划分，此前是「两个类共写一个文件」的隐患）：

- `config.json` 里**非敏感**的键归 AppConfig 所有，本模块只透传不覆盖；
- 敏感字段（api_key / img_api_key / secret_key）与多 Profile 密钥容器
  `ai_keys` 归本模块独有，永远以本实例的内存值为准；
- 其余键在保存时**以磁盘现状为基准**，只回写「本次显式 set() 过的键」。

最后一条是本次修复的核心：旧实现对整个内存快照做全量回写，而内存快照是
进程启动时读的。于是「用户先改主题、再改 API Key」这个极常见的顺序，
第二次保存会把主题连同 `ai.profiles` 一起退回旧值 —— 静默丢配置。
"""

import ctypes
import json
import logging
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from cryptography.fernet import Fernet

from .config import AI_KEYS_FIELD, DEFAULT_CONFIG, DEFAULT_PROFILE_NAME
from .storage import atomic_write_json

logger = logging.getLogger(__name__)

#: 需要加密落盘的字段（与 AppConfig 共用同一定义）
_SENSITIVE_FIELDS = ("api_key", "img_api_key", "secret_key")


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
                ctypes.POINTER(self._DATA_BLOB),
                ctypes.c_wchar_p,
                ctypes.POINTER(self._DATA_BLOB),
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.POINTER(self._DATA_BLOB),
            ]
            self._crypt32.CryptUnprotectData.argtypes = [
                ctypes.POINTER(self._DATA_BLOB),
                ctypes.POINTER(ctypes.c_wchar_p),
                ctypes.POINTER(self._DATA_BLOB),
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.POINTER(self._DATA_BLOB),
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
        if not self._crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
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
        # M7: set()/save()/get() 会被多处并发调用，实例内加锁
        self._lock = threading.RLock()
        # L7: 记录「读盘失败」与「解密失败」，两者都不得在下次 save 时
        # 把用户既有配置当作默认值/空值覆盖掉
        self._load_failed = False
        self._undecryptable: dict = {}
        #: 各 Profile 中解不开的密钥密文，save 时原样写回
        self._undecryptable_ai_keys: Dict[str, str] = {}
        #: 本实例**显式 set() 过**的键。只有这些键才允许在保存时覆盖磁盘值，
        #: 其余键一律以磁盘现状为准（否则陈旧快照会回退别的组件的改动）
        self._dirty: set = set()
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
        if not encrypted_value.startswith("gAAAAA"):
            # 未加密的旧格式/被篡改值：不再降级接受明文，返回空并强制重新加密
            logger.warning("检测到未加密的敏感字段，已清空。请重新保存配置以加密。")
            return ""
        try:
            return self.fernet.decrypt(encrypted_value.encode()).decode()
        except Exception as e:
            logger.error(f"解密失败，密钥可能已损坏: {e}")
            return ""

    def _load(self) -> dict:
        """加载配置。

        L7: 读盘失败**不再静默返回默认值**。旧实现把解析异常吞掉后返回
        `_default_config()`，此后任何一次 `set()` 都会触发 `save()`，把默认值
        连同已加密的 `api_key` 一起写回磁盘 —— 用户的密钥与全部设置被永久抹掉。
        现在改为：先把无法解析的原文件留档（原始字节保留，可人工恢复），
        再标记 `_load_failed`，让 `save()` 能如实告警而不是假装一切正常。
        """
        if not self.config_file.exists():
            return self._default_config()

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            if not isinstance(config, dict):
                raise ValueError(f"配置根节点不是对象（{type(config).__name__}）")
        except Exception as e:
            self._load_failed = True
            archived = self._archive_corrupt_config()
            logger.error(
                f"加载配置失败: {e}；原文件已留档为 "
                f"{archived.name if archived else '（留档失败）'}。本次运行使用默认配置，"
                "无法解密字段的原始密文会被保留、不会被写空。"
            )
            return self._default_config()

        # 解密敏感字段
        for field in _SENSITIVE_FIELDS:
            if field in config and config[field]:
                ciphertext = config[field]
                plain = self._decrypt(ciphertext)
                if plain == "" and str(ciphertext).startswith("gAAAAA"):
                    # 解密失败（Fernet 密钥不匹配/密文损坏）：记下原文，
                    # save() 时原样写回，避免「空值覆盖已加密密钥」
                    self._undecryptable[field] = ciphertext
                config[field] = plain

        # v3: 多 Profile 密钥容器（同样是密文，逐项解密）
        ai_keys = config.get(AI_KEYS_FIELD)
        if isinstance(ai_keys, dict):
            decrypted: Dict[str, str] = {}
            for name, ciphertext in ai_keys.items():
                plain = self._decrypt(ciphertext) if isinstance(ciphertext, str) else ""
                if plain == "" and isinstance(ciphertext, str) and ciphertext.startswith("gAAAAA"):
                    self._undecryptable_ai_keys[str(name)] = ciphertext
                decrypted[str(name)] = plain
            config[AI_KEYS_FIELD] = decrypted

        return config

    def _archive_corrupt_config(self) -> Optional[Path]:
        """把无法解析的配置文件留档，供人工恢复；返回留档路径。"""
        try:
            if not self.config_file.exists():
                return None
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base = f"{self.config_file.stem}.corrupt-{stamp}"
            dst = self.config_file.with_name(f"{base}.json")
            seq = 1
            while dst.exists():
                dst = self.config_file.with_name(f"{base}_{seq}.json")
                seq += 1
            dst.write_bytes(self.config_file.read_bytes())
            logger.warning(f"已留档损坏的配置文件: {dst.name}")
            return dst
        except OSError as e:
            logger.error(f"留档损坏配置文件失败: {e}")
            return None

    def _default_config(self) -> dict:
        """默认配置。

        复用 `AppConfig.DEFAULT_CONFIG` 作为单一来源 —— 旧实现把 17 个默认值
        在这里抄了第二份，两边一旦漂移就会出现「首启有值、恢复默认后没值」。
        """
        return {**DEFAULT_CONFIG, "img_api_key": ""}

    def save(self) -> bool:
        """保存配置（加密敏感字段）。

        保存策略（v3 重写）：

        ============================  ==========================
        键                            取值来源
        ============================  ==========================
        敏感字段 / `ai_keys` 容器     **内存**（本模块独占）
        本次 `set()` 过的键           **内存**（`self._dirty`）
        其余一切键                    **磁盘现状**（不碰）
        ============================  ==========================

        旧实现是「整份内存快照全量回写」，而内存快照取自进程启动时刻，
        于是**同一次会话里**先改主题、再改 API Key，第二次保存就会把主题
        退回旧值，并连带抹掉 AppConfig 刚写入的 `ai.profiles`。
        现在的写法是先读盘再按键覆盖，两个组件可以安全地共用一个文件。

        另外：
          - 用 `atomic_write_json`（临时文件 + `os.replace`），
            `mode=0o600` 在替换前施加，不存在"权限尚且宽松"的窗口期；
          - 内存为空但原始密文仍在手上的字段，**原样写回密文**；
          - 读盘曾失败时**拒绝写入** —— 宁可不保存，也不用残缺内容覆盖
            磁盘上唯一一份可能还能人工救回的数据。
        """
        with self._lock:
            if self._load_failed:
                logger.error(
                    "配置文件此前读取失败，本次保存已跳过：磁盘上的原始内容"
                    "（已留档为 config.corrupt-*.json）不得被残缺内存覆盖。"
                )
                return False

            config_to_save = dict(self._read_raw() or {})

            # 1) 本实例显式改过的键：以内存为准
            for key in self._dirty:
                if key in self.config:
                    config_to_save[key] = self.config[key]

            # 2) 敏感字段：以内存为准，并明确清掉磁盘上的明文残留
            for field in _SENSITIVE_FIELDS:
                if self.config.get(field):
                    config_to_save[field] = self._encrypt(self.config[field])
                elif field in self._undecryptable:
                    # 无法解密 → 保留原密文（不做"空值覆盖"）
                    config_to_save[field] = self._undecryptable[field]
                else:
                    config_to_save[field] = ""

            # 3) ai_keys 容器：以内存为准（逐项加密）
            ai_keys = self.config.get(AI_KEYS_FIELD)
            if isinstance(ai_keys, dict):
                config_to_save[AI_KEYS_FIELD] = self._encrypt_ai_keys(ai_keys)
            else:
                config_to_save.pop(AI_KEYS_FIELD, None)

            atomic_write_json(self.config_file, config_to_save, indent=2, mode=0o600)
            self._dirty.clear()
            return True

    def _encrypt_ai_keys(self, mapping: dict) -> dict:
        """加密各 Profile 的密钥；解不开的密文原样保留（与单字段同策略）。"""
        result: Dict[str, str] = {}
        for name, value in mapping.items():
            name = str(name)
            if isinstance(value, str) and value:
                result[name] = self._encrypt(value)
            elif name in self._undecryptable_ai_keys:
                result[name] = self._undecryptable_ai_keys[name]
            else:
                result[name] = ""
        return result

    def _read_raw(self) -> Optional[dict]:
        """读磁盘原始内容（不解密）。失败返回 None，绝不抛异常。"""
        try:
            if not self.config_file.exists():
                return None
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def get(self, key: str, default=None):
        """获取配置值"""
        with self._lock:
            return self.config.get(key, default)

    def set(self, key: str, value):
        """设置配置值"""
        with self._lock:
            self.config[key] = value
            self._dirty.add(key)
            self.save()

    def get_api_key(self) -> str:
        """获取API密钥"""
        return self.get("api_key", "")

    def set_api_key(self, api_key: str):
        """设置API密钥"""
        self.set("api_key", api_key)

    # ======================================================== 多 Profile 密钥

    def get_ai_key(self, profile: str = DEFAULT_PROFILE_NAME) -> str:
        """取某 Profile 的明文密钥。

        默认 Profile 直接复用旧的顶层 `api_key` 字段 —— 老用户的密钥
        不需要任何迁移动作就能继续用（这是刻意保留的兼容路径）。
        """
        profile = str(profile or DEFAULT_PROFILE_NAME)
        with self._lock:
            if profile == DEFAULT_PROFILE_NAME:
                return self.get("api_key", "") or ""
            keys = self.config.get(AI_KEYS_FIELD)
            if not isinstance(keys, dict):
                return ""
            value = keys.get(profile)
            return value if isinstance(value, str) else ""

    def set_ai_key(self, profile: str, value: str) -> None:
        """写入某 Profile 的密钥（落盘为密文）。"""
        profile = str(profile or DEFAULT_PROFILE_NAME)
        value = value or ""
        with self._lock:
            if profile == DEFAULT_PROFILE_NAME:
                self.set("api_key", value)
                return
            keys = self.config.get(AI_KEYS_FIELD)
            keys = dict(keys) if isinstance(keys, dict) else {}
            keys[profile] = value
            self._undecryptable_ai_keys.pop(profile, None)
            self.config[AI_KEYS_FIELD] = keys
            self.save()

    def delete_ai_key(self, profile: str) -> None:
        """删除某 Profile 的密钥（删除 Profile 时调用）。"""
        profile = str(profile or DEFAULT_PROFILE_NAME)
        with self._lock:
            if profile == DEFAULT_PROFILE_NAME:
                self.set("api_key", "")
                return
            keys = self.config.get(AI_KEYS_FIELD)
            if not isinstance(keys, dict) or profile not in keys:
                return
            keys = dict(keys)
            del keys[profile]
            self._undecryptable_ai_keys.pop(profile, None)
            self.config[AI_KEYS_FIELD] = keys
            self.save()

    def rename_ai_key(self, old: str, new: str) -> None:
        """Profile 改名时把密钥一起搬过去。"""
        old = str(old or DEFAULT_PROFILE_NAME)
        new = str(new or DEFAULT_PROFILE_NAME)
        if not new or old == new:
            return
        with self._lock:
            if old == DEFAULT_PROFILE_NAME:
                self.set_ai_key(new, self.get_ai_key(DEFAULT_PROFILE_NAME))
                self.set_ai_key(DEFAULT_PROFILE_NAME, "")
                return
            keys = self.config.get(AI_KEYS_FIELD)
            keys = dict(keys) if isinstance(keys, dict) else {}
            if old not in keys:
                return
            keys[new] = keys.pop(old)
            if old in self._undecryptable_ai_keys:
                self._undecryptable_ai_keys[new] = self._undecryptable_ai_keys.pop(old)
            self.config[AI_KEYS_FIELD] = keys
            self.save()

    def has_ai_key(self, profile: str = DEFAULT_PROFILE_NAME) -> bool:
        return bool(self.get_ai_key(profile))

    def ai_key_profiles(self) -> List[str]:
        """已单独存放过密钥的 Profile 名（不含默认 Profile）。"""
        with self._lock:
            keys = self.config.get(AI_KEYS_FIELD)
            if not isinstance(keys, dict):
                return []
            return [str(name) for name, value in keys.items() if value]


# 全局实例
_secure_config: Optional[SecureConfig] = None
# M7: 单例构造必须加锁 —— 旧实现无锁，首次并发调用可能各构造一个实例，
# 而每个实例在密钥文件不存在时会各自 `Fernet.generate_key()`，
# 只有一个写入磁盘成功，另一个实例用它自己的密钥加密数据后永远解不开。
_secure_config_lock = threading.Lock()


def get_secure_config() -> SecureConfig:
    """获取安全配置管理器单例（线程安全）"""
    global _secure_config
    if _secure_config is None:
        with _secure_config_lock:
            if _secure_config is None:
                _secure_config = SecureConfig()
    return _secure_config
