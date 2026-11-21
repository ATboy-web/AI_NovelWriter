"""两个 FastAPI 服务入口的冒烟测试（进程隔离）。

为什么必须存在：`backend/ai-service/app/main.py` 与 `backend/novel-service/app/main.py`
此前在 CI 里**从未被导入过** —— dev 依赖缺 pydantic-settings / uvicorn，
两个服务连 import 都过不去，所有"服务能起来"的假设都没有测试兜底。

为什么用子进程：两个服务的包名都叫 `app`，与桌面端 `app/` 同名。
在同一 pytest 进程里导入会污染 sys.modules，进而影响桌面端测试。
子进程 + cwd=服务目录，恰好也复现了"独立启动服务"的真实路径引导场景
（历史缺陷：只把 backend/shared 自身加进 sys.path，导致 `from shared.xxx import ...`
在独立启动时 ModuleNotFoundError）。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_SERVICES = ["ai-service", "novel-service"]

_PROBE = r"""
import json, traceback
out = {}
try:
    from fastapi.testclient import TestClient

    # 顺序即真实启动顺序：服务包 __init__ 负责把 backend/shared 挂上 sys.path，
    # 因此必须先导入 app.main，再校验 shared 是否可用。
    from app.main import app
    import shared.api_errors as _ae
    out["shared_import_ok"] = callable(_ae.internal_error)
    with TestClient(app) as c:
        r = c.get("/health")
        out["health_status"] = r.status_code
        out["health_body"] = r.json()
        out["unknown_path_status"] = c.get("/__definitely_not_a_route__").status_code
    schema = app.openapi()
    out["openapi_paths"] = len(schema.get("paths", {}))
    out["route_count"] = len(app.routes)
    out["ok"] = True
except Exception:
    out["ok"] = False
    out["error"] = traceback.format_exc()[-3000:]
print("PROBE_JSON=" + json.dumps(out, ensure_ascii=False))
"""


def _run_probe(service: str) -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(_BACKEND_DIR / service),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=180,
    )
    line = next((ln for ln in (proc.stdout or "").splitlines() if ln.startswith("PROBE_JSON=")), None)
    if line is None:
        pytest.fail(f"{service} 探针无输出\nstdout={proc.stdout}\nstderr={proc.stderr}")
    return json.loads(line[len("PROBE_JSON=") :])


@pytest.fixture(scope="module", params=_SERVICES)
def service_probe(request):
    return request.param, _run_probe(request.param)


def test_service_imports_standalone(service_probe):
    name, res = service_probe
    assert res.get("ok") is True, f"{name} 无法独立导入：\n{res.get('error')}"


def test_shared_package_resolvable_standalone(service_probe):
    """守卫：独立启动时 `from shared.api_errors import ...` 必须可用。"""
    name, res = service_probe
    assert res.get("shared_import_ok") is True, f"{name} 定位不到 backend/shared 包"


def test_health_endpoint(service_probe):
    name, res = service_probe
    assert res.get("health_status") == 200, f"{name} /health 非 200"
    body = res.get("health_body") or {}
    assert body.get("status") == "healthy"
    assert body.get("version")
    assert body.get("timestamp")


def test_openapi_schema_builds(service_probe):
    name, res = service_probe
    assert (res.get("openapi_paths") or 0) > 0, f"{name} OpenAPI 无路径，路由未注册"
    assert (res.get("route_count") or 0) > 5, f"{name} 路由数量异常"


def test_unknown_path_is_not_served(service_probe):
    """未知且非公开的路径必须被拒绝。

    注意口径：认证中间件先于路由匹配执行，所以未带凭据时是 401 而不是 404；
    关闭认证的环境则为 404。两者都可接受，唯独不能是 2xx。
    """
    name, res = service_probe
    assert res.get("unknown_path_status") in (401, 403, 404), (
        f"{name} 未知路径未被拒绝：{res.get('unknown_path_status')}"
    )
