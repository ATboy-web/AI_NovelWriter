"""迭代探针 2：端到端串联路径与集成点边界。

与 boundary_probe.py 的区别：那份打单点，这份**打串联**（谁把谁的数据吃掉）。
覆盖：
  A. 自学习闭环：finalize_chapter → 落盘 → get_writing_context → 回灌
  B. 解析器在调用点的类型契约（dict-期望 vs list-期望）
  C. 章节窗口过滤的"距离"语义
  D. 空/异常输入下不产生脏数据
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + ("" if cond else f"  {detail}"))
    if not cond:
        FAILS.append(f"{name}: {detail}")


print("=" * 70)
print("A. 自学习闭环端到端")
print("=" * 70)
try:
    from app.writing_skills import WritingSkillManager

    wsm = WritingSkillManager()
    body = "他推开门，风灌进来。" * 60

    # A1 高分章节应写入 success_pattern，且权重 > 0.6
    wsm.learn_from_chapter(body, 10, ["张三"], success=True, quality=95)
    wins = wsm.time_memory.query(memory_type="success_pattern", limit=20)
    q95 = [m for m in wins if "评分95" in m["content"]]
    check("A1 高分章节写入 success_pattern", bool(q95), f"共 {len(wins)} 条")
    if q95:
        imp = q95[0].get("importance", 0)
        check("A2 高分权重 > 0.6（评分真的影响权重）", imp > 0.6, f"importance={imp}")
    else:
        check("A2 高分权重 > 0.6（评分真的影响权重）", False, "上一步已失败")

    # A3 低分章节应被记为 failure_pattern（而非"什么都不做"）
    wsm.learn_from_chapter(body, 11, ["张三"], success=False, quality=40)
    misses = wsm.time_memory.query(memory_type="failure_pattern", limit=20)
    check("A3 低分章节写入 failure_pattern", bool(misses), f"共 {len(misses)} 条")
    if misses:
        imp40 = misses[0].get("importance", 0)
        imp95 = q95[0].get("importance", 0) if q95 else 0.9
        check(
            "A3b 失败记忆与成功记忆分开存放",
            all("未达标" in m["content"] for m in misses),
            f"{[m['content'][:30] for m in misses]}",
        )
        check(
            "A3c 失败记忆权重随低分上升（越差越该记住）", imp40 > 0.5, f"importance={imp40}（成功侧 95 分为 {imp95}）"
        )
    else:
        check("A3b 失败记忆与成功记忆分开存放", False, "上一步已失败")
        check("A3c 失败记忆权重随低分上升（越差越该记住）", False, "上一步已失败")

    # A3d get_writing_context 必须把失败模式也读回来
    ctx_fail = wsm.get_writing_context(character="张三", chapter=12)
    check("A3d 未达标章节被回灌进上下文", "未达标章节" in ctx_fail, f"上下文前 200 字：{ctx_fail[:200]!r}")

    # A4 get_writing_context 必须真的把成功模式带出来
    ctx = wsm.get_writing_context(character="张三", chapter=12)
    check(
        "A4 get_writing_context 带上近期成功模式",
        "近期成功模式" in ctx,
        f"上下文长度 {len(ctx)}，前 120 字：{ctx[:120]!r}",
    )

    # A5 quality=None 时不应崩、也不应写入带评分的记录
    wsm.learn_from_chapter(body, 12, ["张三"], success=True)
    wins3 = wsm.time_memory.query(memory_type="success_pattern", limit=50)
    no_score = [m for m in wins3 if "评分" not in m["content"]]
    check("A5 quality=None 仍写入但不带评分", bool(no_score), f"无评分记录 {len(no_score)} 条")
    for m in no_score:
        if m.get("importance") != 0.6:
            check("A5b 无评分时权重回落 0.6", False, f"importance={m.get('importance')}")
            break
    else:
        check("A5b 无评分时权重回落 0.6", True)
except Exception as e:  # noqa: BLE001
    import traceback

    check("A 段整体可执行", False, f"{type(e).__name__}: {e}\n{traceback.format_exc()[-600:]}")

print()
print("=" * 70)
print("B. 解析器调用点的类型契约")
print("=" * 70)
try:
    from app.character_ui import _auto_detect_characters  # type: ignore
except Exception:  # noqa: BLE001
    _auto_detect_characters = None

try:
    from app.parsing import parse_json_response

    # B1 字符串数组：只保留 str，且过滤空白
    r = parse_json_response('["张三", "  ", "李四"]', [], is_list=True)
    kept = [n for n in r if isinstance(n, str) and n.strip()] if isinstance(r, list) else []
    check("B1 str 数组过滤空白", kept == ["张三", "李四"], f"{kept}")

    # B2 AI 返回对象数组（常见误返）→ 收敛后应被过滤掉而不是崩
    r = parse_json_response('[{"name": "张三"}]', [], is_list=True)
    kept = [n for n in r if isinstance(n, str) and n.strip()] if isinstance(r, list) else []
    check("B2 对象数组被过滤为不新增（不崩）", kept == [], f"{kept}")

    # B3 **修正后的断言**：`is_list=False` 只"优先找 {}"，**不承诺拒收顶层数组**
    # （文档只承诺反向：is_list=True 时拒收 dict）。所以这里验证的是
    # "调���点必须自己守卫"这条契约 —— 直接钉住两个已加守卫的调用点。
    r = parse_json_response("[1,2,3]", None)
    check("B3 is_list=False 不拒顶层数组（文档契约，钉住）", isinstance(r, list), f"{r!r}")

    import inspect  # noqa: E402

    import app.novel_agent as na  # noqa: E402

    src = inspect.getsource(na.NovelAgent)
    check(
        "B3b _world_builder 对非 dict 有守卫",
        "not isinstance(settings, dict)" in src,
        "未找到 isinstance(settings, dict) 守卫",
    )
    check(
        "B3c 风格分析对非 dict 有守卫",
        "not isinstance(style, dict)" in src,
        "未找到 isinstance(style, dict) 守卫",
    )

    # B4 期望 list 时拿到 dict 必须安全
    r = parse_json_response('{"a":1}', [], is_list=True)
    check("B4 期望 list 时顶层对象被拒", not isinstance(r, dict), f"{r!r}")
except Exception as e:  # noqa: BLE001
    check("B 段整体可执行", False, f"{type(e).__name__}: {e}")

print()
print("=" * 70)
print("C. 章节窗口距离语义")
print("=" * 70)
try:
    from app.writing_skills import TimeAwareMemory

    tm = TimeAwareMemory()
    tm.add_memory("第 10 章", memory_type="success_pattern", chapter=10)
    tm.add_memory("第 100 章", memory_type="success_pattern", chapter=100)
    tm.add_memory("第 500 章", memory_type="success_pattern", chapter=500)

    got = tm.query(memory_type="success_pattern", chapter=300, chapter_window=200)
    contents = " ".join(m["content"] for m in got)
    check("C1 窗口内（100 章，距离 200）在", "第 100 章" in contents, f"{contents!r}")
    check("C2 窗口外（10 章，距离 290）不在", "第 10 章" not in contents, f"{contents!r}")
    check("C3 窗口边缘（500 章，距离 200）在", "第 500 章" in contents, f"{contents!r}")

    got2 = tm.query(memory_type="success_pattern", chapter=None)
    check("C4 不传 chapter 时不过滤（旧行为）", len(got2) >= 3, f"{len(got2)}")
except Exception as e:  # noqa: BLE001
    check("C 段整体可执行", False, f"{type(e).__name__}: {e}")

print()
print("=" * 70)
print("D. 空/异常输入不产生脏数据")
print("=" * 70)
try:
    from app.writing_skills import WritingSkillManager as WSM

    w = WSM()
    before = len(w.time_memory.query(memory_type="success_pattern", limit=999))
    for bad in ("", "   ", "\n\n\n"):
        try:
            w.learn_from_chapter(bad, 1, ["张三"], success=True)
        except Exception as e:  # noqa: BLE001
            check(f"D1 空正文 {bad!r} 不抛异常", False, f"{type(e).__name__}: {e}")
            break
    else:
        check("D1 空/空白正文不抛异常", True)
    after = len(w.time_memory.query(memory_type="success_pattern", limit=999))
    check("D2 空正文不写入脏记忆", after == before, f"{before} → {after}")
except Exception as e:  # noqa: BLE001
    check("D 段整体可执行", False, f"{type(e).__name__}: {e}")

print()
print("=" * 70)
if FAILS:
    print(f"❌ {len(FAILS)} 项未通过：")
    for x in FAILS:
        print(f"   - {x}")
    sys.exit(1)
print("✅ 迭代探针 2 全部通过")
