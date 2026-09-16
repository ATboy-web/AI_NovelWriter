"""
配置管理模块 - 管理应用配置

v3 的 `config.json` 结构::

    {
      "api_provider": "ollama",     # ← 顶层扁平键：活跃 Profile 的镜像（向后兼容）
      "model": "qwen2.5:14b",
      "temperature": 0.8,
      "theme": "light",             # ← 与 AI 无关的普通键，照旧扁平存放

      "ai": {                       # ← v3 新增：AI 连接档案
        "schema_version": 2,
        "active_profile": "default",
        "profiles": {
          "default": {"api_provider": "ollama", "model": "qwen2.5:14b", ...},
          "work":    {"api_provider": "deepseek", "model": "deepseek-v4-flash", ...}
        }
      }
    }

三个设计约束（都是踩过坑之后定下来的）：

1. **扁平键必须继续可用。** v2 里有 50+ 处 `config.get("model")` /
   `config.get("api_provider")` 调用点。多 Profile 不能要求它们全部改造，
   否则一旦漏改就会出现「界面显示 A、实际请求 B」。所以活跃 Profile 的字段
   会被**镜像**到顶层同名扁平键，`get()` 先看 Profile、再回落到扁平键。

2. **API Key 永不进入 Profile。** Profile 里只有连接参数；密钥交给
   `SecureConfig` 加密保管：默认 Profile 复用旧的顶层 `api_key` 字段
   （因此老用户的密钥零迁移、零风险），其余 Profile 存于加密容器
   `ai_keys.<profile>`。这样 profile 段落整体可以安全地明文落盘，
   而密钥依旧只有密文。

3. **迁移必须幂等且可回滚。** 第一次落盘前会把旧文件另存为
   `config.pre-v3-profiles-<时间戳>.json`；顶层扁平键**不删除**，
   所以把文件换成旧版本程序也能继续跑。
"""

import copy
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import atomic_write_json

logger = logging.getLogger(__name__)

# 默认配置（单一定义，避免重复）
DEFAULT_CONFIG = {
    # ---- AI 连接参数（会进 Profile）----
    "api_provider": "ollama",
    "api_key": "",
    "api_base": "http://localhost:11434",
    "model": "qwen2.5:14b",
    "max_tokens": 4096,
    "temperature": 0.8,
    "context_window": 32000,
    "thinking_enabled": True,
    "reasoning_effort": "high",
    "timeout": 600.0,
    "connect_timeout": 10.0,
    "max_retries": 3,
    "balance_url": "",
    "balance_total_path": "",
    "balance_currency_path": "",
    # ---- 非 AI 参数（扁平存放）----
    "auto_save": True,
    "theme": "light",
    "adult_content": False,
    "edge_content": False,
    "img_provider": "comfyui",
    "img_api_base": "http://127.0.0.1:8188",
    "img_model": "sd_xl_base_1.0.safetensors",
    "img_width": 1024,
    "img_height": 1024,
    "auto_detect_scene": True,
}

#: 需要加密落盘的字段（单一来源：SecureConfig 与本模块共用，避免两处定义漂移）
SENSITIVE_CONFIG_FIELDS = ("api_key", "img_api_key", "secret_key")

# ============================================================ 多 Profile 常量

PROFILES_SECTION = "ai"
PROFILES_SCHEMA_VERSION = 2
AI_KEYS_FIELD = "ai_keys"
DEFAULT_PROFILE_NAME = "default"

#: 属于「AI 连接档案」的字段。
#: 这些字段的权威副本在 `ai.profiles.<name>`，顶层扁平键只是活跃 Profile 的镜像。
AI_PROFILE_FIELDS = (
    "api_provider",
    "api_base",
    "model",
    "max_tokens",
    "temperature",
    "context_window",
    "thinking_enabled",
    "reasoning_effort",
    "timeout",
    "connect_timeout",
    "max_retries",
    "balance_url",
    "balance_total_path",
    "balance_currency_path",
)

_AI_PROFILE_FIELD_SET = frozenset(AI_PROFILE_FIELDS)

#: Profile 字段的默认值（单一来源：直接取自 DEFAULT_CONFIG，避免两处定义漂移）
AI_PROFILE_DEFAULTS: Dict[str, Any] = {field: DEFAULT_CONFIG[field] for field in AI_PROFILE_FIELDS}

