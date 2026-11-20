"""`tests/_tk_harness.py` 的契约 —— 这一层存在的意义就是"把 Tk 偶发失败说清楚"。

## 背景（这是本次排查的结论摘要）

全量套件曾偶发失败：

```
_tkinter.TclError: Can't find a usable init.tcl in the following directories:
  {C:\\...\\Python311\\tcl\\tcl8.6}
init.tcl: couldn't read file ".../init.tcl": No error
```

已确证的事实（见 `docs` 里的排查记录）：

| 事实 | 依据 |
|---|---|
| **每次 `tk.Tk()` 都会新建 Tcl 解释器并重新从磁盘读 init.tcl** | 一次约 25 KB；全量套件的读次数 = 创建次数（实测单文件 43 用例 → 27 次） |
| **不是句柄泄漏** | 连续 4000 次创建销毁，句柄稳定在 184；再压 900 个文件句柄仍能建窗口 |
| **不是模块副作用 / 单线程可稳定复现** | 导入全部 98 个 app 模块后连建 400 次，0 失败 |
| **不是路径错误** | 错误信息里给出的目录正是正确的 Tcl 库目录 |
| **是"读"失败且 errno 为 0** | `couldn't read file ...: No error` ⇒ Win32 返回失败但未置错误码（过滤驱动/瞬时资源） |

因此代码层面能做的三件事，全部落在这一层：

1. **单一入口**：原先 7 个测试文件各写一份 `tk.Tk()` + `except: pytest.skip`，
   同一个故障有七种表现（其中 `test_panel_layout` 一 skip，面板布局回归就没人守了）；
2. **重试 + 留痕**：瞬时失败被吸收，但**必须记录**（否则"静默恢复"又是一次掩盖）；
3. **判据收窄**：只有"确实建不出窗口"才允许跳过；面板自身写坏必须让测试失败。
"""

from __future__ import annotations

import json
import pathlib
import re
import tkinter as tk

import _tk_harness
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


class _FakeTkModule:
    """替身：`tk.Tk()` 前 `fail_times` 次失败，之后返回可用的假根窗口。"""

    def __init__(self, fail_times: int, error: BaseException | None = None):
        self.fail_times = fail_times
        self.calls = 0
        self.error = error or tk.TclError('invalid command name "tcl_findLibrary"')

    def Tk(self):  # noqa: N802 - 模拟 tkinter 的 PascalCase 接口
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.error
        return _FakeRoot()


class _FakeRoot:
    def __init__(self):
        self.withdrawn = False
        self.destroyed = False

    def withdraw(self):
        self.withdrawn = True

    def destroy(self):
        self.destroyed = True


@pytest.fixture(autouse=True)
def _clean_logs(monkeypatch, tmp_path):
    """把两份日志指到临时目录，避免污染真实排查文件。"""
    monkeypatch.setattr(_tk_harness, "FAILURE_LOG", tmp_path / "failure.jsonl")
    monkeypatch.setattr(_tk_harness, "RETRY_LOG", tmp_path / "retry.jsonl")
    _tk_harness.tk_available.cache_clear()
    yield
    _tk_harness.tk_available.cache_clear()


class TestCreateRoot:
    def test_returns_withdrawn_root(self):
        root = _tk_harness.create_root()
        try:
            assert root.winfo_exists(), "应返回可用的根窗口"
            assert root.winfo_ismapped() == 0, "根窗口应处于隐藏状态（withdraw 生效）"
        finally:
            root.destroy()

    def test_transient_failure_is_absorbed_and_recorded(self, monkeypatch, tmp_path):
        """前 1 次失败、第 2 次成功 ⇒ 返回可用窗口 **且留下重试记录**。

        这条是关键：**不允许静默恢复**。若不记录，我们会误判"问题已消失"。
        """
        fake = _FakeTkModule(fail_times=1)
        monkeypatch.setattr(_tk_harness, "tk", fake)

        root = _tk_harness.create_root()
        assert isinstance(root, _FakeRoot), "重试后应成功返回"
        assert fake.calls == 2, f"应尝试 2 次，实际 {fake.calls}"

        log = _tk_harness.RETRY_LOG
        assert log.exists(), "重试成功也必须留痕"
        record = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
        assert record["failed_attempts"] == 1
        assert "tcl_findLibrary" in record["trace"][0]["error"]
        assert record["trace"][0]["elapsed_ms"] >= 0

    def test_persistent_failure_raises_with_full_context(self, monkeypatch):
        """始终失败 ⇒ 抛 `TkUnavailable`，并写出**可定因**的现场。"""
        fake = _FakeTkModule(fail_times=99)
        monkeypatch.setattr(_tk_harness, "tk", fake)

        with pytest.raises(_tk_harness.TkUnavailable) as exc:
            _tk_harness.create_root(attempts=3, retry_delay=0)
        assert fake.calls == 3
        assert "3 次尝试" in str(exc.value)

        log = _tk_harness.FAILURE_LOG
        assert log.exists(), '失败现场必须落盘，否则又回到"查不出原因"'
        record = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
        for key in ("error", "current_test", "argv", "cwd", "handles", "attempts"):
            assert key in record, f"现场缺少 {key}"
        # init.tcl 的可读性结论必须有（读成功给 True，定位失败给 read_error）
        assert "init_tcl_read_ok" in record or "init_tcl_read_error" in record

    def test_error_is_chained(self, monkeypatch):
        """保留原始异常链 —— 排查时要能看到 Tcl 的原文。"""
        fake = _FakeTkModule(fail_times=99)
        monkeypatch.setattr(_tk_harness, "tk", fake)
        with pytest.raises(_tk_harness.TkUnavailable) as exc:
            _tk_harness.create_root(attempts=1, retry_delay=0)
        assert isinstance(exc.value.__cause__, tk.TclError)


