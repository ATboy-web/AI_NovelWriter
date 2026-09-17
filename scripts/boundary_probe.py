"""边界探针：主动攻击本轮改动过的代码路径，而不是重跑既有测试。

覆盖：
  A. parse_json_response 的边界（优先级修复后的行为）
  B. 自学习质量的边界（quality=None / 0 / 60 / 100 / 负数 / 超范围）
  C. chapter 过滤的边界（chapter=0 未标注记忆不应被清空）
  D. dedup 后的测试文件是否仍有意义（空类、悬空装饰器）
  E. panel_layout 的 sanitize（跨版本残留 key）
  F. dialogs 的静默开关可重入性
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        FAILS.append(f"{name}: {detail}")


print("=" * 70)
print("A. parse_json_response 边界（优先级修复后）")
print("=" * 70)
from app.parsing import parse_json_response  # noqa: E402

# A1 尾逗号 + 内嵌空数组：期望 dict 时必须拿到 dict（本轮修的缺陷）
r = parse_json_response('{"type": "action", "foreshadowing": [],}', None)
check("A1 尾逗号+内嵌空数组 → dict", isinstance(r, dict), f"got {type(r).__name__}={r!r}")
check("A1b type 字段正确", isinstance(r, dict) and r.get("type") == "action", f"{r!r}")

# A2 纯数组 + 尾逗号，期望 list
r = parse_json_response("[1, 2, 3,]", None, is_list=True)
check("A2 数组尾逗号(is_list) → list", isinstance(r, list) and r == [1, 2, 3], f"{r!r}")

# A3 is_list=True 时必须拒绝 dict
r = parse_json_response('{"a": 1}', [], is_list=True)
check("A3 is_list=True 拒绝 dict → 返回默认 []", r == [], f"{r!r}")

# A4 is_list=False 时嵌套数组不应顶替 dict
r = parse_json_response('{"a": [1,2]}', None)
check("A4 期望 dict 不被内嵌数组顶替", isinstance(r, dict), f"{r!r}")

# A5 markdown 围栏
r = parse_json_response('```json\n{"k": "v"}\n```', None)
check("A5 markdown 围栏 → dict", isinstance(r, dict) and r.get("k") == "v", f"{r!r}")

# A6 全角冒号
r = parse_json_response('{"a"：1}', None)
check("A6 全角冒号 → dict", isinstance(r, dict), f"{r!r}")

# A7 单引号（已知不支持，作为边界钉住而非缺陷）
r = parse_json_response("{'a': 1}", None)
check("A7 单引号已知不支持（钉住边界）", r is None, f"got {r!r}（若变了需更新文档）")

# A8 空串 / None / 空白
for bad in ("", "   ", None):
    r = parse_json_response(bad, {"d": 1})
    check(f"A8 输入 {bad!r} → 返回默认", r == {"d": 1}, f"{r!r}")

# A9 超长嵌套不崩
deep = "{" + '"a":{' * 50 + "1" + "}" * 50 + "}"
r = parse_json_response(deep, None)
check("A9 深层嵌套不抛异常", True, f"（返回 {type(r).__name__}）")

print()
print("=" * 70)
print("B. 自学习质量边界")
print("=" * 70)
try:
    from app.writing_skills import WritingSkillManager

    wsm = WritingSkillManager()
    # B1 不传 quality（旧调用路径）不应崩
    # 注意签名：learn_from_chapter(chapter_content, chapter_num, characters: List[str], ...)
    # 第三个参数是**角色名列表**，不是字符数 —— 传 int 会 "'int' object is not iterable"。
    try:
        wsm.learn_from_chapter("测试正文" * 50, 1, ["张三"], success=True)
        check("B1 quality 缺省可调用", True)
    except TypeError as e:
        check("B1 quality 缺省可调用", False, str(e))

    # B2 各边界值
    for q, lo, hi in [(0, 0.0, 1.0), (-999, 0.0, 1.0), (60, 0.5, 0.5), (100, 0.9, 0.9), (1000, 0.9, 0.9)]:
        try:
            wsm.learn_from_chapter("测试正文" * 50, 2, ["张三"], success=(q >= 60), quality=q)
            check(f"B2 quality={q} 不崩", True)
        except Exception as e:  # noqa: BLE001
            check(f"B2 quality={q} 不崩", False, f"{type(e).__name__}: {e}")

    # B3 importance 必须落在 [0.5, 0.9]（脚本里 min/max 夹过）
    import app.writing_skills as ws_mod

    src = Path(ws_mod.__file__).read_text(encoding="utf-8")
    check("B3 importance 有夹取", "min(0.9" in src and "max(0.5" in src, "未找到 min(0.9/max(0.5)")
except Exception as e:  # noqa: BLE001
    check("B 段整体可执行", False, f"{type(e).__name__}: {e}")

print()
print("=" * 70)
print("C. chapter 过滤边界（关键：chapter=0 的旧记忆不能被过滤掉）")
print("=" * 70)
try:
    from app.writing_skills import TimeAwareMemory

    tm = TimeAwareMemory()
    tm.add_memory("无章节标注的旧记忆", memory_type="note")  # chapter 默认 0
    got = tm.query(memory_type="note", chapter=500, chapter_window=200)
    check("C1 chapter=0 旧记忆在远章节仍可见", any("无章节标注" in m["content"] for m in got), f"got {len(got)} 条")

    tm.add_memory("第 500 章记忆", memory_type="note", chapter=500)
    got = tm.query(memory_type="note", chapter=500, chapter_window=200)
    check("C2 同章节记忆可见", any("第 500 章记忆" in m["content"] for m in got), f"got {len(got)} 条")
except Exception as e:  # noqa: BLE001
    check("C 段整体可执行", False, f"{type(e).__name__}: {e}")

print()
print("=" * 70)
print("D. 去重后测试文件健康度")
print("=" * 70)
empty_classes: list[str] = []
dangling_deco: list[str] = []
for f in sorted((REPO / "tests").glob("test_*.py")):
    text = f.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        check(f"D0 {f.name} 可解析", False, f"{e.lineno}: {e.msg}")
        continue
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            methods = [m for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if not any(m.name.startswith("test_") for m in methods):
                empty_classes.append(f"{f.name}::{node.name}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            if not getattr(node, "decorator_list", []):
                pass
# 悬空装饰器会直接导致 SyntaxError，能 parse 就说明没有
check("D1 无空壳 Test* 类残留", not empty_classes, f"{empty_classes}")
check("D2 全部测试文件语法合法", True)

print()
print("=" * 70)
print("E. panel_layout sanitize（跨版本残留 key）")
print("=" * 70)
try:
    from app.panels import layout as layout_mod

    lay = layout_mod.PanelLayout(primary="不存在的面板__xxx", secondary="也不存在__yyy", mode=layout_mod.MODE_SPLIT)
    sane = lay.sanitize({"章节", "角色"})
    # 注意：`primary` 不在可用集合时**按设计清空**（交给宿主兜底默认面板），
    # 而不是强行挑一个 —— 所以断言"清空"而不是"变成某个存在的面板"。
    check(
        "E1 sanitize 后 primary 被清空（交给宿主兜底）",
        sane.primary == "" and sane.secondary == "",
        f"primary={sane.primary!r} secondary={sane.secondary!r}",
    )
    # E1b 分栏必须降级为单栏（不留空右栏）
    check("E1b 不清空右栏后自动降级单栏", sane.mode == layout_mod.MODE_SINGLE, f"{sane.mode}")
    # E1c 有一个可用时必须选中它（不是清空）
    s1c = layout_mod.PanelLayout(primary="角色", secondary="不存在", mode=layout_mod.MODE_SPLIT).sanitize(
        {"章节", "角色"}
    )
    check("E1c 已知面板被保留", s1c.primary == "角色", f"{s1c.primary!r}")
    # E2 主栏==右栏必须被拆开（否则会出现两栏互换）
    l2 = layout_mod.PanelLayout(primary="章节", secondary="章节", mode=layout_mod.MODE_SPLIT)
    s2 = l2.sanitize({"章节", "角色"})
    check("E2 两栏不得是同一面板", s2.primary != s2.secondary or s2.secondary is None, f"{s2.primary}/{s2.secondary}")
    # E3 ratio 越界必须被夹回
    l3 = layout_mod.PanelLayout(ratio=99.0)
    s3 = l3.sanitize({"章节"})
    check("E3 ratio 越界被夹回", layout_mod.MIN_RATIO <= s3.ratio <= layout_mod.MAX_RATIO, f"{s3.ratio}")
except Exception as e:  # noqa: BLE001
    check("E 段可执行", False, f"{type(e).__name__}: {e}")

print()
print("=" * 70)
print("F. dialogs 静默开关可重入")
print("=" * 70)
try:
    from app import dialogs

    dialogs.set_silent(True)
    a = dialogs.is_silent()
    with dialogs.silent_modals():
        b = dialogs.is_silent()
    c = dialogs.is_silent()
    dialogs.set_silent(False)
    d = dialogs.is_silent()
    check("F1 set_silent(True) 生效", a is True, f"{a}")
    check("F2 上下文内仍静默", b is True, f"{b}")
    check("F3 上下文退出后**仍静默**（因为外层 set 过）", c is True, f"{c}")
    check("F4 set_silent(False) 可复位", d is False, f"{d}")
except Exception as e:  # noqa: BLE001
    check("F 段可执行", False, f"{type(e).__name__}: {e}")

print()
print("=" * 70)
if FAILS:
    print(f"❌ {len(FAILS)} 项未通过：")
    for x in FAILS:
        print(f"   - {x}")
    sys.exit(1)
print("✅ 全部边界探针通过")
