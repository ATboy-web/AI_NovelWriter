"""`ai_settings_ui` 剩余分支：档案操作 / 客户端重建 / 后台派发 / 输入框。

## 为什么挑这几个（按故障类型）

设置页的失效方式**不是崩溃**，而是：

| 失效 | 用户看到 |
|---|---|
| 档案切换后表单没跟着换 | "改着 A 存到 B" —— 密钥与模型错配，白花钱 |
| 重建客户端失败却静默 | 改了配置但不生效，用户以为改了 |
| 后台任务结果没回主线程 | 点"测试连接"永远转圈，或 Tk 跨线程崩 |
| 重命名/删除档案失败 | 档案还在，用户以为删了（或反之） |

这些都不会写在日志里给用户看，所以只能靠用例钉住。

## 覆盖策略

- `_label_for`：纯函数，穷举三种回落
- 档案增删改切：`_AIForm` 用替身（只需要 `cfg` / `active_var` / `dialog`），
  `_ask_text` 与 `dialogs.*` 打桩 —— 要验的是**分支走向**与**是否重建界面**
- `_run_in_background`：真实现 + 假对话框，验成功/异常两条都回到 `on_done`
- `_ask_text`：真 Tk（`after()` 送 Enter / Escape），验确定与取消的返回值
"""

from __future__ import annotations

import time
import tkinter as tk
from typing import Optional

import _tk_harness
import pytest

from app import ai_settings_ui as mod
from app import dialogs
from app.ai_settings_ui import AISettingsMixin, _label_for


class _Var:
    """`tk.StringVar` 的最小替身（只要 get/set）。"""

    def __init__(self, value: str = "") -> None:
        self._value = value

    def get(self) -> str:
        return self._value

    def set(self, value: str) -> None:
        self._value = value


class FakeCfg:
    """只实现档案操作面；`switch/rename/delete` 的报错可注入。"""

    def __init__(self, names=("default", "work"), active="default", *, boom: Optional[str] = None):
        self.profile_names_list = list(names)
        self.active_profile = active
        self._boom = boom
        self.renamed: list[tuple[str, str]] = []
        self.deleted: list[str] = []
        self.switched: list[str] = []

    def profile_names(self):
        return list(self.profile_names_list)

    def create_profile(self, name, activate: bool = False):
        if self._boom == "create":
            raise ValueError("档案已存在")
        self.profile_names_list.append(name)
        if activate:
            self.active_profile = name

    def switch_profile(self, name):
        if self._boom == "switch":
            raise ValueError("档案不存在")
        self.active_profile = name
        self.switched.append(name)

    def rename_profile(self, old, new):
        if self._boom == "rename":
            raise ValueError("名字冲突")
        self.renamed.append((old, new))

    def delete_profile(self, name):
        if self._boom == "delete":
            raise ValueError("不能删除最后一个档案")
        self.deleted.append(name)


class FakeDialog:
    def __init__(self) -> None:
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True

    def after(self, _ms, fn, *args):
        """立即执行 —— 等价"回调已回到主线程"。"""
        fn(*args)


class FakeForm:
    def __init__(self, cfg, active: str = "default") -> None:
        self.cfg = cfg
        self.active_var = _Var(active)
        self.dialog = FakeDialog()


class Host(AISettingsMixin):
    def __init__(self) -> None:
        self.logs: list[str] = []
        self.reopened: list[str] = []
        self.refreshed = 0

    def _log(self, message: str) -> None:
        self.logs.append(message)

    # 只替换"重建界面"这一个副作用，其余走真实现
    def _reopen_settings(self, dialog, message: str = "") -> None:
        self.reopened.append(message)
        self._reopen_called_with = dialog

    def _refresh_ai_client(self) -> None:
        self.refreshed += 1


class TestLabelFor:
    """由 provider key 反查下拉显示项 —— 下拉显示错，用户就改错服务。"""

    LABELS = ["DeepSeek", "OpenAI", "自定义"]
    KEY_OF = {"DeepSeek": "deepseek", "OpenAI": "openai", "自定义": "custom"}

    def test_exact_match(self):
        assert _label_for("openai", self.LABELS, self.KEY_OF) == "OpenAI"

    def test_unknown_key_falls_back_to_custom(self):
        """未知 provider（例如新加的）落到"自定义"项，而不是空选。"""
        assert _label_for("brand-new", self.LABELS, self.KEY_OF) == "自定义"

    def test_no_custom_falls_back_to_first(self):
        labels = ["DeepSeek", "OpenAI"]
        key_of = {"DeepSeek": "deepseek", "OpenAI": "openai"}

        assert _label_for("brand-new", labels, key_of) == "DeepSeek"

    def test_empty_labels_returns_empty(self):
        assert _label_for("deepseek", [], {}) == ""


