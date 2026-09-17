"""迭代探针 3：面板/布局/事件 + 工程一致性门禁。

前两轮打的是解析与自学习，这轮打"外壳"：
  A. 事件总线：只在写盘成功后广播、订阅者为空不订阅、广播异常不影响主流程
  B. 布局持久化：往返一致、坏文件不崩
  C. 弹窗收口门禁仍然成立（没有绕过 dialogs 的 messagebox 调用）
  D. 版本号单一权威（pyproject）
  E. 根目录文档固定 6 个（README/README_EN/CHANGELOG/CONTRIBUTING/QUICKSTART/USAGE）
  F. 字体令牌门禁（无字面量残留）
"""

from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + ("" if cond else f"  {detail}"))
    if not cond:
        FAILS.append(f"{name}: {detail}")


print("=" * 70)
print("A. 事件总线")
print("=" * 70)
try:
    from app.events import bus as event_bus
    from app.events.bus import WILDCARD

    b = event_bus.EventBus()  # 实例化（`root=None` 时不做 Tk 绑定）

    # 处理器契约：handler(topic, payload) —— 不是单参 payload。
    def _rec(sink: list):
        def _h(topic, payload):
            sink.append((topic, payload))

        return _h

    # A1 订阅 + 广播（publish 返回触达的订阅者数）
    got: list = []
    b.subscribe("test.topic", _rec(got))
    n = b.publish("test.topic", {"value": 1})
    check(
        "A1 订阅者收到广播",
        bool(got) and got[0][0] == "test.topic" and got[0][1].get("value") == 1,
        f"got={got} 返回{n}",
    )
    check("A1b publish 返回触达数", n == 1, f"{n}")

    # A2 订阅者抛异常不得影响其他订阅者与发布方
    got2: list = []

    def _boom(_topic, _payload):
        raise RuntimeError("boom")

    b.subscribe("test.boom", _boom)
    b.subscribe("test.boom", _rec(got2))
    try:
        b.publish("test.boom", {"x": 1})
        check("A2 广播异常被隔离", True)
    except Exception as e:  # noqa: BLE001
        check("A2 广播异常被隔离", False, f"异常逃逸：{type(e).__name__}: {e}")
    check("A2b 异常订阅者之后的订阅者仍收到", bool(got2), f"{got2}")

    # A3 通配符
    wild: list = []
    b.subscribe(WILDCARD, _rec(wild))
    b.publish("some.other.topic", {"y": 2})
    check("A3 通配符订阅收到任意主题", bool(wild), f"{len(wild)} 条")

    # A4 无订阅者时 publish 不崩（用全新实例，避免上面 WILDCARD 订阅干扰计数）
    try:
        n = event_bus.EventBus().publish("nobody.listens.here")
        check("A4 无订阅者不崩", n == 0, f"返回 {n}")
    except Exception as e:  # noqa: BLE001
        check("A4 无订阅者不崩", False, f"{type(e).__name__}: {e}")

    # A5 unsubscribe 幂等/未订阅返回 False 而非抛异常
    try:
        r = b.unsubscribe("test.topic", _boom)
        check("A5 unsubscribe 未注册句柄不抛异常", r is False, f"{r}")
    except Exception as e:  # noqa: BLE001
        check("A5 unsubscribe 未注册句柄不抛异常", False, f"{type(e).__name__}: {e}")
except Exception as e:  # noqa: BLE001
    import traceback

    check("A 段整体可执行", False, f"{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}")

print()
print("=" * 70)
print("B. 布局持久化往返")
print("=" * 70)
try:
    from app.panels import layout as lmod

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "panel_layout.json"
        orig = lmod.PanelLayout(
            mode=lmod.MODE_SPLIT, primary="章节", secondary="角色", ratio=0.33, popped_out=["时间线"]
        )
        ok = lmod.save(orig, p)
        check("B1 save 返回 True", ok is True, f"{ok}")
        loaded = lmod.load(p)
        check("B2 mode 往返一致", loaded.mode == orig.mode, f"{loaded.mode}")
        check(
            "B3 primary/secondary 往返一致",
            (loaded.primary, loaded.secondary) == (orig.primary, orig.secondary),
            f"{loaded.primary}/{loaded.secondary}",
        )
        check("B4 ratio 往返一致", abs(loaded.ratio - orig.ratio) < 1e-9, f"{loaded.ratio}")
        check("B5 popped_out 往返一致", loaded.popped_out == orig.popped_out, f"{loaded.popped_out}")

        # B6 坏文件不崩（跨版本、手动改坏、空文件）
        for bad in ("{ not json", "", "[]", '{"mode": "不存在的模式"}'):
            p.write_text(bad, encoding="utf-8")
            try:
                got = lmod.load(p)
                check(f"B6 坏文件 {bad[:14]!r} 不崩", isinstance(got, lmod.PanelLayout), f"{type(got)}")
            except Exception as e:  # noqa: BLE001
                check(f"B6 坏文件 {bad[:14]!r} 不崩", False, f"{type(e).__name__}: {e}")

        # B7 不存在的路径
        try:
            got = lmod.load(Path(d) / "nope.json")
            check("B7 文件不存在时给默认布局", isinstance(got, lmod.PanelLayout), f"{type(got)}")
        except Exception as e:  # noqa: BLE001
            check("B7 文件不存在时给默认布局", False, f"{type(e).__name__}: {e}")
