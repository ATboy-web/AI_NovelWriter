"""`ToolkitUIMixin._run_cloud_transfer` 的四条路径测试。

## 为什么值得测

上传与下载此前是两段逐字相同的闭包，收敛成一个方法后，**线程启动、成功、
失败、异常兜底**四条路径只有一份实现 —— 也就只有这一处能测。
这里用「同步线程替身」把异步依赖摊平，用假 `safe_after` 直接执行回调，
因此在无显示环境也能完整验证（CI 计入）。

覆盖点：
- 成功：日志两条（开始 / 完成）+ showinfo
- 失败（action 返回 False）：日志两条 + showerror
- 异常：不抛到线程外，转成 showerror("错误")
- 异常变量必须被正确捕获（`except ... as exc` 的 exc 在块外会被删除，
  若不绑定默认参数，延迟回调会拿不到值）
"""

from __future__ import annotations

import pytest

from app import toolkit_ui
from app.toolkit_ui import ToolkitUIMixin


class _SyncThread:
    """同步执行的线程替身：start() 立即跑完 target。"""

    def __init__(self, target=None, daemon=None, **kwargs):
        self._target = target

    def start(self):
        if self._target:
            self._target()


class _Host(ToolkitUIMixin):
    def __init__(self):
        self.root = object()
        self.cloud_storage = object()
        self.logs: list[str] = []

    def _log(self, message: str) -> None:
        self.logs.append(message)


@pytest.fixture
def host():
    return _Host()


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    """线程同步化 + 弹窗与 safe_after 改成立即执行。"""
    monkeypatch.setattr(toolkit_ui.threading, "Thread", _SyncThread)
    monkeypatch.setattr(toolkit_ui, "safe_after", lambda _w, fn: fn())

    calls: list[tuple] = []
    monkeypatch.setattr(toolkit_ui.dialogs, "showinfo", lambda title, msg: calls.append(("info", title, msg)))
    monkeypatch.setattr(toolkit_ui.dialogs, "showerror", lambda title, msg: calls.append(("error", title, msg)))
    return calls


ARGS = dict(
    started="开始上传到 A...",
    done_log="上传成功！",
    fail_log="上传失败",
    ok_text="小说已上传到 A",
    fail_text="上传失败，请检查网络和配置",
)


class TestCloudTransfer:
    def test_success_path(self, host, _patch):
        host._run_cloud_transfer(**ARGS, action=lambda: True)
        assert host.logs == ["开始上传到 A...", "上传成功！"]
        assert _patch == [("info", "成功", "小说已上传到 A")]

    def test_failure_path(self, host, _patch):
        host._run_cloud_transfer(**ARGS, action=lambda: False)
        assert host.logs == ["开始上传到 A...", "上传失败"]
        assert _patch == [("error", "失败", "上传失败，请检查网络和配置")]

    def test_exception_is_contained(self, host, _patch):
        def boom():
            raise RuntimeError("网络中断")

        host._run_cloud_transfer(**ARGS, action=boom)
        # 只记了"开始"，没有"成功/失败"——异常在 try 内被兜住
        assert host.logs == ["开始上传到 A..."]
        assert _patch and _patch[0][0] == "error"
        assert _patch[0][1] == "错误"
        assert "网络中断" in _patch[0][2]

    def test_action_invoked_once(self, host):
        counter = {"n": 0}

        def action():
            counter["n"] += 1
            return True

        host._run_cloud_transfer(**ARGS, action=action)
        assert counter["n"] == 1
