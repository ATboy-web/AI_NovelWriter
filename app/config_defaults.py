"""配置默认值与字段名单（**纯常量**，不依赖任何其它 app 模块）。

## 为什么单独成一个模块

`config` 与 `secure_config` 原本互相 import：`secure_config` 在模块级取这 4 个常量，
`config` 又在函数内延迟导入 `SecureConfig` —— 形成 latent 环（当前不炸，
但只要有人把那条延迟导入提到模块级，立刻变 `ImportError`）。

把"纯数据"下移到本模块后，依赖变成单向：

    config ──▶ config_defaults ◀── secure_config
       └──────────────▶ secure_config（延迟，方向不变）

`config` 仍**原样 re-export** 这些名字，`from app.config import DEFAULT_CONFIG`
等既有写法全部保持可用。

## 改动这里要连带检查

- `config.py` 的 re-export 列表
- `secure_config` 的字段名单（`SENSITIVE_CONFIG_FIELDS` 决定哪些键加密落盘）
"""

from __future__ import annotations

#: 默认配置（单一定义，避免重复）
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
    # ❗ 历史审计曾移除两个**声明了却完全没有对应功能**的键：
    #   - `auto_save`：章节保存是无条件执行的（`chapter_ui` 里没有读这个键做分支），
    #     所以它既不能开也不能关。**保持移除**。
    #   - `theme`：v3.4（2026-11-20 UI 改版）起**重新启用且真实接线** ——
    #     设置对话框「高级」页有主题选择控件，`theme_switch.switch_theme`
    #     据此换肤并持久化；取值见 `app/theme_system.py`（cyberpunk/wasteland/mechapunk）。
    #     旧文件里的遗留值（如 "light"）由 normalize_theme 回落默认，不会报错。
    # 配置读取用 `.get(key, default)`，旧配置文件里多出来的键会被忽略。
    "theme": "cyberpunk",
    "adult_content": False,
    "edge_content": False,
    "img_provider": "comfyui",
    "img_api_base": "http://127.0.0.1:8188",
    "img_model": "sd_xl_base_1.0.safetensors",
    "img_width": 1024,
    "img_height": 1024,
    "auto_detect_scene": True,
}

#: 需要加密落盘的字段（单一来源：SecureConfig 与 config 共用，避免两处定义漂移）
SENSITIVE_CONFIG_FIELDS = ("api_key", "img_api_key", "secret_key")

#: 加密密钥在配置文件中的存放键（多 Profile 结构）
AI_KEYS_FIELD = "ai_keys"

#: 未指定档案时使用的默认档案名
DEFAULT_PROFILE_NAME = "default"

__all__ = [
    "AI_KEYS_FIELD",
    "DEFAULT_CONFIG",
    "DEFAULT_PROFILE_NAME",
    "SENSITIVE_CONFIG_FIELDS",
]