class TestRunInBackground:
    """后台派发：结果必须经 `on_done` 回来，异常也要变成**可展示的原因**。"""

    @staticmethod
    def _wait_for(predicate, timeout: float = 3.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return False

    def test_success_returns_result(self):
        got: list = []
        host = Host()

        host._run_in_background(lambda: {"ok": True, "model": "m1"}, got.append, FakeDialog())

        assert self._wait_for(lambda: got), "后台结果没有回送"
        assert got[0] == {"ok": True, "model": "m1"}

    def test_exception_is_converted_to_reason(self):
        """失败必须带上异常类型与消息 —— 只回 "失败" 等于没告诉用户发生了什么。"""
        got: list = []
        host = Host()

        def boom():
            raise ConnectionError("DNS 解析失败")

        host._run_in_background(boom, got.append, FakeDialog())

        assert self._wait_for(lambda: got), "异常没有回送"
        assert got[0]["ok"] is False
        assert "ConnectionError" in got[0]["reason"]
        assert "DNS 解析失败" in got[0]["reason"]

    def test_works_without_ui_object(self):
        """`dialog` 为 None 时也要能跑（无 GUI 环境下的降级路径）。"""
        got: list = []
        host = Host()

        host._run_in_background(lambda: 7, got.append, None)

        assert self._wait_for(lambda: got)
        assert got[0] == 7


class TestProfileOperations:
    """档案增删改切 —— 每个都要么重建界面，要么明确报错，不能"看起来成功"。"""

    def _patch_ask(self, monkeypatch, value):
        monkeypatch.setattr(mod, "_ask_text", lambda *a, **kw: value)

    def test_switch_profile_rebuilds_ui(self, monkeypatch):
        monkeypatch.setattr(dialogs, "showerror", lambda *a, **kw: pytest.fail("不该报错"))
        host = Host()
        form = FakeForm(FakeCfg(), active="work")  # 下拉选到 work，实际还是 default

        host._ai_switch_profile(form)

        assert form.cfg.switched == ["work"]
        assert host.refreshed == 1, "切档案后没有重建 AI 客户端"
        assert host.reopened == ["已切换配置档案"]

    def test_switch_to_same_profile_is_noop(self):
        """下拉没变时不该重建界面（否则用户每点一次都闪一下）。"""
        host = Host()
        # 下拉与当前档案**一致**：这才会走到"没变就返回"分支
        form = FakeForm(FakeCfg(active="work"), active="work")

        host._ai_switch_profile(form)

        assert host.refreshed == 0
        assert host.reopened == []

    def test_switch_failure_reverts_selection(self, monkeypatch):
        """切换失败要把下拉**拨回原档案** —— 否则界面显示 A、实际还是 B。"""
        errors: list = []
        monkeypatch.setattr(dialogs, "showerror", lambda *a, **kw: errors.append(a))
        host = Host()
        form = FakeForm(FakeCfg(active="default", boom="switch"), active="work")

        host._ai_switch_profile(form)

        assert form.active_var.get() == "default"
        assert errors, "失败了却没提示"
        assert host.reopened == [], "失败后不该重建界面"

    def test_create_profile_activates_and_reopens(self, monkeypatch):
        self._patch_ask(monkeypatch, "gemini-备用")
        monkeypatch.setattr(dialogs, "showerror", lambda *a, **kw: pytest.fail("不该报错"))
        host = Host()
        cfg = FakeCfg()
        form = FakeForm(cfg)

        host._ai_create_profile(form)

        assert host.reopened == ["已新建并切换到档案《gemini-备用》"], cfg.profile_names_list

    def test_create_cancelled_does_nothing(self, monkeypatch):
        self._patch_ask(monkeypatch, "")
        host = Host()
        form = FakeForm(FakeCfg())

        host._ai_create_profile(form)

        assert host.reopened == []

    def test_rename_profile(self, monkeypatch):
        self._patch_ask(monkeypatch, "work-2")
        monkeypatch.setattr(dialogs, "showerror", lambda *a, **kw: pytest.fail("不该报错"))
        host = Host()
        cfg = FakeCfg(active="work")
        form = FakeForm(cfg, active="work")

        host._ai_rename_profile(form)

        assert cfg.renamed == [("work", "work-2")]
        assert host.reopened == ["档案已重命名为《work-2》"]

    def test_rename_to_same_name_is_noop(self, monkeypatch):
        """没改名就回车 ⇒ 不该调底层（否则会报"名字冲突"这种莫名其妙的错）。"""
        self._patch_ask(monkeypatch, "work")
        host = Host()
        cfg = FakeCfg(active="work")
        form = FakeForm(cfg, active="work")

        host._ai_rename_profile(form)

        assert cfg.renamed == []
        assert host.reopened == []

    def test_rename_failure_reports(self, monkeypatch):
        errors: list = []
        self._patch_ask(monkeypatch, "冲突名")
        monkeypatch.setattr(dialogs, "showerror", lambda *a, **kw: errors.append(a))
        host = Host()
        form = FakeForm(FakeCfg(active="work", boom="rename"), active="work")

        host._ai_rename_profile(form)

        assert errors
        assert host.reopened == []

    def test_delete_requires_confirmation(self, monkeypatch):
        """删除档案会连它的 API Key 一起删 —— 必须确认。"""
        asked: list = []
        monkeypatch.setattr(dialogs, "askyesno", lambda *a, **kw: asked.append(a) or False)
        host = Host()
        cfg = FakeCfg(active="work")
        form = FakeForm(cfg, active="work")

        host._ai_delete_profile(form)

        assert asked, "删除没有二次确认"
        assert cfg.deleted == [], "用户点了否却删了"

    def test_delete_confirmed(self, monkeypatch):
        monkeypatch.setattr(dialogs, "askyesno", lambda *a, **kw: True)
        monkeypatch.setattr(dialogs, "showerror", lambda *a, **kw: pytest.fail("不该报错"))
        host = Host()
        cfg = FakeCfg(active="work")
        form = FakeForm(cfg, active="work")

        host._ai_delete_profile(form)

        assert cfg.deleted == ["work"]
        assert host.reopened == ["已删除档案《work》"]

    def test_delete_failure_reports(self, monkeypatch):
        errors: list = []
        monkeypatch.setattr(dialogs, "askyesno", lambda *a, **kw: True)
        monkeypatch.setattr(dialogs, "showerror", lambda *a, **kw: errors.append(a))
        host = Host()
        form = FakeForm(FakeCfg(active="work", boom="delete"), active="work")

        host._ai_delete_profile(form)

        assert errors
        assert host.reopened == []


class TestRefreshAIClientAndReopen:
    def test_refresh_ai_client_rebuilds(self, monkeypatch):
        built: list = []

        class FakeClient:
            def __init__(self, config):
                built.append(config)

        import app.ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "AIClient", FakeClient)
        host = Host()
        host.config = object()

        AISettingsMixin._refresh_ai_client(host)

        assert built == [host.config]
        assert host.ai_client is not None

    def test_refresh_failure_is_logged_not_raised(self, monkeypatch):
        """重建失败只记日志 —— 配置已经保存成功，不该因为重建失败让用户以为没保存。"""

        class Boom:
            def __init__(self, config):
                raise RuntimeError("没有可用 provider")

        import app.ai_client as ai_client_mod

        monkeypatch.setattr(ai_client_mod, "AIClient", Boom)
        host = Host()
        host.config = object()

        AISettingsMixin._refresh_ai_client(host)

        assert any("重建 AI 客户端失败" in line for line in host.logs)

    def test_reopen_settings_destroys_and_rebuilds(self):
        host = Host()
        host._show_settings = lambda: host.logs.append("reopened")
        dialog = FakeDialog()

        AISettingsMixin._reopen_settings(host, dialog, "已切换")

        assert dialog.destroyed
        assert "reopened" in host.logs
        assert "已切换" in host.logs


