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

import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Dict, List, Tuple

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
        if label in mapping:                     # 极端情况下重名，追加 key 消歧
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


# ============================================================ 界面 Mixin


class AISettingsMixin:
    """设置页 AI 页签的构建与保存。"""

    # ------------------------------------------------------------ 入口

    def _build_ai_settings_tab(self, parent, dialog) -> Callable[[], None]:
        """构建 AI 页签，返回保存回调 `save() -> None`。"""
        cfg = self.config
        labels, key_of = provider_choices()

        # ============================================== Profile 区
        prof_box = ttk.LabelFrame(parent, text="配置档案（Profile）")
        prof_box.pack(fill=tk.X, padx=20, pady=(10, 6))

        prof_row = tk.Frame(prof_box)
        prof_row.pack(fill=tk.X, padx=8, pady=6)

        active_var = tk.StringVar(value=cfg.active_profile)
        prof_combo = ttk.Combobox(
            prof_row, textvariable=active_var, values=cfg.profile_names(),
            state="readonly", width=18,
        )
        prof_combo.pack(side=tk.LEFT)

        key_state = tk.StringVar()

        def refresh_key_state(*_):
            name = active_var.get()
            if cfg.profile_has_key(name):
                key_state.set(f"密钥：{cfg.mask_api_key(cfg.profile_api_key(name))}")
            else:
                key_state.set("密钥：未设置")
            # 表单内容必须跟着 Profile 走，否则会"改着 A 存到 B"
            _load_profile_into_form(name)

        key_label = tk.Label(prof_row, textvariable=key_state, fg="#666")
        key_label.pack(side=tk.LEFT, padx=10)

        def _switch(*_):
            name = active_var.get()
            if name == cfg.active_profile:
                return
            try:
                cfg.switch_profile(name)
            except ValueError as exc:
                messagebox.showerror("切换失败", str(exc), parent=dialog)
                active_var.set(cfg.active_profile)
                return
            self._refresh_ai_client()
            self._reopen_settings(dialog, "已切换配置档案")

        def _create():
            name = _ask_text(dialog, "新建配置档案", "档案名称（如 work、gemini-备用）：")
            if not name:
                return
            try:
                cfg.create_profile(name, activate=True)
            except ValueError as exc:
                messagebox.showerror("新建失败", str(exc), parent=dialog)
                return
            self._reopen_settings(dialog, f"已新建并切换到档案《{name}》")

        def _rename():
            old = active_var.get()
            name = _ask_text(dialog, "重命名配置档案", "新的名称：", initial=old)
            if not name or name == old:
                return
            try:
                cfg.rename_profile(old, name)
            except ValueError as exc:
                messagebox.showerror("重命名失败", str(exc), parent=dialog)
                return
            self._reopen_settings(dialog, f"档案已重命名为《{name}》")

        def _delete():
            name = active_var.get()
            if not messagebox.askyesno(
                "删除配置档案",
                f"确定删除档案《{name}》？\n该档案单独保存的 API Key 也会一并删除。",
                parent=dialog,
            ):
                return
            try:
                cfg.delete_profile(name)
            except ValueError as exc:
                messagebox.showerror("删除失败", str(exc), parent=dialog)
                return
            self._reopen_settings(dialog, f"已删除档案《{name}》")

        for text, command in (("切换", _switch), ("新建", _create),
                              ("重命名", _rename), ("删除", _delete)):
            ttk.Button(prof_row, text=text, command=command, width=6).pack(
                side=tk.LEFT, padx=2
            )

        # ============================================== 连接区
        conn_box = ttk.LabelFrame(parent, text="连接")
        conn_box.pack(fill=tk.X, padx=20, pady=6)

        _label(conn_box, "AI 服务商")
        provider_var = tk.StringVar()
        provider_combo = ttk.Combobox(
            conn_box, textvariable=provider_var, values=labels,
            state="readonly", width=42,
        )
        provider_combo.pack(anchor=tk.W, padx=20, pady=2)

        _label(conn_box, "API 地址")
        base_entry = ttk.Entry(conn_box, width=52)
        base_entry.pack(anchor=tk.W, padx=20, pady=2)
        base_hint = tk.Label(conn_box, text="", fg="#666", anchor=tk.W, justify=tk.LEFT)
        base_hint.pack(anchor=tk.W, padx=20)

        _label(conn_box, "API 密钥")
        key_row = tk.Frame(conn_box)
        key_row.pack(anchor=tk.W, padx=20, pady=2)
        key_entry = ttk.Entry(key_row, width=44, show="*")
        key_entry.pack(side=tk.LEFT)
        show_key = tk.BooleanVar(value=False)

        def _toggle_key():
            key_entry.configure(show="" if show_key.get() else "*")

        ttk.Checkbutton(key_row, text="显示", variable=show_key,
                        command=_toggle_key).pack(side=tk.LEFT, padx=6)
        tk.Label(conn_box,
                 text="密钥加密后保存，不明文落盘；每个档案各存各的。",
                 fg="#666", anchor=tk.W).pack(anchor=tk.W, padx=20)

        # ============================================== 模型与采样
        model_box = ttk.LabelFrame(parent, text="模型与采样")
        model_box.pack(fill=tk.X, padx=20, pady=6)

        _label(model_box, "模型名称")
        model_var = tk.StringVar()
        model_combo = ttk.Combobox(model_box, textvariable=model_var, width=42)
        model_combo.pack(anchor=tk.W, padx=20, pady=2)

        _label(model_box, "最大输出 token")
        max_tokens_var = tk.StringVar()
        ttk.Entry(model_box, textvariable=max_tokens_var, width=12).pack(
            anchor=tk.W, padx=20, pady=2
        )

        _label(model_box, "温度（0 ~ 2，越高越发散）")
        temp_var = tk.StringVar()
        ttk.Spinbox(model_box, from_=0, to=2, increment=0.1,
                    textvariable=temp_var, width=12).pack(anchor=tk.W, padx=20, pady=2)

        _label(model_box, "上下文窗口")
        ctx_var = tk.StringVar()
        ttk.Combobox(model_box, textvariable=ctx_var, width=12,
                     values=["8000", "16000", "32000", "64000", "128000", "200000"],
                     ).pack(anchor=tk.W, padx=20, pady=2)

        # ============================================== 思考模式
        think_box = ttk.LabelFrame(parent, text="深度思考")
        think_box.pack(fill=tk.X, padx=20, pady=6)

        think_var = tk.BooleanVar()
        think_check = tk.Checkbutton(
            think_box, text="启用深度思考（reasoning / thinking 参数）",
            variable=think_var,
        )
        think_check.pack(anchor=tk.W, padx=20, pady=(6, 2))

        _label(think_box, "思考强度")
        effort_var = tk.StringVar()
        effort_combo = ttk.Combobox(
            think_box, textvariable=effort_var, values=list(REASONING_EFFORTS),
            state="readonly", width=14,
        )
        effort_combo.pack(anchor=tk.W, padx=20, pady=2)
        think_note = tk.Label(think_box, text="", fg="#666", anchor=tk.W,
                              justify=tk.LEFT, wraplength=520)
        think_note.pack(anchor=tk.W, padx=20, pady=(0, 6))

        # ============================================== 网络与重试
        net_box = ttk.LabelFrame(parent, text="网络与重试")
        net_box.pack(fill=tk.X, padx=20, pady=6)

        _label(net_box, "读取超时（秒）—— 单次请求等待响应的上限")
        timeout_var = tk.StringVar()
        ttk.Entry(net_box, textvariable=timeout_var, width=12).pack(
            anchor=tk.W, padx=20, pady=2
        )

        _label(net_box, "连接超时（秒）—— 建连阶段的独立上限")
        connect_var = tk.StringVar()
        ttk.Entry(net_box, textvariable=connect_var, width=12).pack(
            anchor=tk.W, padx=20, pady=2
        )

        _label(net_box, "瞬时故障重试次数（仅对 429 / 5xx / 网络错误生效）")
        retries_var = tk.StringVar()
        ttk.Spinbox(net_box, from_=0, to=10, textvariable=retries_var, width=12).pack(
            anchor=tk.W, padx=20, pady=2
        )

        # ============================================== 余额
        bal_box = ttk.LabelFrame(parent, text="余额查询")
        bal_box.pack(fill=tk.X, padx=20, pady=6)

        bal_state = tk.StringVar()
        tk.Label(bal_box, textvariable=bal_state, fg="#666", anchor=tk.W,
                 justify=tk.LEFT, wraplength=520).pack(anchor=tk.W, padx=20, pady=(6, 2))

        _label(bal_box, "余额接口地址（留空使用内置）")
        bal_url_entry = ttk.Entry(bal_box, width=52)
        bal_url_entry.pack(anchor=tk.W, padx=20, pady=2)

        _label(bal_box, "余额字段路径（如 balance_infos.0.total_balance）")
        bal_total_entry = ttk.Entry(bal_box, width=40)
        bal_total_entry.pack(anchor=tk.W, padx=20, pady=2)

        _label(bal_box, "币种字段路径（如 balance_infos.0.currency）")
        bal_cur_entry = ttk.Entry(bal_box, width=40)
        bal_cur_entry.pack(anchor=tk.W, padx=20, pady=(2, 8))

        # ============================================== 动作按钮
        action_box = tk.Frame(parent)
        action_box.pack(fill=tk.X, padx=20, pady=(4, 12))

        result_var = tk.StringVar(value="")
        result_label = tk.Label(action_box, textvariable=result_var, fg="#333",
                                anchor=tk.W, justify=tk.LEFT, wraplength=560)
        result_label.pack(anchor=tk.W, pady=(0, 6))

        def _current_provider() -> str:
            return key_of.get(provider_var.get(), "custom")

        def _show_result(text: str, ok=None):
            """ok=True 绿 / False 红 / None 中性灰。

            余额的"该服务未提供余额接口"属于**正常事实**而不是错误，
            用红色显示会让用户以为功能坏了。
            """
            result_var.set(text)
            color = "#333" if ok is None else ("#1a7f37" if ok else "#b42318")
            result_label.configure(fg=color)

        def _show_url():
            spec_key = _current_provider()
            spec = get_spec(spec_key)
            base = base_entry.get().strip() or spec.base_url
            preview = spec.resolved_url(base)
            _show_result(
                f"[URL 预览] {preview}\n"
                f"（按表单当前填写的内容计算；服务商默认地址 {spec.base_url}）"
            )

        def _test_connection():
            spec_key = _current_provider()
            _show_result("正在测试连接（会发送一个 1 token 的请求）…")
            params = dict(
                provider=spec_key,
                api_base=base_entry.get().strip(),
                api_key=key_entry.get().strip(),
                model=model_var.get().strip(),
            )
            self._run_in_background(
                lambda: self.ai_client.probe_connection(**params),
                lambda r: _show_result(_format_probe(spec_key, r), bool(r.get("ok"))),
                dialog,
            )

        def _query_balance():
            spec_key = _current_provider()
            _show_result("正在按已保存的配置查询余额…")
            self._run_in_background(
                lambda: self.ai_client.query_balance(spec_key, use_cache=False),
                lambda r: _show_result(
                    f"[余额] {r.format_total()}",
                    None if not getattr(r, "supported", False) else getattr(r, "ok", False),
                ),
                dialog,
            )

        ttk.Button(action_box, text="请求 URL 预览", command=_show_url).pack(side=tk.LEFT)
        ttk.Button(action_box, text="测试连接", command=_test_connection).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(action_box, text="查询余额", command=_query_balance).pack(side=tk.LEFT)

        # ============================================== 联动逻辑
        def _load_profile_into_form(name: str):
            prof = cfg.profiles().get(name, {})
            spec_key = str(prof.get("api_provider", "ollama"))
            provider_var.set(_label_for(spec_key, labels, key_of))
            base_entry.delete(0, tk.END)
            base_entry.insert(0, str(prof.get("api_base", "")))
            key_entry.delete(0, tk.END)
            key_entry.insert(0, cfg.profile_api_key(name))
            model_var.set(str(prof.get("model", "")))
            max_tokens_var.set(str(prof.get("max_tokens", 4096)))
            temp_var.set(str(prof.get("temperature", 0.8)))
            ctx_var.set(str(prof.get("context_window", 32000)))
            think_var.set(bool(prof.get("thinking_enabled", True)))
            effort_var.set(str(prof.get("reasoning_effort", "high")))
            timeout_var.set(str(prof.get("timeout", 600.0)))
            connect_var.set(str(prof.get("connect_timeout", 10.0)))
            retries_var.set(str(prof.get("max_retries", 3)))
            for entry, key in ((bal_url_entry, "balance_url"),
                               (bal_total_entry, "balance_total_path"),
                               (bal_cur_entry, "balance_currency_path")):
                entry.delete(0, tk.END)
                entry.insert(0, str(prof.get(key, "")))
            model_combo['values'] = models_for_provider(spec_key)
            _apply_capabilities()

        def _apply_capabilities(*_):
            spec_key = _current_provider()
            spec = get_spec(spec_key)
            caps = spec.supports.as_dict()
            base_hint.configure(
                text=f"该服务商的默认地址：{spec.base_url}"
                     + ("（已含 /v1）" if spec.base_url_includes_v1 else "")
            )
            # 能力驱动显隐：不再靠 `if provider == "claude"` 之类的硬编码
            if caps.get("thinking"):
                think_check.configure(state="normal")
                effort_combo.configure(state="readonly")
                think_note.configure(text="该服务商支持思考模式参数。")
            else:
                think_check.configure(state="disabled")
                effort_combo.configure(state="disabled")
                think_note.configure(
                    text="该服务商不支持思考模式参数，上面的开关不会发送任何额外字段。"
                )
            if caps.get("balance"):
                bal_state.set(f"该服务商有余额接口（{spec.note}）。可直接点「查询余额」。")
            else:
                bal_state.set(
                    f"该服务商未提供余额接口（{spec.note}）。"
                    "若你确知自建/代理端点，可在下面填写以启用查询。"
                )

        def _on_provider_change(*_):
            spec_key = _current_provider()
            spec = get_spec(spec_key)
            # 换服务商必须换地址：沿用旧地址是本项目历史上最容易配错的地方
            base_entry.delete(0, tk.END)
            base_entry.insert(0, spec.base_url)
            candidates = models_for_provider(spec_key)
            model_combo['values'] = candidates
            if candidates:
                model_var.set(candidates[0])
            _apply_capabilities()

        provider_combo.bind('<<ComboboxSelected>>', _on_provider_change)

        # ============================================== 保存
        def save() -> None:
            """把表单写入当前 Profile。非法输入当场报错，不做静默夹断。"""
            name = active_var.get()
            if name != cfg.active_profile:
                cfg.switch_profile(name)
            fields = [
                ("api_provider", _current_provider()),
                ("api_key", key_entry.get().strip()),
                ("api_base", base_entry.get().strip()),
                ("model", model_var.get().strip()),
                ("max_tokens", max_tokens_var.get().strip()),
                ("temperature", temp_var.get().strip()),
                ("context_window", ctx_var.get().strip()),
                ("thinking_enabled", think_var.get()),
                ("reasoning_effort", effort_var.get().strip()),
                ("timeout", timeout_var.get().strip()),
                ("connect_timeout", connect_var.get().strip()),
                ("max_retries", retries_var.get().strip()),
                ("balance_url", bal_url_entry.get().strip()),
                ("balance_total_path", bal_total_entry.get().strip()),
                ("balance_currency_path", bal_cur_entry.get().strip()),
            ]
            for key, value in fields:
                try:
                    cfg.set(key, value)
                except (ValueError, RuntimeError) as exc:
                    messagebox.showerror(
                        "配置未保存",
                        f"{AI_PROFILE_LABELS.get(key, key)} 的值不合法：\n{exc}\n\n"
                        "已停止保存，请修正后重试（前面的字段已写入）。",
                        parent=dialog,
                    )
                    return

        # 初始化：先把活跃 Profile 灌进表单（内含 provider 下拉与能力联动）
        prof_combo.bind('<<ComboboxSelected>>', _switch)
        refresh_key_state()

        return save

    # ------------------------------------------------------------ 辅助

    def _refresh_ai_client(self) -> None:
        """配置变更后重建 AI 客户端与智能体，让新配置立刻生效。"""
        try:
            from .ai_client import AIClient
            self.ai_client = AIClient(self.config)
        except Exception as exc:                        # noqa: BLE001 - 重建失败不该崩界面
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
        """

        def runner():
            try:
                result = work()
            except Exception as exc:                    # noqa: BLE001 - 需回报给用户
                result = exc
            try:
                dialog.after(0, lambda: _deliver(result))
            except tk.TclError:
                pass                                    # 对话框已被关闭

        def _deliver(result):
            if isinstance(result, Exception):
                on_done({"ok": False, "reason": f"{type(result).__name__}: {result}"})
            else:
                on_done(result)

        threading.Thread(target=runner, daemon=True).start()


# ============================================================ 顶层小工具


def _label(parent, text: str) -> None:
    ttk.Label(parent, text=text, font=('微软雅黑', 10, 'bold')).pack(
        anchor=tk.W, padx=20, pady=(8, 2)
    )


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
    win.bind('<Return>', confirm)
    win.bind('<Escape>', cancel)
    win.wait_window()
    return result["value"]


def _format_probe(provider_key: str, result: dict) -> str:
    """把 `probe_connection` 的返回值整理成一行给人看的文字。"""
    if not result.get("ok"):
        return (f"[连接失败] {provider_key}\n"
                f"请求地址：{result.get('url', '（未计算）')}\n"
                f"原因：{result.get('reason', '未知')}")
    sample = (result.get("sample") or "").strip()
    tail = f"，返回片段：{sample}" if sample else "（模型未返回文本，属正常）"
    return (f"[连接成功] {provider_key} / {result.get('model', '')} "
            f"(HTTP {result.get('status')}){tail}")