#: 供设置页生成表单用的中文标签
AI_PROFILE_LABELS: Dict[str, str] = {
    "api_provider": "AI 服务商",
    "api_base": "API 地址",
    "model": "模型名称",
    "max_tokens": "最大输出 token",
    "temperature": "温度",
    "context_window": "上下文窗口",
    "thinking_enabled": "深度思考模式",
    "reasoning_effort": "思考强度",
    "timeout": "读取超时（秒）",
    "connect_timeout": "连接超时（秒）",
    "max_retries": "瞬时故障重试次数",
    "balance_url": "余额接口地址（可选）",
    "balance_total_path": "余额字段路径（可选）",
    "balance_currency_path": "币种字段路径（可选）",
}

#: 各字段的取值范围，设置页与 `set()` 共用一套（避免界面能填、后端拒绝）
PROFILE_FIELD_RANGES: Dict[str, tuple] = {
    "max_tokens": (1, 2_000_000),
    "temperature": (0.0, 2.0),
    "context_window": (512, 8_000_000),
    "timeout": (5.0, 7200.0),
    "connect_timeout": (1.0, 300.0),
    "max_retries": (0, 10),
}

#: 思考强度的合法取值（各家 API 的并集；registry 里的 adapter 会各自裁剪）
REASONING_EFFORTS = ("minimal", "low", "medium", "high", "max")

_PROFILE_NAME_BAD_CHARS = set('\\/:*?"<>|')


def _safe_coerce(key: str, value: Any) -> Any:
    """清洗单字段取值；无法清洗时退回默认值（**不抛异常**）。

    这个函数只用在「迁移/加载」路径上 —— 磁盘上可能是任意历史脏值
    （`"0.8"` 字符串、`None`、超范围数字）。启动阶段绝不能因为一个坏字段
    就打不开程序，所以这里一律降级到默认值并记 warning。
    """
    try:
        return _coerce_profile_field(key, value)
    except (TypeError, ValueError) as exc:
        fallback = AI_PROFILE_DEFAULTS.get(key)
        logger.warning(
            "配置字段 %s 取值非法（%r：%s），已回退为默认值 %r",
            key,
            value,
            exc,
            fallback,
        )
        return fallback


def _coerce_profile_field(key: str, value: Any) -> Any:
    """校验并转换 Profile 字段值，非法时抛 `ValueError`。

    与 `_safe_coerce` 的分工：**用户输入**走这里（快速失败，界面能提示），
    **磁盘读入**走 `_safe_coerce`（宽容降级，程序能启动）。
    """
    default = AI_PROFILE_DEFAULTS.get(key)
    lo_hi = PROFILE_FIELD_RANGES.get(key)

    if key == "thinking_enabled":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("1", "true", "yes", "on", "启用"):
                return True
            if lowered in ("0", "false", "no", "off", "禁用", ""):
                return False
        if isinstance(value, int):
            return bool(value)
        raise ValueError("需要布尔值（true/false）")

    if key == "reasoning_effort":
        if not isinstance(value, str) or not value.strip():
            raise ValueError("需要非空的思考强度，如 high / medium / low")
        return value.strip().lower()

    if key in ("balance_url", "balance_total_path", "balance_currency_path"):
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("需要字符串")
        return value.strip()

    # 其余全部是数值字段（api_provider / api_base / model 单独处理）
    if key in ("api_provider", "api_base", "model"):
        if value is None:
            return "" if key != "api_provider" else default
        if not isinstance(value, str):
            raise ValueError("需要字符串")
        text = value.strip()
        if key == "api_provider" and not text:
            return default
        return text

    if isinstance(value, bool) or value is None:
        raise ValueError("需要数字")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"需要数字，得到 {value!r}") from None
    if key in ("max_tokens", "context_window", "max_retries"):
        number = int(number)
    if lo_hi is not None and not (lo_hi[0] <= number <= lo_hi[1]):
        raise ValueError(f"需在 {lo_hi[0]} ~ {lo_hi[1]} 之间，得到 {number}")
    return number