@pytest.mark.skipif(not _tk_harness.tk_available(), reason="无显示环境")
class TestAskTextTk:
    """`_ask_text` 是设置页取名字的唯一入口（新建/重命名档案都走它）。

    ❗ 用**点按钮**而不是 `event_generate("<Return>")` 驱动：
    未聚焦/未映射的 Toplevel 上，合成键盘事件不保证命中绑定，
    用例会退化成"等 3 秒超时"，然后以 `application has been destroyed` 假失败。
    """

    @staticmethod
    def _find(widget, predicate):
        for child in widget.winfo_children():
            if predicate(child):
                return child
            found = TestAskTextTk._find(child, predicate)
            if found is not None:
                return found
        return None

    @classmethod
    def _entry(cls, win):
        from tkinter import ttk

        return cls._find(win, lambda w: isinstance(w, ttk.Entry))

    @classmethod
    def _button(cls, win, text: str):
        from tkinter import ttk

        return cls._find(win, lambda w: isinstance(w, ttk.Button) and w.cget("text") == text)

    def _run(self, *, fill=None, press="确定", initial=""):
        """开对话框 → 填内容 → 点按钮 → 返回值。"""
        seen: dict = {}
        root = _tk_harness.create_root()

        def act():
            win = next((c for c in root.winfo_children() if isinstance(c, tk.Toplevel)), None)
            if win is None:  # pragma: no cover
                return
            entry = self._entry(win)
            seen["initial"] = entry.get()
            if fill is not None:
                entry.delete(0, tk.END)
                entry.insert(0, fill)
            button = self._button(win, press)
            if button is None:  # pragma: no cover - 按钮缺失说明实现坏了
                win.destroy()
                return
            button.invoke()

        root.after(80, act)
        root.after(3000, root.destroy)
        try:
            seen["value"] = mod._ask_text(root, "重命名", "新的名称：", initial=initial)
        finally:
            try:
                root.destroy()
            except tk.TclError:  # pragma: no cover - 超时已销毁
                pass
        return seen

    def test_confirm_returns_stripped_text(self):
        seen = self._run(fill="  work  ")

        assert seen["value"] == "work", "首尾空白没被去掉（会建出带空格的档案名）"

    def test_initial_value_is_prefilled(self):
        """重命名时要把旧名字填进输入框，否则用户每次都要重打。"""
        seen = self._run(press="取消", initial="work-old")

        assert seen["initial"] == "work-old"

    def test_cancel_returns_empty(self):
        seen = self._run(fill="不会用到", press="取消")

        assert seen["value"] == "", "取消必须返回空串（调用方据此判断'没改名'）"