class TestTkAvailable:
    def test_true_when_usable(self, monkeypatch):
        monkeypatch.setattr(_tk_harness, "tk", _FakeTkModule(fail_times=0))
        assert _tk_harness.tk_available() is True

    def test_false_when_broken(self, monkeypatch):
        monkeypatch.setattr(_tk_harness, "tk", _FakeTkModule(fail_times=99))
        assert _tk_harness.tk_available() is False

    def test_result_is_cached(self, monkeypatch):
        """只探测一次：探测本身也是一次"新建解释器"，不该在每个模块/类上重做。"""
        fake = _FakeTkModule(fail_times=0)
        monkeypatch.setattr(_tk_harness, "tk", fake)
        _tk_harness.tk_available()
        _tk_harness.tk_available()
        _tk_harness.tk_available()
        assert fake.calls == 1, f"应只探测 1 次，实际 {fake.calls}"


class TestSingleEntryPointGuard:
    """守卫：测试代码里不得再直接 `tk.Tk()`（绕过重试与留痕）。

    双向：白名单指向的写法必须**仍然存在于 harness 内**，否则说明清单过期。
    """

    ALLOWED_FILES = ("tests/_tk_harness.py", "tests/test_tk_harness.py")

    @staticmethod
    def _test_files() -> list[pathlib.Path]:
        return [p for p in sorted((REPO / "tests").rglob("*.py")) if "__pycache__" not in str(p)]

    def test_no_direct_tk_root_creation_outside_harness(self):
        pattern = re.compile(r"(?<![\w.])tk(?:inter)?\.Tk\(\)")
        offenders = []
        for path in self._test_files():
            rel = path.relative_to(REPO).as_posix()
            if rel in self.ALLOWED_FILES:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#") or '"""' in stripped:
                    continue
                if pattern.search(stripped):
                    offenders.append(f"{rel}:{number} {stripped[:70]}")
        assert not offenders, "以下位置直接建 Tk 根窗口，绕过了 _tk_harness（无重试、无留痕）：\n  " + "\n  ".join(
            offenders
        )

    def test_harness_itself_still_creates_roots(self):
        """反向断言：白名单里的写法必须真的存在（防清单过期）。"""
        source = (REPO / "tests" / "_tk_harness.py").read_text(encoding="utf-8")
        assert "tk.Tk()" in source, "harness 里应保留唯一的 tk.Tk() 调用"

    def test_no_duplicated_availability_probes(self):
        """不得再有自写的 `_tk_available()` —— 判据不一致的源头。"""
        offenders = []
        for path in self._test_files():
            rel = path.relative_to(REPO).as_posix()
            if rel in self.ALLOWED_FILES:
                continue
            text = path.read_text(encoding="utf-8")
            if "def _tk_available(" in text:
                offenders.append(rel)
        assert not offenders, f"这些文件仍自写探测函数，应改用 _tk_harness.tk_available()：{offenders}"

    def test_no_bare_tk_skip_outside_harness(self):
        """`except ...: pytest.skip("无可用显示环境")` 这种"把环境问题当无需测试"的写法要绝迹。"""
        pattern = re.compile(r"无可用(?:显示环境|Tk 环境)")
        offenders = []
        for path in self._test_files():
            rel = path.relative_to(REPO).as_posix()
            if rel in self.ALLOWED_FILES:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line) and "pytest.skip" in line:
                    offenders.append(f"{rel}:{number} {line.strip()[:70]}")
        assert not offenders, "仍有把 Tk 环境问题转成 skip 的旧写法：\n  " + "\n  ".join(offenders)