except Exception as e:  # noqa: BLE001
    check("B 段整体可执行", False, f"{type(e).__name__}: {e}")

print()
print("=" * 70)
print("C. 弹窗收口门禁")
print("=" * 70)
try:
    offenders: list[str] = []
    for f in (REPO / "app").rglob("*.py"):
        if f.name == "dialogs.py":
            continue  # dialogs 本身当然要 import messagebox
        text = f.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("showinfo", "showwarning", "showerror", "askyesno"):
                check_holder = ast.unparse(node.value)
                if "messagebox" in check_holder:
                    offenders.append(f"{f.name}:{node.lineno}")
            if isinstance(node, ast.ImportFrom) and node.module and "messagebox" in node.module:
                offenders.append(f"{f.name}:{node.lineno} (import)")
    check("C1 无业务代码直接调 messagebox", not offenders, f"{offenders[:5]}")
except Exception as e:  # noqa: BLE001
    check("C 段整体可执行", False, f"{type(e).__name__}: {e}")

print()
print("=" * 70)
print("D. 版本号单一权威")
print("=" * 70)
try:
    import tomllib

    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    ver = pyproject["project"]["version"]
    import app

    check(
        f"D1 app.__version__ 与 pyproject 一致（{ver}）",
        app.__version__ == ver,
        f"app={app.__version__} pyproject={ver}",
    )
except Exception as e:  # noqa: BLE001
    check("D 段整体可执行", False, f"{type(e).__name__}: {e}")

print()
print("=" * 70)
print("E. 根目录文档固定 6 个")
print("=" * 70)
try:
    expected = {"README.md", "README_EN.md", "CHANGELOG.md", "CONTRIBUTING.md", "QUICKSTART.md", "USAGE.md"}
    actual = {
        p.name for p in REPO.iterdir() if p.is_file() and p.suffix == ".md" and (p.name.isupper() or p.name in expected)
    }
    missing = expected - {p.name for p in REPO.iterdir() if p.is_file()}
    check("E1 六个根文档都在", not missing, f"缺失 {missing}")
    actual_md = {p.name for p in REPO.glob("*.md")}
    extra = actual_md - expected
    check("E2 没有多出来的根 .md", not extra, f"多出 {extra}")
except Exception as e:  # noqa: BLE001
    check("E 段整体可执行", False, f"{type(e).__name__}: {e}")

print()
print("=" * 70)
print("F. 字体令牌门禁（无字面量残留）")
print("=" * 70)
try:
    hits: list[str] = []
    pat = ast.parse
    for f in (REPO / "app").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        tree = pat(text)
        for node in ast.walk(tree):
            # 形如 ("Microsoft YaHei", 12) 的元组
            if isinstance(node, ast.Tuple) and len(node.elts) == 2:
                a, b = node.elts
                if (
                    isinstance(a, ast.Constant)
                    and isinstance(a.value, str)
                    and isinstance(b, ast.Constant)
                    and isinstance(b.value, int)
                    and ("YaHei" in a.value or "SimHei" in a.value or "Arial" in a.value)
                ):
                    hits.append(f"{f.name}:{node.lineno}")
    check("F1 无硬编码字体字面量", not hits, f"{hits[:5]}")
except Exception as e:  # noqa: BLE001
    check("F 段整体可执行", False, f"{type(e).__name__}: {e}")

print()
print("=" * 70)
if FAILS:
    print(f"❌ {len(FAILS)} 项未通过：")
    for x in FAILS:
        print(f"   - {x}")
    sys.exit(1)
print("✅ 迭代探针 3 全部通过")
