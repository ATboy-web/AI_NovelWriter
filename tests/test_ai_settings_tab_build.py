"""AI 设置页签的构建与交互测试（P1-4 拆分后新增）。

此前 `ai_settings_ui` 覆盖率仅 11.57%：既有测试只测了三个纯函数，
真正承载风险的 440 行表单构建/联动/保存逻辑一行未测。
拆分成 `_ai_build_*` / `_ai_*` 方法后，这些行为终于可以逐条断言。

用真实 Tk（经 `_tk_harness.optional_root`，无显示环境会带告警跳过），
配置与 AI 客户端用替身，后台任务改为同步执行以获得确定性。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from _tk_harness import optional_root

from app import ai_settings_ui as mod
from app.ai_settings_ui import AISettingsMixin
from app.providers import get_spec, specs_for_ui


class FakeConfig:
    """最小多档案配置替身，只实现页签用到的读写面。"""

    def __init__(self):
        self.active_profile = "default"
        self._profiles = {
            "default": {
                "api_provider": "deepseek",
                "api_base": "https://api.deepseek.com",
                "model": "deepseek-chat",
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
            }
        }
        self._keys = {"default": "sk-secret-value"}
        self.written = {}
        self.reject_key = None

    def profile_names(self):
        return list(self._profiles)

    def profiles(self):
        return self._profiles

    def profile_has_key(self, name):
        return bool(self._keys.get(name))

    def profile_api_key(self, name):
        return self._keys.get(name, "")

    def mask_api_key(self, key):
        return "***" if key else ""

    def switch_profile(self, name):
        if name not in self._profiles:
            raise ValueError(f"档案不存在：{name}")
        self.active_profile = name

    def create_profile(self, name, activate=False):
        if name in self._profiles:
            raise ValueError("档案已存在")
        self._profiles[name] = dict(self._profiles["default"])
        if activate:
            self.active_profile = name

    def rename_profile(self, old, new):
        if old not in self._profiles:
            raise ValueError("档案不存在")
        self._profiles[new] = self._profiles.pop(old)
        if self.active_profile == old:
            self.active_profile = new

    def delete_profile(self, name):
        if len(self._profiles) <= 1:
            raise ValueError("至少保留一个档案")
        self._profiles.pop(name, None)

    def set(self, key, value):
        if key == self.reject_key:
            raise ValueError("数值超出范围")
        self.written[key] = value
        self._profiles[self.active_profile][key] = value


class FakeAIClient:
    def __init__(self):
        self.local_supported = False
        self.models = []
        self.probe_result = {"ok": True, "message": "连接正常"}
        self.local_error = None

    def can_list_local_models(self, provider):
        return self.local_supported

    def list_local_models(self):
        if self.local_error:
            raise self.local_error
        return self.models

    def check_local_service(self):
        return (True, "本地服务在线")

    def probe_connection(self, **kwargs):
        return dict(self.probe_result, params=kwargs)

    def query_balance(self, provider, use_cache=False):
        class R:
            supported = True
            ok = True

            def format_total(self):
                return "￥12.34"

        return R()


class Host(AISettingsMixin):
    """承载 Mixin 的最小宿主：后台任务同步化，便于断言。"""

    def __init__(self):
        self.config = FakeConfig()
        self.ai_client = FakeAIClient()
        self.logs = []
        self.reopened = []
        self.refreshed = 0

    def _run_in_background(self, work, on_done, dialog):
        try:
            result = work()
        except Exception as exc:  # noqa: BLE001 - 与真实实现一致地转成错误形状
            result = {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
        on_done(result)

    def _refresh_ai_client(self):
        self.refreshed += 1

    def _reopen_settings(self, dialog, message=""):
        self.reopened.append(message)

    def _log(self, message):
        self.logs.append(message)


@pytest.fixture
def tk_root():
    root = optional_root()
    try:
        yield root
    finally:
        root.destroy()


@pytest.fixture
def built(tk_root):
    """返回 (host, frame, save, form)。form 通过截获构建入口拿到。"""
    import tkinter as tk

    host = Host()
    frame = tk.Frame(tk_root)
    frame.pack()
    captured = {}
    original = host._ai_build_profile_section

    def spy(f, parent):
        captured["form"] = f
        return original(f, parent)

    host._ai_build_profile_section = spy
    save = host._build_ai_settings_tab(frame, host_dialog_stub(tk_root))
    return host, frame, save, captured["form"]


def host_dialog_stub(root):
    """页签只需要一个能当 parent 的窗口对象。"""
    return root


def _labelframe_texts(frame):
    from tkinter import ttk

    return [w.cget("text") for w in frame.winfo_children() if isinstance(w, ttk.LabelFrame)]


# ------------------------------------------------------------------ 构建


def test_all_sections_built_in_order(built):
    _, frame, save, _ = built
    assert callable(save)
    assert _labelframe_texts(frame) == [
        "配置档案（Profile）",
        "连接",
        "模型与采样",
        "深度思考",
        "网络与重试",
        "余额查询",
    ]


def test_profile_loaded_into_form(built):
    host, _, _, f = built
    assert f.base_entry.get() == "https://api.deepseek.com"
    assert f.model_var.get() == "deepseek-chat"
    assert f.temp_var.get() == "0.8"
    assert f.timeout_var.get() == "600.0"
    assert f.key_entry.get() == "sk-secret-value"
    assert "密钥：" in f.key_state.get()


def test_key_state_when_missing(built):
    host, _, _, f = built
    host.config._keys.clear()
    host._ai_refresh_key_state(f)
    assert f.key_state.get() == "密钥：未设置"


# ------------------------------------------------------------------ 联动


def test_provider_change_resets_base_and_models(built):
    host, _, _, f = built
    target = next(s for s in specs_for_ui() if s["key"] != "deepseek")
    label = next(lb for lb, k in f.key_of.items() if k == target["key"])
    f.provider_var.set(label)
    host._ai_on_provider_change(f)
    assert f.base_entry.get() == get_spec(target["key"]).base_url
    assert f.model_var.get() == list(f.model_combo["values"])[0]


def test_capabilities_drive_thinking_controls(built):
    host, _, _, f = built
    no_think = next(s for s in specs_for_ui() if not s["supports"].get("thinking"))
    label = next(lb for lb, k in f.key_of.items() if k == no_think["key"])
    f.provider_var.set(label)
    host._ai_apply_capabilities(f)
    assert str(f.think_check.cget("state")) == "disabled"
    assert "不支持思考模式" in f.think_note.cget("text")


def test_balance_note_reflects_capability(built):
    host, _, _, f = built
    host._ai_apply_capabilities(f)
    spec = get_spec(host._ai_current_provider(f))
    expected = "有余额接口" if spec.supports.as_dict().get("balance") else "未提供余额接口"
    assert expected in f.bal_state.get()


def test_local_controls_visibility(built):
    host, _, _, f = built
    host.ai_client.local_supported = True
    host._ai_sync_local_controls(f)
    assert f.local_row.winfo_manager() == "pack"
    host.ai_client.local_supported = False
    host._ai_sync_local_controls(f)
    assert f.local_row.winfo_manager() == ""


def test_local_controls_hidden_when_capability_query_fails(built):
    host, _, _, f = built

    def boom(provider):
        raise RuntimeError("能力查询失败")

    host.ai_client.can_list_local_models = boom
    host._ai_sync_local_controls(f)
    assert f.local_row.winfo_manager() == ""


# ------------------------------------------------------------------ 保存


def test_save_writes_all_fields(built):
    host, _, save, _ = built
    save()
    for key in ("api_provider", "api_base", "model", "temperature", "timeout", "max_retries"):
        assert key in host.config.written
    assert host.config.written["api_provider"] == "deepseek"


def test_save_stops_on_invalid_value(built, monkeypatch):
    host, _, save, _ = built
    host.config.reject_key = "temperature"
    seen = []
    monkeypatch.setattr(mod.dialogs, "showerror", lambda *a, **k: seen.append(a))
    save()
    assert seen, "非法输入必须弹错误提示"
    assert "temperature" in host.config.written or "model" in host.config.written
    assert "max_retries" not in host.config.written, "报错后必须停止保存后续字段"


def test_save_switches_profile_first(built):
    host, _, save, f = built
    host.config.create_profile("work")
    f.active_var.set("work")
    save()
    assert host.config.active_profile == "work"


# ------------------------------------------------------------------ Profile 动作


def test_create_profile_flow(built, monkeypatch):
    host, _, _, f = built
    monkeypatch.setattr(mod, "_ask_text", lambda *a, **k: "work")
    host._ai_create_profile(f)
    assert "work" in host.config.profiles()
    assert host.reopened and "work" in host.reopened[0]


def test_create_profile_cancelled(built, monkeypatch):
    host, _, _, f = built
    monkeypatch.setattr(mod, "_ask_text", lambda *a, **k: "")
    host._ai_create_profile(f)
    assert host.reopened == []


def test_create_profile_error_shown(built, monkeypatch):
    host, _, _, f = built
    monkeypatch.setattr(mod, "_ask_text", lambda *a, **k: "default")
    seen = []
    monkeypatch.setattr(mod.dialogs, "showerror", lambda *a, **k: seen.append(a))
    host._ai_create_profile(f)
    assert seen and seen[0][0] == "新建失败"


def test_rename_and_delete_flow(built, monkeypatch):
    host, _, _, f = built
    host.config.create_profile("work", activate=True)
    f.active_var.set("work")
    monkeypatch.setattr(mod, "_ask_text", lambda *a, **k: "work2")
    host._ai_rename_profile(f)
    assert "work2" in host.config.profiles()
    f.active_var.set("work2")
    monkeypatch.setattr(mod.dialogs, "askyesno", lambda *a, **k: True)
    host._ai_delete_profile(f)
    assert "work2" not in host.config.profiles()


def test_delete_declined(built, monkeypatch):
    host, _, _, f = built
    monkeypatch.setattr(mod.dialogs, "askyesno", lambda *a, **k: False)
    host._ai_delete_profile(f)
    assert host.reopened == []


def test_switch_to_same_profile_is_noop(built):
    host, _, _, f = built
    host._ai_switch_profile(f)
    assert host.refreshed == 0


def test_switch_failure_restores_selection(built, monkeypatch):
    host, _, _, f = built
    f.active_var.set("不存在的档案")
    seen = []
    monkeypatch.setattr(mod.dialogs, "showerror", lambda *a, **k: seen.append(a))
    host._ai_switch_profile(f)
    assert seen and f.active_var.get() == host.config.active_profile


# ------------------------------------------------------------------ 动作按钮


def test_url_preview(built):
    host, _, _, f = built
    host._ai_show_url(f)
    assert f.result_var.get().startswith("[URL 预览]")


def test_test_connection_success_and_failure(built):
    host, _, _, f = built
    host._ai_test_connection(f)
    assert f.result_var.get()
    host.ai_client.probe_result = {"ok": False, "message": "密钥无效"}
    host._ai_test_connection(f)
    assert str(f.result_label.cget("fg")) == "#b42318"


def test_query_balance_uses_neutral_color_when_unsupported(built):
    host, _, _, f = built

    class Unsupported:
        supported = False
        ok = False

        def format_total(self):
            return "该服务未提供余额接口"

    host.ai_client.query_balance = lambda *a, **k: Unsupported()
    host._ai_query_balance(f)
    assert str(f.result_label.cget("fg")) == "#333", "正常事实不该显示成红色错误"


def test_local_model_refresh_paths(built):
    host, _, _, f = built

    class M:
        def __init__(self, name):
            self.name = name

    host.ai_client.models = [M("llama3"), M("qwen2")]
    _click(f.local_row, "刷新本地模型")
    assert "已读到 2 个本地模型" in f.local_var.get()
    assert list(f.model_combo["values"]) == ["llama3", "qwen2"]
    assert f.model_var.get() == "deepseek-chat", "刷新候选不得覆盖用户已填模型名"

    host.ai_client.models = []
    _click(f.local_row, "刷新本地模型")
    assert "未读到模型" in f.local_var.get()

    host.ai_client.local_error = RuntimeError("服务未启动")
    _click(f.local_row, "刷新本地模型")
    assert "读取失败" in f.local_var.get()


def test_check_local_service(built):
    host, _, _, f = built
    _click(f.local_row, "检测本地服务")
    assert "本地服务在线" in f.local_var.get()


def _click(row, text):
    from tkinter import ttk

    for w in row.winfo_children():
        if isinstance(w, ttk.Button) and w.cget("text") == text:
            w.invoke()
            return
    raise AssertionError(f"找不到按钮：{text}")
