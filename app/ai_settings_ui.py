"""设置页「AI 模型」页签（v3 P2-5）。

从 `lifecycle_ui._show_settings` 里抽出来单独成模块，原因有三：

1. 原实现把服务商下拉、模型预设、API 地址预设**手工维护了第二份清单**
   （修 P5）—— 注册表里加了 mimo / kimi，设置页却没有，用户选不到，
   只能选 "custom" 再手填地址，等于注册表白做。
   现在下拉、地址、模型候选**全部由注册表生成**。
2. 原实现有**两个温度输入框**且绑到同一个变量（修 P11），
   用户改上面那个、程序读的是下面那个，表现为"改了没用"。
3. 多 Profile、超时、重试、思考模式、余额查询这些新能力需要一个
   能放得下的表单，塞进 600 行的 `_show_settings` 里只会让它更难维护。

本模块只负责**界面与接线**：取值走向 `AppConfig` 的校验（非法输入当场报错），
「测试连接」走 `AIClient.probe_connection`，「余额」走 `AIClient.query_balance`，
URL 预览由 `ProviderSpec.resolved_url` 直接算 —— 三者都不会另写一套请求逻辑。
"""

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Tuple

from app import UIStyle, dialogs

from .config import AI_PROFILE_LABELS, REASONING_EFFORTS
from .providers import get_spec, specs_for_ui

__all__ = ["AISettingsMixin", "provider_choices", "models_for_provider"]


# ============================================================ 纯函数（可单测）


def provider_choices() -> Tuple[List[str], Dict[str, str]]:
    """返回 (下拉显示的条目, 条目→provider key)。

    显示名用注册表里的 `name`（如 "DeepSeek"、"通义千问 (DashScope)"），
    这样用户在界面上看到的是服务名而不是内部 key。
    """
    labels: List[str] = []
    mapping: Dict[str, str] = {}
    for spec in specs_for_ui():
        label = spec["name"]
        if label in mapping:  # 极端情况下重名，追加 key 消歧
            label = f"{label} [{spec['key']}]"
        labels.append(label)
        mapping[label] = spec["key"]
    return labels, mapping


def models_for_provider(provider_key: str) -> List[str]:
    """某 provider 的模型候选（来自注册表，不再本地维护一份）。"""
    for spec in specs_for_ui():
        if spec["key"] == provider_key:
            candidates = list(spec["models"])
            if spec["default_model"] and spec["default_model"] not in candidates:
                candidates.insert(0, spec["default_model"])
            return candidates or ["custom-model"]
    return ["custom-model"]


def describe_capabilities(caps: dict, note: str = "") -> str:
    """把能力字典拼成一句人话，放在表单下方做说明。"""
    parts = []
    parts.append("支持流式输出" if caps.get("streaming") else "不支持流式输出")
    parts.append("支持深度思考" if caps.get("thinking") else "不支持深度思考参数")
    parts.append("返回 token 用量" if caps.get("usage") else "不返回 token 用量（将按估算记账）")
    parts.append("有余额接口" if caps.get("balance") else "无余额接口")
    if caps.get("local"):
        parts.append("本地部署，无计费")
    text = "；".join(parts)
    return f"{text}。{note}" if note else text


class _AIForm:
    """AI 页签的控件与变量载体。

    原实现靠一个 440 行闭包共享 30 多个控件/变量；拆成分区方法后需要一个
    显式载体在方法之间传递。这里只收纳属性，不含任何逻辑。
    """

    cfg: Any
    dialog: Any
    labels: List[str]
    key_of: Dict[str, str]
    # Profile
    active_var: Any
    prof_combo: Any
    key_state: Any
    # 连接
    provider_var: Any
    provider_combo: Any
    base_entry: Any
    base_hint: Any
    key_entry: Any
    # 模型与采样
    model_var: Any
    model_combo: Any
    local_var: Any
    local_row: Any
    max_tokens_var: Any
    temp_var: Any
    ctx_var: Any
    # 深度思考
    think_var: Any
    think_check: Any
    effort_var: Any
    effort_combo: Any
    think_note: Any
    # 网络与重试
    timeout_var: Any
    connect_var: Any
    retries_var: Any
    # 余额
    bal_state: Any
    bal_url_entry: Any
    bal_total_entry: Any
    bal_cur_entry: Any
    # 动作区
    result_var: Any
    result_label: Any


