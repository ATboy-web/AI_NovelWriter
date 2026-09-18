"""静默吞异常登记制（v3.2 / 任务"降低运行崩坏风险"）。

## 为什么要"登记制"而不是"一律禁止"

`except ...: pass` 本身不是坏味道 —— 有些地方**必须**吞：

- `__del__` / 析构里抛异常会让解释器打印 "Exception ignored" 并可能中断清理；
- 事件广播是**旁路**，广播失败不该影响主流程（记账已经写完了）；
- `_ImportStub` 的降级是**设计**（导入失败要能继续跑，好让打包缺陷可见）。

所以"一律禁止"是错的。真正的问题是**不可见的吞**：
新加一处 `except Exception: pass` 时，没人会注意到，
于是"某个功能静默失灵"变成一个查不出来的现象 ——
本仓的小说审计里，主角锁定失效就是这么被 `pass` 吃掉的。

## 机制

| 做法 | 效果 |
|---|---|
| 所有 `except: pass` 必须登记在 `JUSTIFIED` 里，附**理由** | 新增一处 ⇒ 测试变红 ⇒ 必须显式说明"为什么这里该吞" |
| 登记项必须**真的存在** | 反向断言：修好了却忘删登记 ⇒ 也变红（防止登记表变成历史垃圾） |
| 只允许**具体异常类型**出现在"无日志"的吞里 | 宽泛的 `except Exception: pass` 要么加日志，要么收窄类型 |

## 判据的边界（说清楚，避免假阳性）

- **有日志的 `except` 不算**：`logger.warning(...)` 之后即使什么都不做，失败也已可见。
- **不是 `pass` 的不算**：例如 `except: return None`、`except: continue`
  在上下文里各自有语义，不在本守卫范围内（它们不制造"完全无声"的失败）。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
APP_DIR = REPO_ROOT / "app"
sys.path.insert(0, str(Path(__file__).parent))

#: 已核准的"无日志静默吞异常"位置 → 理由。键为 `相对路径:行号`。
#:
#: ❗ 行号会因无关编辑而漂移 —— 这是**有意接受**的代价：
#: 行号对不上时测试会红，逼着人来看一眼"这处还在不在、理由还成立吗"，
#: 比用一个模糊的"按函数名匹配"更不容易漏掉真实变化。
JUSTIFIED: dict[str, str] = {
    "app/__init__.py:41": "`_ImportStub` 降级：导入失败必须能继续跑，否则打包缺陷不可见",
    "app/__init__.py:47": "元数据读取失败时回落到 `_FALLBACK_VERSION`，是版本探测的正常分支",
    "app/agent_orchestrator.py:30": "`__del__` 析构：抛异常会让解释器打印 ignored 并干扰线程池清理",
    "app/diagnostic_logger.py:141": "日志组件自身：在这里报错会把「记录失败」升级成「业务失败」",
    "app/novel_store.py:90": "事件订阅方抛异常不得影响写盘（此时写盘已经成功）",
    "app/storage.py:138": "临时文件名生成：拿不到 pid/tid 就退化为无前缀，仍能唯一",
    "app/storage.py:144": "旧临时文件的尽力清理：清理失败不该让本次写入失败",
    "app/storage.py:173": "备份轮转失败不该阻断主写入（备份是加值，不是前提）",
    "app/storage.py:228": "损坏文件归档是尽力而为；归档失败仍要继续读取回退链",
    "app/storage.py:234": "读取回退链的某一级不可用就试下一级，属正常分支",
    "app/storage.py:240": "回退链同上：候选文件缺失/损坏时继续尝试下一个",
    "app/usage_tracker.py:259": "用量事件广播是旁路，失败绝不回滚已经记账的数据",
}

#: 允许"无日志吞"的异常类型白名单。
#: 这些都是**明确的、可预期的**失败类别，吞掉有确定语义：
#: - Tk 相关：控件已销毁，任何操作都无意义
#: - JSON/ValueError：解析回退链的正常分支
#: - OSError：文件不存在/不可读时的最佳努力
_NARROW_TYPES_ALLOWED = {
    "tk.TclError",
    "ValueError",
    "KeyError",
    "IndexError",
    "AttributeError",
    "ImportError",
    "FileNotFoundError",
    "OSError",
    "RuntimeError",
    "LookupError",
    "json.JSONDecodeError",
}


def _iter_pass_handlers():
    """产出 `(相对路径, 行号, 异常类型字符串, 是否纯净 pass)`。"""
    for path in sorted(APP_DIR.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            # 只关心"整个 handler 体就是一个 pass"的情况
            body = [s for s in node.body if not isinstance(s, ast.Expr)]
            if not (len(body) == 1 and isinstance(body[0], ast.Pass)):
                continue
            type_name = ast.unparse(node.type) if node.type else ""
            yield rel, node.lineno, type_name


def _normalized_types(type_name: str) -> set[str]:
    """`(a, b)` → `{"a", "b"}`；空（裸 except）→ 空集。"""
    text = (type_name or "").strip()
    if not text:
        return set()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    return {p.strip() for p in text.split(",") if p.strip()}


class TestSilentSwallowsAreRegistered:
    def test_no_unregistered_silent_swallow(self):
        """新增的 `except: pass` 必须登记并写明理由。"""
        offenders = []
        for rel, lineno, type_name in _iter_pass_handlers():
            key = f"{rel}:{lineno}"
            if key in JUSTIFIED:
                continue
            types = _normalized_types(type_name)
            # 宽泛吞（裸 except / Exception / BaseException）一律要求登记
            if not types or types & {"Exception", "BaseException"}:
                offenders.append(f"{key}  except {type_name or '<bare>'}")
                continue
            # 收窄类型：允许，但类型必须在白名单里
            unknown = types - _NARROW_TYPES_ALLOWED
            if unknown:
                offenders.append(f"{key}  except {type_name}  ← 未列入白名单的类型：{sorted(unknown)}")
        assert not offenders, (
            "发现未登记的静默吞异常。请二选一：\n"
            "  a) 加日志（`logger.warning(...)`）—— 推荐；\n"
            "  b) 若确实该吞，在 `JUSTIFIED` 里登记并写明理由；\n"
            "  c) 或把异常类型收窄到 `_NARROW_TYPES_ALLOWED` 中的具体类型。\n\n" + "\n".join(offenders)
        )

    def test_registry_entries_still_exist(self):
        """反向断言：登记表不能变成历史垃圾。

        修好了某处却忘了删登记 ⇒ 这里变红。
        （本仓的硬纪律："守卫要同时拦回流与被删"。）
        """
        actual = {f"{rel}:{ln}" for rel, ln, _t in _iter_pass_handlers()}
        stale = sorted(set(JUSTIFIED) - actual)
        assert not stale, f"这些登记项已不存在（修好了？行号漂移？）请核对并更新 JUSTIFIED：{stale}"

    def test_registry_has_reasons(self):
        for key, reason in JUSTIFIED.items():
            assert len(reason) >= 8, f"{key} 的理由太短，等于没写：{reason!r}"

    def test_scanner_actually_finds_things(self):
        """防"扫描器啥也没扫到"式空转通过。"""
        found = list(_iter_pass_handlers())
        assert len(found) >= 20, f"只扫到 {len(found)} 处，疑似扫描失效（预期几十处）"

    def test_scanner_detects_a_synthetic_swallow(self, tmp_path, monkeypatch):
        """负向对照：人造一处 `except Exception: pass` ⇒ 必须被检出。

        ❗ 没有这条，"上面全绿"可能只是因为扫描器永远返回空。
        """
        fake_app = tmp_path / "app"
        fake_app.mkdir()
        (fake_app / "x.py").write_text(
            "def f():\n    try:\n        pass\n    except Exception:\n        pass\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(sys.modules[__name__], "APP_DIR", fake_app)
        monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
        found = list(_iter_pass_handlers())
        assert len(found) == 1, f"扫描器没检出人造的静默吞：{found}"
        assert found[0][2] == "Exception"


class TestHighRiskSitesAreNotSilent:
    """点名检查几处**会造成数据/语义损失**的位置，必须已带日志。"""

    @pytest.mark.parametrize(
        ("rel", "needle", "why"),
        [
            ("app/editor_ui.py", "主角锁定", "静默失败 ⇒ AI 不知道主角是谁 ⇒ 中途换主角"),
            ("app/character_system.py", "自定义武器", "静默失败 ⇒ 用户自定义武器/技能凭空消失"),
            ("app/timeline_ui.py", "世界线文件", "静默失败 ⇒ 某条世界线凭空消失在列表里"),
            ("app/timeline_ui.py", "分支角色", "静默失败 ⇒ 分支角色与上下文不一致"),
            ("app/writing_skills_panel.py", "读取作品题材失败", "静默失败 ⇒ 用户自定义题材被悄悄换成默认值"),
        ],
    )
    def test_site_logs_instead_of_passing(self, rel, needle, why):
        code = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert needle in code, f"{rel} 里找不到「{needle}」相关日志（{why}）"