class AppConfig:
    """应用配置（敏感字段加密存储 + AI 连接参数多 Profile）"""

    # 敏感字段列表 - 这些字段使用加密存储
    SENSITIVE_FIELDS = list(SENSITIVE_CONFIG_FIELDS)

    def __init__(self):
        self.config_dir = Path.home() / ".ai_novel_writer"
        self.config_dir.mkdir(exist_ok=True)
        self.config_file = self.config_dir / "config.json"
        self.novels_dir = self.config_dir / "novels"
        self.novels_dir.mkdir(exist_ok=True)

        # M7-style: set()/get()/save() 会被 UI 线程与创作线程并发调用
        self._lock = threading.RLock()
        # 迁移落盘前是否还需写一份「迁移前」备份（只在首次需要写入时做一次）
        self._migration_backup_pending = False

        # 先初始化安全配置（用于敏感字段加解密）
        self._secure_config = None
        try:
            from .secure_config import SecureConfig

            self._secure_config = SecureConfig()
        except Exception:
            self._secure_config = None

        self.config = self._load()

    # ------------------------------------------------------------ 加载 / 迁移

    def _load(self) -> dict:
        file_existed = self.config_file.exists()
        if file_existed:
            with open(self.config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
        else:
            config = DEFAULT_CONFIG.copy()

        # 解密敏感字段（M3 修复：单一加密数据源，读取时解密）
        if self._secure_config:
            for field in self.SENSITIVE_FIELDS:
                if field in config and config[field]:
                    decrypted = self._secure_config._decrypt(config[field])
                    if decrypted:
                        config[field] = decrypted
                    else:
                        # 无法解密的残留值（明文或损坏），清空
                        config[field] = ""

        # v3: 建立/补齐 ai.profiles；返回 True 表示结构发生了变化
        migrated = self._normalize_profiles(config)
        self._mirror_active_profile(config)
        # 只有「磁盘上原本就有旧格式文件」才需要留档 —— 全新安装没东西可备份
        self._migration_backup_pending = migrated and file_existed
        if migrated:
            logger.info(
                "配置已升级为多 Profile 结构（schema_version=%s，active_profile=%s）",
                PROFILES_SCHEMA_VERSION,
                config[PROFILES_SECTION]["active_profile"],
            )
        return config

    def _normalize_profiles(self, config: dict) -> bool:
        """就地补齐 `ai.profiles`，返回是否发生了结构变化。

        幂等：当结构已是当前 schema 且字段齐全时直接返回 False，
        不会让每次启动都触发一次落盘。
        """
        section = config.get(PROFILES_SECTION)
        if self._profiles_are_current(section):
            return False

        profiles: Dict[str, dict] = {}
        if isinstance(section, dict) and isinstance(section.get("profiles"), dict):
            # 已有手写/半成品结构：保留用户数据，只补缺项
            for name, prof in section["profiles"].items():
                profiles[str(name)] = dict(prof) if isinstance(prof, dict) else {}

        if DEFAULT_PROFILE_NAME not in profiles:
            profiles[DEFAULT_PROFILE_NAME] = {}

        # 迁移核心：用顶层扁平键填充 default Profile
        default_profile = profiles[DEFAULT_PROFILE_NAME]
        for field in AI_PROFILE_FIELDS:
            if field not in default_profile:
                default_profile[field] = _safe_coerce(field, config.get(field, AI_PROFILE_DEFAULTS[field]))

        # 其它 Profile 也补齐缺项（以 default 为模板），保证每个 Profile 自洽
        for name, prof in profiles.items():
            for field in AI_PROFILE_FIELDS:
                if field not in prof:
                    prof[field] = default_profile[field]

        # 把历史脏值统一洗一遍（旧版本可能存过字符串数字）
        for prof in profiles.values():
            for field in AI_PROFILE_FIELDS:
                prof[field] = _safe_coerce(field, prof[field])

        active = section.get("active_profile") if isinstance(section, dict) else None
        if active not in profiles:
            active = DEFAULT_PROFILE_NAME

        config[PROFILES_SECTION] = {
            "schema_version": PROFILES_SCHEMA_VERSION,
            "active_profile": active,
            "profiles": profiles,
        }
        return True

    @staticmethod
    def _profiles_are_current(section: Any) -> bool:
        """结构是否已是当前 schema 且无需补齐。"""
        if not isinstance(section, dict):
            return False
        if section.get("schema_version") != PROFILES_SCHEMA_VERSION:
            return False
        profiles = section.get("profiles")
        if not isinstance(profiles, dict) or DEFAULT_PROFILE_NAME not in profiles:
            return False
        if section.get("active_profile") not in profiles:
            return False
        for prof in profiles.values():
            if not isinstance(prof, dict):
                return False
            if any(field not in prof for field in AI_PROFILE_FIELDS):
                return False
        return True

    def _mirror_active_profile(self, config: dict) -> None:
        """把活跃 Profile 的字段镜像到顶层扁平键（兼容 v2 调用点）。"""
        prof = self._active_profile_dict(config)
        for field in AI_PROFILE_FIELDS:
            if field in prof:
                config[field] = prof[field]

    # ------------------------------------------------------------ 读写

    def save(self):
        with self._lock:
            data = copy.deepcopy(self.config)

            # `ai_keys`（各 Profile 的加密密钥容器）由 SecureConfig 独占写权限。
            # 这里的自校验非常必要：AppConfig 与 SecureConfig 同写一个文件，
            # 若直接回写自己的陈旧快照，会把刚存进去的新 Profile 密钥抹掉。
            on_disk = self._read_raw()
            if isinstance(on_disk, dict) and isinstance(on_disk.get(AI_KEYS_FIELD), dict):
                data[AI_KEYS_FIELD] = on_disk[AI_KEYS_FIELD]
                self.config[AI_KEYS_FIELD] = on_disk[AI_KEYS_FIELD]

            # 加密敏感字段后再落盘（M3 修复：明文不写入 config.json）
            if self._secure_config:
                for field in self.SENSITIVE_FIELDS:
                    if data.get(field):
                        data[field] = self._secure_config._encrypt(data[field])

            if self._migration_backup_pending:
                self._write_migration_backup()

            atomic_write_json(self.config_file, data, mode=0o600)
            self._migration_backup_pending = False

    def _read_raw(self) -> Optional[dict]:
        """读取磁盘上的原始 JSON（不解密）。失败返回 None，绝不抛异常。"""
        try:
            if not self.config_file.exists():
                return None
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def _write_migration_backup(self) -> None:
        """迁移前留档（可回滚）。已存在同名文件时**不覆盖**，一次迁移一份。"""
        try:
            if not self.config_file.exists():
                return
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dst = self.config_file.with_name(f"config.pre-v3-profiles-{stamp}.json")
            if dst.exists():
                return
            dst.write_bytes(self.config_file.read_bytes())
            logger.info("迁移前配置已留档: %s（可据此回滚到单 Profile 格式）", dst.name)
        except OSError as exc:
            logger.warning("留档迁移前配置失败（不影响本次迁移）: %s", exc)

    # ------------------------------------------------------------ Profile 视图

    @property
    def active_profile(self) -> str:
        section = self.config.get(PROFILES_SECTION)
        if isinstance(section, dict):
            name = section.get("active_profile")
            if name:
                return str(name)
        return DEFAULT_PROFILE_NAME

    def _active_profile_dict(self, config: Optional[dict] = None) -> dict:
        """返回活跃 Profile 的**可变**字典（缺失时按默认值创建）。"""
        target = self.config if config is None else config
        section = target.get(PROFILES_SECTION)
        if not isinstance(section, dict):
            section = {
                "schema_version": PROFILES_SCHEMA_VERSION,
                "active_profile": DEFAULT_PROFILE_NAME,
                "profiles": {DEFAULT_PROFILE_NAME: dict(AI_PROFILE_DEFAULTS)},
            }
            target[PROFILES_SECTION] = section
        profiles = section.setdefault("profiles", {})
        name = section.get("active_profile") or DEFAULT_PROFILE_NAME
        prof = profiles.get(name)
        if not isinstance(prof, dict):
            prof = dict(AI_PROFILE_DEFAULTS)
            profiles[name] = prof
        # 数值/布尔字段缺项时补默认值（不覆盖已有值）
        for field, fallback in AI_PROFILE_DEFAULTS.items():
            prof.setdefault(field, fallback)
        return prof

    def profile_names(self) -> List[str]:
        """全部 Profile 名（default 恒排第一，其余按字典序）。"""
        section = self.config.get(PROFILES_SECTION)
        names = []
        if isinstance(section, dict) and isinstance(section.get("profiles"), dict):
            names = [str(n) for n in section["profiles"].keys()]
        if DEFAULT_PROFILE_NAME not in names:
            names.insert(0, DEFAULT_PROFILE_NAME)
        else:
            names.remove(DEFAULT_PROFILE_NAME)
            names.insert(0, DEFAULT_PROFILE_NAME)
        return names

    def profiles(self) -> Dict[str, dict]:
        """全部 Profile 的深拷贝（供界面展示，避免外部直接改内存）。"""
        section = self.config.get(PROFILES_SECTION)
        if not isinstance(section, dict) or not isinstance(section.get("profiles"), dict):
            return {DEFAULT_PROFILE_NAME: dict(AI_PROFILE_DEFAULTS)}
        return copy.deepcopy(section["profiles"])

    def profile_snapshot(self, name: str = "") -> dict:
        """某 Profile 的只读摘要，供设置页/关于页展示。"""
        name = name or self.active_profile
        prof = self.profiles().get(name) or dict(AI_PROFILE_DEFAULTS)
        return {
            "name": name,
            "is_active": name == self.active_profile,
            "has_api_key": self.profile_has_key(name),
            "api_key_masked": self.mask_api_key(self.profile_api_key(name)),
            **prof,
        }

    @staticmethod
    def mask_api_key(value: str) -> str:
        """密钥只显示首尾片段。用于界面回显，避免截图/日志泄露整串密钥。"""
        value = value or ""
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}{'*' * 6}{value[-4:]}"

    # ------------------------------------------------------------ Profile 操作

    @staticmethod
    def _validate_profile_name(name: str) -> str:
        name = (name or "").strip()
        if not name:
            raise ValueError("Profile 名称不能为空")
        if len(name) > 40:
            raise ValueError("Profile 名称不能超过 40 个字符")
        if any(ch in _PROFILE_NAME_BAD_CHARS for ch in name):
            raise ValueError('Profile 名称不能包含 \\ / : * ? " < > |')
        if any(ch in name for ch in "\r\n\t"):
            raise ValueError("Profile 名称不能包含换行或制表符")
        return name

    def switch_profile(self, name: str) -> str:
        """切换活跃 Profile，并把它的字段镜像到顶层扁平键。

        这是「多 Profile」与「v2 扁平读法」之间的同步点：切换之后，
        所有 `config.get("model")` 之类的旧调用点立刻拿到新 Profile 的值。
        """
        name = self._validate_profile_name(name)
        with self._lock:
            section = self.config.get(PROFILES_SECTION)
            if not isinstance(section, dict) or name not in (section.get("profiles") or {}):
                raise ValueError(f"Profile 不存在：{name}")
            section["active_profile"] = name
            self._mirror_active_profile(self.config)
            self.save()
        return name

    def create_profile(self, name: str, copy_from: str = "", activate: bool = False) -> str:
        """新建 Profile。`copy_from` 为 ``""`` 时以默认值起手（推荐，避免抄错端点）。"""
        name = self._validate_profile_name(name)
        with self._lock:
            section = self.config.get(PROFILES_SECTION)
            if not isinstance(section, dict):
                self._normalize_profiles(self.config)
                section = self.config[PROFILES_SECTION]
            profiles = section["profiles"]
            if name in profiles:
                raise ValueError(f"Profile 已存在：{name}")
            if copy_from:
                source = profiles.get(copy_from)
                if not isinstance(source, dict):
                    raise ValueError(f"要复制的 Profile 不存在：{copy_from}")
                profiles[name] = copy.deepcopy(source)
            else:
                profiles[name] = dict(AI_PROFILE_DEFAULTS)
            if activate:
                section["active_profile"] = name
                self._mirror_active_profile(self.config)
            self.save()
        return name

    def delete_profile(self, name: str) -> None:
        """删除 Profile（含其加密密钥）。不允许删掉最后一个或正在使用的那一个。"""
        name = self._validate_profile_name(name)
        with self._lock:
            section = self.config.get(PROFILES_SECTION)
            profiles = (section or {}).get("profiles") or {}
            if name not in profiles:
                raise ValueError(f"Profile 不存在：{name}")
            if len(profiles) <= 1:
                raise ValueError("至少要保留一个 Profile")
            if name == self.active_profile:
                raise ValueError("不能删除正在使用的 Profile，请先切换到其它 Profile")
            del profiles[name]
            if self._secure_config:
                self._secure_config.delete_ai_key(name)
            self.save()

    def rename_profile(self, old: str, new: str) -> str:
        """重命名 Profile（一并搬走它的加密密钥）。"""
        old = self._validate_profile_name(old)
        new = self._validate_profile_name(new)
        with self._lock:
            section = self.config.get(PROFILES_SECTION)
            profiles = (section or {}).get("profiles") or {}
            if old not in profiles:
                raise ValueError(f"Profile 不存在：{old}")
            if new in profiles:
                raise ValueError(f"Profile 已存在：{new}")
            profiles[new] = profiles.pop(old)
            if section.get("active_profile") == old:
                section["active_profile"] = new
                self._mirror_active_profile(self.config)
            if self._secure_config:
                self._secure_config.rename_ai_key(old, new)
            self.save()
        return new

    # ------------------------------------------------------------ 密钥（按 Profile）

    def profile_api_key(self, name: str = "") -> str:
        """取某 Profile 的明文密钥（仅供界面回显，不要写日志）。"""
        name = name or self.active_profile
        if self._secure_config:
            value = self._secure_config.get_ai_key(name)
            if value:
                return value
        if name == DEFAULT_PROFILE_NAME:
            # 默认 Profile 与旧的顶层 `api_key` 同源
            return self.config.get("api_key", "") or ""
        # 非默认 Profile 没有独立密钥时，**绝不借用**其它 Profile 的密钥 ——
        # 否则用户会看到"切换了 Profile 却还在用旧密钥"，且钱花在错账号上
        return ""

    def profile_has_key(self, name: str = "") -> bool:
        return bool(self.profile_api_key(name))

    def _set_active_api_key(self, value: str) -> None:
        name = self.active_profile
        if self._secure_config:
            self._secure_config.set_ai_key(name, value)
        elif name != DEFAULT_PROFILE_NAME:
            raise RuntimeError("加密组件不可用，拒绝以明文保存非默认 Profile 的密钥")
        if name == DEFAULT_PROFILE_NAME:
            self.config["api_key"] = value

    # ------------------------------------------------------------ 读写（扁平键兼容）

    def get(self, key: str, default=None):
        with self._lock:
            if key == "api_key":
                value = self.profile_api_key()
                if value:
                    return value
                return default if default is not None else ""

            if key in _AI_PROFILE_FIELD_SET:
                prof = self._active_profile_dict()
                if key in prof:
                    return prof[key]
                if key in self.config:
                    return self.config[key]
                return AI_PROFILE_DEFAULTS.get(key, default)

            if self._secure_config and key in self.SENSITIVE_FIELDS:
                value = self._secure_config.get(key)
                if value:
                    return value
            return self.config.get(key, default)

    def set(self, key: str, value):
        with self._lock:
            if key == "api_key":
                self._set_active_api_key(value)
                self.save()
                return

            if key in self.SENSITIVE_FIELDS:
                if self._secure_config:
                    self._secure_config.set(key, value)
                # 同步内存中的值
                self.config[key] = value
                self.save()
                return

            if key in _AI_PROFILE_FIELD_SET:
                coerced = _coerce_profile_field(key, value)
                self._active_profile_dict()[key] = coerced
                # 镜像到顶层扁平键，保证 v2 的读法立刻看到新值
                self.config[key] = coerced
            else:
                self.config[key] = value
            self.save()

    # ------------------------------------------------------------ 便捷读法

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(float(self.get(key, default)))
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """布尔读取。

        注意 `getattr(mock, ..., False)` 一类的写法对 MagicMock 会返回真值子
        Mock，所以这里只认真正的布尔/数字/常见字符串。
        """
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return default

    # ------------------------------------------------------------ 迁移落盘

    def ensure_profiles_persisted(self) -> bool:
        """把内存中的多 Profile 结构写盘一次（应用启动时调用）。

        设计成显式方法而不是在 `__init__` 里落盘，是为了让「构造配置对象」
        保持只读 —— 单测里 `AppConfig()` 会指向真实用户目录，构造函数写盘
        会污染开发机上的真实配置。
        """
        with self._lock:
            if not self._migration_backup_pending:
                return False
            self.save()
            return True
