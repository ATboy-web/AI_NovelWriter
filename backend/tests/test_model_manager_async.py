"""P2-9 回归：本地模型扫描不得阻塞事件循环。

`_scan_local_models` 里 Path.exists / rglob / stat 全是阻塞 IO。
旧实现直接在 async 函数体内执行，磁盘慢时会卡住整个事件循环
（所有并发请求一起等）。现改为 asyncio.to_thread 下沉到工作线程。

同样用子进程隔离：ai-service 的包名 `app` 与桌面端同名。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent

_PROBE = r"""
import asyncio, json, tempfile, threading, traceback
from pathlib import Path
out = {}
try:
    from app.core import model_manager as mm

    tmp = Path(tempfile.mkdtemp())
    (tmp / "fake-model.gguf").write_bytes(b"x" * 16)
    mm.settings.LOCAL_MODEL_PATH = str(tmp)

    mgr = mm.ModelManager()
    main_thread = threading.get_ident()
    seen = {}
    original = mgr._scan_local_models_sync

    def spy():
        seen["worker_thread"] = threading.get_ident()
        return original()

    mgr._scan_local_models_sync = spy
    asyncio.run(mgr._scan_local_models())
    out["main_thread"] = main_thread
    out["worker_thread"] = seen.get("worker_thread")
    out["discovered"] = sorted(mgr.models.keys())
    out["ok"] = True
except Exception:
    out["ok"] = False
    out["error"] = traceback.format_exc()[-3000:]
print("PROBE_JSON=" + json.dumps(out, ensure_ascii=False))
"""


@pytest.fixture(scope="module")
def scan_probe():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(_BACKEND_DIR / "ai-service"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=180,
    )
    line = next((ln for ln in (proc.stdout or "").splitlines() if ln.startswith("PROBE_JSON=")), None)
    if line is None:
        pytest.fail(f"探针无输出\nstdout={proc.stdout}\nstderr={proc.stderr}")
    return json.loads(line[len("PROBE_JSON=") :])


def test_scan_runs_in_worker_thread(scan_probe):
    assert scan_probe.get("ok") is True, scan_probe.get("error")
    assert scan_probe.get("worker_thread") is not None, "同步扫描实现未被调用"
    assert scan_probe["worker_thread"] != scan_probe["main_thread"], (
        "阻塞扫描仍在事件循环线程里执行（asyncio.to_thread 被回退了）"
    )


def test_scan_still_discovers_models(scan_probe):
    """行为不变：换线程不能改变扫描结果。"""
    assert scan_probe.get("discovered") == ["local_fake-model"]