# ============================================================ 界面 Mixin


class AISettingsMixin:
    """设置页 AI 页签的构建与保存。"""

    # ------------------------------------------------------------ 入口

    def _build_ai_settings_tab(self, parent, dialog) -> Callable[[], None]:
        """构建 AI 页签，返回保存回调 `save() -> None`。

        P1-4：原实现是 440 行、圈复杂度 44 的巨石函数（全仓最高），
        所有控件靠闭包共享，改一处要在整段里上下翻找，也几乎无法单测。
        现按表单分区拆成独立方法，控件与变量统一挂在 `_AIForm` 上传递。
        **分区构建顺序、各控件的 pack 参数与回调语义逐字保持不变**。
        """
        f = _AIForm()
        f.cfg = self.config
        f.dialog = dialog
        f.labels, f.key_of = provider_choices()

        self._ai_build_profile_section(f, parent)
        self._ai_build_connection_section(f, parent)
        self._ai_build_model_section(f, parent)
        self._ai_build_thinking_section(f, parent)
        self._ai_build_network_section(f, parent)
        self._ai_build_balance_section(f, parent)
        self._ai_build_action_section(f, parent)

        f.provider_combo.bind("<<ComboboxSelected>>", lambda *_: self._ai_on_provider_change(f))

        # 初始化：先把活跃 Profile 灌进表单（内含 provider 下拉与能力联动）
        f.prof_combo.bind("<<ComboboxSelected>>", lambda *_: self._ai_switch_profile(f))
        self._ai_refresh_key_state(f)

        return lambda: self._ai_save(f)

    # ------------------------------------------------------------ 分区构建

    def _ai_build_profile_section(self, f: "_AIForm", parent) -> None:
        cfg = f.cfg
        prof_box = ttk.LabelFrame(parent, text="配置档案（Profile）")
        prof_box.pack(fill=tk.X, padx=20, pady=(10, 6))

        prof_row = tk.Frame(prof_box)
        prof_row.pack(fill=tk.X, padx=8, pady=6)

        f.active_var = tk.StringVar(value=cfg.active_profile)
        f.prof_combo = ttk.Combobox(
            prof_row,
            textvariable=f.active_var,
            values=cfg.profile_names(),
            state="readonly",
            width=18,
        )
        f.prof_combo.pack(side=tk.LEFT)

        f.key_state = tk.StringVar()
        key_label = tk.Label(prof_row, textvariable=f.key_state, fg="#666")
        key_label.pack(side=tk.LEFT, padx=10)

        for text, command in (
            ("切换", lambda: self._ai_switch_profile(f)),
            ("新建", lambda: self._ai_create_profile(f)),
            ("重命名", lambda: self._ai_rename_profile(f)),
            ("删除", lambda: self._ai_delete_profile(f)),
        ):
            ttk.Button(prof_row, text=text, command=command, width=6).pack(side=tk.LEFT, padx=2)

    def _ai_build_connection_section(self, f: "_AIForm", parent) -> None:
        conn_box = ttk.LabelFrame(parent, text="连接")
        conn_box.pack(fill=tk.X, padx=20, pady=6)

        _label(conn_box, "AI 服务商")
        f.provider_var = tk.StringVar()
        f.provider_combo = ttk.Combobox(
            conn_box,
            textvariable=f.provider_var,
            values=f.labels,
            state="readonly",
            width=42,
        )
        f.provider_combo.pack(anchor=tk.W, padx=20, pady=2)

        _label(conn_box, "API 地址")
        f.base_entry = ttk.Entry(conn_box, width=52)
        f.base_entry.pack(anchor=tk.W, padx=20, pady=2)
        f.base_hint = tk.Label(conn_box, text="", fg="#666", anchor=tk.W, justify=tk.LEFT)
        f.base_hint.pack(anchor=tk.W, padx=20)

        _label(conn_box, "API 密钥")
        key_row = tk.Frame(conn_box)
        key_row.pack(anchor=tk.W, padx=20, pady=2)
        f.key_entry = ttk.Entry(key_row, width=44, show="*")
        f.key_entry.pack(side=tk.LEFT)
        show_key = tk.BooleanVar(value=False)

        def _toggle_key():
            f.key_entry.configure(show="" if show_key.get() else "*")

        ttk.Checkbutton(key_row, text="显示", variable=show_key, command=_toggle_key).pack(side=tk.LEFT, padx=6)
        tk.Label(conn_box, text="密钥加密后保存，不明文落盘；每个档案各存各的。", fg="#666", anchor=tk.W).pack(
            anchor=tk.W, padx=20
        )

    def _ai_build_model_section(self, f: "_AIForm", parent) -> None:
        model_box = ttk.LabelFrame(parent, text="模型与采样")
        model_box.pack(fill=tk.X, padx=20, pady=6)

        _label(model_box, "模型名称")
        f.model_var = tk.StringVar()
        f.model_combo = ttk.Combobox(model_box, textvariable=f.model_var, width=42)
        f.model_combo.pack(anchor=tk.W, padx=20, pady=2)

        # ---- 本地模型：从服务实际拉取"已安装"的模型
        # 为什么需要：`AIClient.get_ollama_models()` 早就实现了，但**全仓零界面调用**
        # ⇒ 用户只能手打模型名，填错了要到生成时才失败。模型候选原先来自注册表里的
        # **静态建议表**（`_OLLAMA_MODELS`），未必与这台机器上真实装了哪些模型一致。
        # 显示与否由能力位 `local` 决定（`can_list_local_models`），
        # 而不是 `provider == "ollama"` —— 以后接 llama.cpp / vLLM 只要声明 local 即可复用。
        f.local_var = tk.StringVar(value="")
        f.local_row = tk.Frame(model_box)
        f.local_row.pack(anchor=tk.W, padx=20, pady=(0, 2))

        def _refresh_local_models():
            f.local_var.set("正在读取本地模型…")

            def _after(models):
                if isinstance(models, dict):  # `_run_in_background` 的异常形状
                    f.local_var.set(f"读取失败：{models.get('reason', '未知错误')}")
                    return
                names = [m.name for m in (models or [])]
                if not names:
                    f.local_var.set("未读到模型（服务未启动，或尚未拉取任何模型）")
                    return
                # 只更新候选列表，**不覆盖用户已填的模型名** —— 覆盖会把配置改掉
                f.model_combo["values"] = names
                f.local_var.set(f"已读到 {len(names)} 个本地模型，可下拉选择")

            self._run_in_background(_list_local_models, _after, f.dialog)

        def _list_local_models():
            return self.ai_client.list_local_models()

        def _check_local_service():
            f.local_var.set("正在检测本地服务…")

            def _after(result):
                if isinstance(result, dict) and "reason" in result:
                    f.local_var.set(f"检测失败：{result.get('reason')}")
                    return
                ok, message = result if isinstance(result, tuple) else (False, str(result))
                f.local_var.set(("✅ " if ok else "❌ ") + str(message))

            self._run_in_background(self.ai_client.check_local_service, _after, f.dialog)

        local_refresh_btn = ttk.Button(f.local_row, text="刷新本地模型", command=_refresh_local_models)
        local_refresh_btn.pack(side=tk.LEFT)
        local_check_btn = ttk.Button(f.local_row, text="检测本地服务", command=_check_local_service)
        local_check_btn.pack(side=tk.LEFT, padx=6)
        tk.Label(f.local_row, textvariable=f.local_var, fg="#666", anchor=tk.W).pack(side=tk.LEFT, padx=6)

        _label(model_box, "最大输出 token")
        f.max_tokens_var = tk.StringVar()
        ttk.Entry(model_box, textvariable=f.max_tokens_var, width=12).pack(anchor=tk.W, padx=20, pady=2)

        _label(model_box, "温度（0 ~ 2，越高越发散）")
        f.temp_var = tk.StringVar()
        ttk.Spinbox(model_box, from_=0, to=2, increment=0.1, textvariable=f.temp_var, width=12).pack(
            anchor=tk.W, padx=20, pady=2
        )

        _label(model_box, "上下文窗口")
        f.ctx_var = tk.StringVar()
        ttk.Combobox(
            model_box,
            textvariable=f.ctx_var,
            width=12,
            values=["8000", "16000", "32000", "64000", "128000", "200000"],
        ).pack(anchor=tk.W, padx=20, pady=2)

    def _ai_build_thinking_section(self, f: "_AIForm", parent) -> None:
        think_box = ttk.LabelFrame(parent, text="深度思考")
        think_box.pack(fill=tk.X, padx=20, pady=6)

        f.think_var = tk.BooleanVar()
        f.think_check = tk.Checkbutton(
            think_box,
            text="启用深度思考（reasoning / thinking 参数）",
            variable=f.think_var,
        )
        f.think_check.pack(anchor=tk.W, padx=20, pady=(6, 2))

        _label(think_box, "思考强度")
        f.effort_var = tk.StringVar()
        f.effort_combo = ttk.Combobox(
            think_box,
            textvariable=f.effort_var,
            values=list(REASONING_EFFORTS),
            state="readonly",
            width=14,
        )
        f.effort_combo.pack(anchor=tk.W, padx=20, pady=2)
        f.think_note = tk.Label(think_box, text="", fg="#666", anchor=tk.W, justify=tk.LEFT, wraplength=520)
        f.think_note.pack(anchor=tk.W, padx=20, pady=(0, 6))

    def _ai_build_network_section(self, f: "_AIForm", parent) -> None:
        net_box = ttk.LabelFrame(parent, text="网络与重试")
        net_box.pack(fill=tk.X, padx=20, pady=6)

        _label(net_box, "读取超时（秒）—— 单次请求等待响应的上限")
        f.timeout_var = tk.StringVar()
        ttk.Entry(net_box, textvariable=f.timeout_var, width=12).pack(anchor=tk.W, padx=20, pady=2)

        _label(net_box, "连接超时（秒）—— 建连阶段的独立上限")
        f.connect_var = tk.StringVar()
        ttk.Entry(net_box, textvariable=f.connect_var, width=12).pack(anchor=tk.W, padx=20, pady=2)

        _label(net_box, "瞬时故障重试次数（仅对 429 / 5xx / 网络错误生效）")
        f.retries_var = tk.StringVar()
        ttk.Spinbox(net_box, from_=0, to=10, textvariable=f.retries_var, width=12).pack(anchor=tk.W, padx=20, pady=2)

    def _ai_build_balance_section(self, f: "_AIForm", parent) -> None:
        bal_box = ttk.LabelFrame(parent, text="余额查询")
        bal_box.pack(fill=tk.X, padx=20, pady=6)

        f.bal_state = tk.StringVar()
        tk.Label(bal_box, textvariable=f.bal_state, fg="#666", anchor=tk.W, justify=tk.LEFT, wraplength=520).pack(
            anchor=tk.W, padx=20, pady=(6, 2)
        )

        _label(bal_box, "余额接口地址（留空使用内置）")
        f.bal_url_entry = ttk.Entry(bal_box, width=52)
        f.bal_url_entry.pack(anchor=tk.W, padx=20, pady=2)

        _label(bal_box, "余额字段路径（如 balance_infos.0.total_balance）")
        f.bal_total_entry = ttk.Entry(bal_box, width=40)
        f.bal_total_entry.pack(anchor=tk.W, padx=20, pady=2)

        _label(bal_box, "币种字段路径（如 balance_infos.0.currency）")
        f.bal_cur_entry = ttk.Entry(bal_box, width=40)
        f.bal_cur_entry.pack(anchor=tk.W, padx=20, pady=(2, 8))

    def _ai_build_action_section(self, f: "_AIForm", parent) -> None:
        action_box = tk.Frame(parent)
        action_box.pack(fill=tk.X, padx=20, pady=(4, 12))

        f.result_var = tk.StringVar(value="")
        f.result_label = tk.Label(
            action_box, textvariable=f.result_var, fg="#333", anchor=tk.W, justify=tk.LEFT, wraplength=560
        )
        f.result_label.pack(anchor=tk.W, pady=(0, 6))

        ttk.Button(action_box, text="请求 URL 预览", command=lambda: self._ai_show_url(f)).pack(side=tk.LEFT)
        ttk.Button(action_box, text="测试连接", command=lambda: self._ai_test_connection(f)).pack(side=tk.LEFT, padx=6)
        ttk.Button(action_box, text="查询余额", command=lambda: self._ai_query_balance(f)).pack(side=tk.LEFT)

    # ------------------------------------------------------------ Profile 动作

    def _ai_refresh_key_state(self, f: "_AIForm") -> None:
        cfg = f.cfg
        name = f.active_var.get()
        if cfg.profile_has_key(name):
            f.key_state.set(f"密钥：{cfg.mask_api_key(cfg.profile_api_key(name))}")
        else:
            f.key_state.set("密钥：未设置")
        # 表单内容必须跟着 Profile 走，否则会"改着 A 存到 B"
        self._ai_load_profile_into_form(f, name)

    def _ai_switch_profile(self, f: "_AIForm") -> None:
        cfg = f.cfg
        name = f.active_var.get()
        if name == cfg.active_profile:
            return
        try:
            cfg.switch_profile(name)
        except ValueError as exc:
            dialogs.showerror("切换失败", str(exc), parent=f.dialog)
            f.active_var.set(cfg.active_profile)
            return
        self._refresh_ai_client()
        self._reopen_settings(f.dialog, "已切换配置档案")

    def _ai_create_profile(self, f: "_AIForm") -> None:
        name = _ask_text(f.dialog, "新建配置档案", "档案名称（如 work、gemini-备用）：")
        if not name:
            return
        try:
            f.cfg.create_profile(name, activate=True)
        except ValueError as exc:
            dialogs.showerror("新建失败", str(exc), parent=f.dialog)
            return
        self._reopen_settings(f.dialog, f"已新建并切换到档案《{name}》")

    def _ai_rename_profile(self, f: "_AIForm") -> None:
        old = f.active_var.get()
        name = _ask_text(f.dialog, "重命名配置档案", "新的名称：", initial=old)
        if not name or name == old:
            return
        try:
            f.cfg.rename_profile(old, name)
        except ValueError as exc:
            dialogs.showerror("重命名失败", str(exc), parent=f.dialog)
            return
        self._reopen_settings(f.dialog, f"档案已重命名为《{name}》")

    def _ai_delete_profile(self, f: "_AIForm") -> None:
        name = f.active_var.get()
        if not dialogs.askyesno(
            "删除配置档案",
            f"确定删除档案《{name}》？\n该档案单独保存的 API Key 也会一并删除。",
            parent=f.dialog,
        ):
            return
        try:
            f.cfg.delete_profile(name)
        except ValueError as exc:
            dialogs.showerror("删除失败", str(exc), parent=f.dialog)
            return
        self._reopen_settings(f.dialog, f"已删除档案《{name}》")

    # ------------------------------------------------------------ 联动逻辑

    def _ai_current_provider(self, f: "_AIForm") -> str:
        return f.key_of.get(f.provider_var.get(), "custom")

    def _ai_sync_local_controls(self, f: "_AIForm") -> None:
        """按当前服务商的能力决定这一行是否出现。"""
        try:
            show = bool(self.ai_client.can_list_local_models(self._ai_current_provider(f)))
        except Exception:  # noqa: BLE001 - 能力查询失败时按"不显示"处理
            show = False
        if show:
            f.local_row.pack(anchor=tk.W, padx=20, pady=(0, 2))
        else:
            f.local_row.pack_forget()

    def _ai_load_profile_into_form(self, f: "_AIForm", name: str) -> None:
        cfg = f.cfg
        prof = cfg.profiles().get(name, {})
        spec_key = str(prof.get("api_provider", "ollama"))
        f.provider_var.set(_label_for(spec_key, f.labels, f.key_of))
        f.base_entry.delete(0, tk.END)
        f.base_entry.insert(0, str(prof.get("api_base", "")))
        f.key_entry.delete(0, tk.END)
        f.key_entry.insert(0, cfg.profile_api_key(name))
        f.model_var.set(str(prof.get("model", "")))
        f.max_tokens_var.set(str(prof.get("max_tokens", 4096)))
        f.temp_var.set(str(prof.get("temperature", 0.8)))
        f.ctx_var.set(str(prof.get("context_window", 32000)))
        f.think_var.set(bool(prof.get("thinking_enabled", True)))
        f.effort_var.set(str(prof.get("reasoning_effort", "high")))
        f.timeout_var.set(str(prof.get("timeout", 600.0)))
        f.connect_var.set(str(prof.get("connect_timeout", 10.0)))
        f.retries_var.set(str(prof.get("max_retries", 3)))
        for entry, key in (
            (f.bal_url_entry, "balance_url"),
            (f.bal_total_entry, "balance_total_path"),
            (f.bal_cur_entry, "balance_currency_path"),
        ):
            entry.delete(0, tk.END)
            entry.insert(0, str(prof.get(key, "")))
        f.model_combo["values"] = models_for_provider(spec_key)
        self._ai_apply_capabilities(f)

    def _ai_apply_capabilities(self, f: "_AIForm") -> None:
        spec = get_spec(self._ai_current_provider(f))
        caps = spec.supports.as_dict()
        f.base_hint.configure(
            text=f"该服务商的默认地址：{spec.base_url}" + ("（已含 /v1）" if spec.base_url_includes_v1 else "")
        )
        # 能力驱动显隐：不再靠 `if provider == "claude"` 之类的硬编码
        if caps.get("thinking"):
            f.think_check.configure(state="normal")
            f.effort_combo.configure(state="readonly")
            f.think_note.configure(text="该服务商支持思考模式参数。")
        else:
            f.think_check.configure(state="disabled")
            f.effort_combo.configure(state="disabled")
            f.think_note.configure(text="该服务商不支持思考模式参数，上面的开关不会发送任何额外字段。")
        if caps.get("balance"):
            f.bal_state.set(f"该服务商有余额接口（{spec.note}）。可直接点「查询余额」。")
        else:
            f.bal_state.set(f"该服务商未提供余额接口（{spec.note}）。若你确知自建/代理端点，可在下面填写以启用查询。")
        # 本地模型控件同样由能力位驱动（`local`）——
        # 放在这里可以同时覆盖"切换服务商"与"载入档案"两条路径
        self._ai_sync_local_controls(f)

    def _ai_on_provider_change(self, f: "_AIForm") -> None:
        spec_key = self._ai_current_provider(f)
        spec = get_spec(spec_key)
        # 换服务商必须换地址：沿用旧地址是本项目历史上最容易配错的地方
        f.base_entry.delete(0, tk.END)
        f.base_entry.insert(0, spec.base_url)
        candidates = models_for_provider(spec_key)
        f.model_combo["values"] = candidates
        if candidates:
            f.model_var.set(candidates[0])
        self._ai_apply_capabilities(f)

    # ------------------------------------------------------------ 动作按钮

    def _ai_show_result(self, f: "_AIForm", text: str, ok=None) -> None:
        """ok=True 绿 / False 红 / None 中性灰。

        余额的"该服务未提供余额接口"属于**正常事实**而不是错误，
        用红色显示会让用户以为功能坏了。
        """
        f.result_var.set(text)
        color = "#333" if ok is None else ("#1a7f37" if ok else "#b42318")
        f.result_label.configure(fg=color)

    def _ai_show_url(self, f: "_AIForm") -> None:
        spec_key = self._ai_current_provider(f)
        spec = get_spec(spec_key)
        base = f.base_entry.get().strip() or spec.base_url
        preview = spec.resolved_url(base)
        self._ai_show_result(f, f"[URL 预览] {preview}\n（按表单当前填写的内容计算；服务商默认地址 {spec.base_url}）")

    def _ai_test_connection(self, f: "_AIForm") -> None:
        spec_key = self._ai_current_provider(f)
        self._ai_show_result(f, "正在测试连接（会发送一个 1 token 的请求）…")
        params = dict(
            provider=spec_key,
            api_base=f.base_entry.get().strip(),
            api_key=f.key_entry.get().strip(),
            model=f.model_var.get().strip(),
        )
        self._run_in_background(
            lambda: self.ai_client.probe_connection(**params),
            lambda r: self._ai_show_result(f, _format_probe(spec_key, r), bool(r.get("ok"))),
            f.dialog,
        )

    def _ai_query_balance(self, f: "_AIForm") -> None:
        spec_key = self._ai_current_provider(f)
        self._ai_show_result(f, "正在按已保存的配置查询余额…")
        self._run_in_background(
            lambda: self.ai_client.query_balance(spec_key, use_cache=False),
            lambda r: self._ai_show_result(
                f,
                f"[余额] {r.format_total()}",
                None if not getattr(r, "supported", False) else getattr(r, "ok", False),
            ),
            f.dialog,
        )

    # ------------------------------------------------------------ 保存

    def _ai_save(self, f: "_AIForm") -> None:
        """把表单写入当前 Profile。非法输入当场报错，不做静默夹断。"""
        cfg = f.cfg
        name = f.active_var.get()
        if name != cfg.active_profile:
            cfg.switch_profile(name)
        fields = [
            ("api_provider", self._ai_current_provider(f)),
            ("api_key", f.key_entry.get().strip()),
            ("api_base", f.base_entry.get().strip()),
            ("model", f.model_var.get().strip()),
            ("max_tokens", f.max_tokens_var.get().strip()),
            ("temperature", f.temp_var.get().strip()),
            ("context_window", f.ctx_var.get().strip()),
            ("thinking_enabled", f.think_var.get()),
            ("reasoning_effort", f.effort_var.get().strip()),
            ("timeout", f.timeout_var.get().strip()),
            ("connect_timeout", f.connect_var.get().strip()),
            ("max_retries", f.retries_var.get().strip()),
            ("balance_url", f.bal_url_entry.get().strip()),
            ("balance_total_path", f.bal_total_entry.get().strip()),
            ("balance_currency_path", f.bal_cur_entry.get().strip()),
        ]
        for key, value in fields:
            try:
                cfg.set(key, value)
            except (ValueError, RuntimeError) as exc:
                dialogs.showerror(
                    "配置未保存",
                    f"{AI_PROFILE_LABELS.get(key, key)} 的值不合法：\n{exc}\n\n"
                    "已停止保存，请修正后重试（前面的字段已写入）。",
                    parent=f.dialog,
                )
                return

    # ------------------------------------------------------------ 辅助

    def _refresh_ai_client(self) -> None:
        """配置变更后重建 AI 客户端与智能体，让新配置立刻生效。"""
        try:
            from .ai_client import AIClient

            self.ai_client = AIClient(self.config)
        except Exception as exc:  # noqa: BLE001 - 重建失败不该崩界面
            self._log(f"[警告] 重建 AI 客户端失败：{exc}")

    def _reopen_settings(self, dialog, message: str = "") -> None:
        """重开设置对话框。

        Profile 切换/增删会改变**大量**控件取值，逐个刷新极易漏项
        （过去就出现过"下拉换了、表单没换"）。整体重建最不容易出错。
        """
        dialog.destroy()
        if message:
            self._log(message)
        self._show_settings()

    def _run_in_background(self, work, on_done, dialog) -> None:
        """在子线程执行网络动作，并把结果安全地回送到 Tk 主线程。

        网络请求不能在事件回调里同步跑：DNS 失败也要等超时，界面会假死。
        结果必须经 `after()` 回主线程 —— Tk 控件只能由主线程访问。

        v3 §1.1 A6：这里原来是裸 `threading.Thread`，现在统一走
        `BackgroundRunner` —— 除了少一处重复，更重要的是它做了
        `copy_context()`，让用量归因上下文能跨线程正确传递。
        """
        from .async_runner import BackgroundRunner

        def _deliver(result):
            if isinstance(result, Exception):
                on_done({"ok": False, "reason": f"{type(result).__name__}: {result}"})
            else:
                on_done(result)

        BackgroundRunner(ui=dialog).submit(
            work,
            on_success=_deliver,
            on_error=_deliver,
            name="anw-settings-probe",
        )