class TestProviderRegistryEdgeCases:
    """注册表的两个边角：重名与"默认模型不在模型列表里"。

    都通过替换 `specs_for_ui` 构造 —— 真实注册表里这两个情况不该出现，
    但**注册表是可扩展的**（第三方 provider 插件），所以代码必须有兜底，
    而兜底最容易在重构时被删掉。
    """

    def test_duplicate_labels_are_disambiguated(self, monkeypatch):
        """两个 provider 同名时，下拉项要追加 key 区分 —— 否则用户选不了第二个。"""
        monkeypatch.setattr(
            mod,
            "specs_for_ui",
            lambda: [
                {"key": "aaa", "name": "同名服务", "models": [], "default_model": ""},
                {"key": "bbb", "name": "同名服务", "models": [], "default_model": ""},
            ],
        )

        labels, mapping = mod.provider_choices()

        assert labels == ["同名服务", "同名服务 [bbb]"]
        assert mapping["同名服务"] == "aaa", "第一项被覆盖了"
        assert mapping["同名服务 [bbb]"] == "bbb"

    def test_default_model_is_prepended_when_missing(self, monkeypatch):
        """默认模型不在候选列表里时要插到最前 —— 否则下拉默认选中别的模型。"""
        monkeypatch.setattr(
            mod,
            "specs_for_ui",
            lambda: [{"key": "k", "name": "K", "models": ["m1", "m2"], "default_model": "m0"}],
        )

        assert mod.models_for_provider("k") == ["m0", "m1", "m2"]

    def test_default_model_already_present_is_not_duplicated(self, monkeypatch):
        monkeypatch.setattr(
            mod,
            "specs_for_ui",
            lambda: [{"key": "k", "name": "K", "models": ["m0", "m1"], "default_model": "m0"}],
        )

        assert mod.models_for_provider("k") == ["m0", "m1"]

    def test_unknown_provider_gets_custom_model(self):
        assert mod.models_for_provider("不存在的 provider") == ["custom-model"]