# ============================================================ 顶层小工具


def _label(parent, text: str) -> None:
    ttk.Label(parent, text=text, font=UIStyle.font("body_bold")).pack(anchor=tk.W, padx=20, pady=(8, 2))


def _label_for(provider_key: str, labels: List[str], key_of: Dict[str, str]) -> str:
    """由 provider key 反查下拉显示项；找不到则回落到 custom 的显示项。"""
    for label in labels:
        if key_of.get(label) == provider_key:
            return label
    for label in labels:
        if key_of.get(label) == "custom":
            return label
    return labels[0] if labels else ""


def _ask_text(dialog, title: str, prompt: str, initial: str = "") -> str:
    """单行输入对话框（tkinter 没有现成的，自己拼一个）。"""
    win = tk.Toplevel(dialog)
    win.title(title)
    win.transient(dialog)
    win.grab_set()
    win.resizable(False, False)

    ttk.Label(win, text=prompt).pack(padx=16, pady=(14, 6), anchor=tk.W)
    var = tk.StringVar(value=initial)
    entry = ttk.Entry(win, textvariable=var, width=34)
    entry.pack(padx=16, pady=2)
    entry.focus_set()

    result = {"value": ""}

    def confirm(_event=None):
        result["value"] = var.get().strip()
        win.destroy()

    def cancel(_event=None):
        result["value"] = ""
        win.destroy()

    row = tk.Frame(win)
    row.pack(pady=12)
    ttk.Button(row, text="确定", command=confirm).pack(side=tk.LEFT, padx=4)
    ttk.Button(row, text="取消", command=cancel).pack(side=tk.LEFT, padx=4)
    win.bind("<Return>", confirm)
    win.bind("<Escape>", cancel)
    win.wait_window()
    return result["value"]


def _format_probe(provider_key: str, result: dict) -> str:
    """把 `probe_connection` 的返回值整理成一行给人看的文字。"""
    if not result.get("ok"):
        return (
            f"[连接失败] {provider_key}\n"
            f"请求地址：{result.get('url', '（未计算）')}\n"
            f"原因：{result.get('reason', '未知')}"
        )
    sample = (result.get("sample") or "").strip()
    tail = f"，返回片段：{sample}" if sample else "（模型未返回文本，属正常）"
    return f"[连接成功] {provider_key} / {result.get('model', '')} (HTTP {result.get('status')}){tail}"
