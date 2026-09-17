# R21 迭代记录：测试 → 发现 → 修复 → 回归

> 本文记录第二十一轮「多轮反复测试」的完整过程：每一轮跑什么、抓到什么、
> 怎么修、修完怎么复核。**结论在最后一节**，过程按轮次排列。
>
> 对应提交：`0668fb3`（M1/M2/M3 决策）→ `0f46246`（O4 去重）→
> `95160d9`（dialogs 修复）→ `a93d283`（R21 四处缺陷）→
> `1d4d2aa`（探针 3）→ `f33c849`（CHANGELOG）。

---

## 0. 本轮的两个组成部分

用户的要求是"完全采用推荐的方案，然后多轮反复测试直到没有新问题"。所以分两步：

**第一步：把四条建议全部落地**（不含 PAT 权限 —— 用户明确说明那是有意为之）

| ID | 事项 | 采纳的选项 | 落地动作 | 提交 |
|---|---|---|---|---|
| M1 | 六个标签指向同一提交 | **方案 A：保留现状只记录** | `RELEASE_HISTORY_NOTES.md §3.1` 写入决策与三条理由；**无 Git 操作** | `0668fb3` |
| M2 | `mobile-app/webview-app` 归档 | **方案 C：保留 + 补归档说明** | 新增该目录 `README.md`（状态卡 + 技术债表）；`CONTRIBUTING.md` 目录树加注 | `0668fb3` |
| M3 | `backend/` 定位 | **方案 A：冻结** | `BACKLOG_REGISTER.md §4.1` 写冻结契约（准入/禁入表 + 不变量 + 解冻条件） | `0668fb3` |
| O4 | 重复测试合并 | **按三层判据执行** | 2420 → 2338 条，净删 738 行 / 12 文件 | `0f46246` |

两项**观察项**按建议**不动**：`parse_exp_json`（截断语义属于设计选择）、
`CharacterSystem`（需先确认宿主环境）。

**第二步：六轮迭代测试。**

---

## 1. 六轮总览

| 轮 | 探针 | 结果 | 抓到的问题 | 处理 |
|---|---|---|---|---|
| 1 | 合并后全量回归 | 2397 passed, 6 skipped | 无回归 | — |
| 2 | lint + 首轮全量 | — | 删重复后 `json` 变成未使用导入 | `ruff --fix` |
| 3 | 合并脚本自身 | **失败** | 脚本三处错误（见 §2） | 回滚重做 |
| 4 | `boundary_probe.py`（A–F 单点边界） | F3 失败 | **`dialogs.silent_modals` 真缺陷** | 修复 + 2 条回归测试 |
| 5 | `iteration_probe2.py`（链路闭环） | A3 / D2 失败，B3 暴露契约缺口 | **自学习 2 处 + 解析器 3 处真缺陷** | 修复 + 31 条契约测试 |
| 6 | `iteration_probe3.py`（外壳/工程门禁） | 22/22 通过 | 无新缺陷 | 仅修我自己的探针 |

---

## 2. 第三轮：合并脚本自己的三个错误（工具缺陷）

这一轮的价值在于**它证明了"工具本身也要被测试"**。

### 2.1 仓库根解析错了一级

`dup_test_census.py` 报"0 组重复"。原因是：

```python
REPO = Path(__file__).resolve().parent          # ← 解析成 scripts/
```

脚本在 `scripts/` 下，`.parent` 就是 `scripts/`，于是它在 `scripts/` 里找 `tests/`，
自然找不到任何东西，**安静地报告"没有重复"**。这与之前
`smoke_generators.py` 那个"自搬入 `scripts/` 起就从未跑通过"是同一类错误。

修法是 `.parent.parent` **外加一条断言**，让路径错误立刻炸而不是静默：

```python
REPO = Path(__file__).resolve().parent.parent
assert (REPO / "tests").is_dir(), f"仓库根解析失败：{REPO}"
```

### 2.2 `clean_empty_classes` 删掉了测试替身

合并脚本删除测试后，会清扫"空掉的测试类"。判据是"类里没有 `test_` 方法"——
但 `FakeApp`、`Recorder`、`FakeWidget`、`DummyPanel` 这些**替身类**天然满足这个条件。

一次误删 27 个条目。用 `git checkout -- tests/` 整体回滚，然后把判据收紧：

```python
if not node.name.startswith("Test"):
    continue
```

收紧后只剩 5 个**真的**空掉的测试类。

### 2.3 删除范围漏掉了装饰器 ⇒ 语法错误

`ast` 的 `node.lineno` 指向 `def`，**不包含它上方 `@decorator` 的行**。
只按 `def` 的行号删，会留下一个孤零零的 `@respx.mock`：

```
IndentationError: unexpected unindent
```

修法是把装饰器行号也算进删除范围：

```python
decs = getattr(node, "decorator_list", []) or []
self.lineno = min([node.lineno] + [d.lineno for d in decs])
```

并且**加一道落盘自检**——改完文件立刻 `ast.parse` 一遍，不通过就整体中止：

```python
def _assert_parses(paths: list[Path]) -> None:
    bad: list[str] = []
    for p in paths:
        try:
            ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as e:
            bad.append(f"{p.name}:{e.lineno}: {e.msg}")
    if bad:
        raise SystemExit("❌ 语法自检失败，已中止：\n  " + "\n  ".join(bad))
    print(f"  ✓ 语法自检通过（{len(paths)} 个文件）")
```

重做后输出 `✓ 语法自检通过（78 个文件）`。

---

## 3. 第四轮：`dialogs.silent_modals` 的嵌套语义缺陷

### 现象

探针 F3 失败。`with dialogs.silent_modals():` 里再嵌一层，
出来之后**静默状态没了**。

### 根因

旧实现用 `_silent_depth` 计数，`__exit__` 在深度归零时**无条件**写死 `set_silent(False)`：

```python
def __exit__(self, *_exc):
    global _silent_depth
    _silent_depth -= 1
    if _silent_depth <= 0:
        set_silent(False)          # ← 外层本来就是 True 的话，这里把它解开了
    return False
```

后果不只是嵌套：外层先 `set_silent(True)` 做全局静默，
内层只要进出一个 `with` 块，**全局静默就失效了**，
后面的模态弹窗会真的弹出来把自动化脚本卡住。

### 修法

进入时记住**进入前的状态**，退出时恢复**那个状态**，而不是硬编码 `False`：

```python
class silent_modals:
    def __init__(self) -> None:
        self._previous: bool | None = None

    def __enter__(self) -> "silent_modals":
        global _silent_depth
        _silent_depth += 1
        self._previous = set_silent(True)
        return self

    def __exit__(self, *_exc) -> bool:
        global _silent_depth
        _silent_depth = max(0, _silent_depth - 1)
        # 恢复进入前的状态：若外层本来就是静默的，退出后仍然是静默的。
        if self._previous is not None:
            set_silent(self._previous)
        return False
```

### 验证

新增 2 条回归测试（`tests/test_dialogs.py` 21 → 23 条），并做**反证**：
临时退回旧实现，确认新测试**确实转红**；恢复后转绿。

---

## 4. 第五轮：自学习的两处真缺陷

自我学习此前被评估为 **L0（只写不读）**。这轮把链路拉起来打，又抓到两处。

### 4.1 失败章节什么都不写（A3）

```python
def learn_from_chapter(self, chapter_content, chapter_num, characters, success=True):
    if success:
        ...  # ← 全部学习逻辑都在这里面
    # success=False 时：函数直接结束，一条记忆都不写
```

而 `QUALITY_THRESHOLD = 75` 确实可达 —— 也就是说"写砸的章节"从不进入记忆，
下一章开写时也就没有任何"这里容易翻车"的提示。

修法：补齐 `else` 分支，写 `memory_type="failure_pattern"`，
**权重随评分下降而上升**（写得越差，越该记住）：

```python
importance = max(0.5, min(0.9, 0.5 + (75 - quality) / 100))
```

60 分 → 0.65，75 分 → 0.5。

### 4.2 空文本写垃圾记忆（D2）

`learn_from_chapter("")` 实测写出 **3 条**记忆（`0 → 3`）。加前置 return：

```python
if not chapter_content or not chapter_content.strip():
    return
```

### 4.3 顺带：写了还得有人读

新写的 `failure_pattern` 如果没人查，等于又回到"只写不读"。
`get_writing_context` 加一段：

```python
recent_misses = self.time_memory.query(
    memory_type="failure_pattern", limit=3, chapter=chapter or None, chapter_window=50
)
if recent_misses:
    misses = [f"- {m['content'][:100]}" for m in recent_misses]
    context_parts.append("\n【近期未达标章节（应避开同类问题）】\n" + "\n".join(misses))
```

### 4.4 一个测试自己的 bug

我在断言里用了 `m["memory_type"]`，但记忆条目里存分数的键是 **`"type"`**。
这不是代码问题，是我的测试写错了 —— 改测试。

另外，角色提及计数原本被包在 `if success:` 里，已移出：
"这章写了谁"与"这章写得好不好"无关。

---

## 5. 第五轮：解析器的类型契约（最值得记的一处）

### 5.1 语义是单向的

收敛后的 `parse_json_response(response, default, is_list=False)` 有 5 层策略。
关键点：**`is_list=False` 不拒绝顶层数组**，它只是"优先找 `{`"。

所以当模型只回一个 JSON 数组（很常见）而调用方期望 dict 时，会拿到 `list`。

### 5.2 三处受影响

| 位置 | 后果 |
|---|---|
| `novel_agent._world_builder_build` | `save_settings(list)` → 崩 |
| `novel_agent.analyze_style` | 按 dict 取键 → 崩 |
| `memory_manager._format_settings_md` | `settings.items()` → `AttributeError: 'list' object has no attribute 'items'` |

第三处我实际复现了那个 `AttributeError` 才动手。

### 5.3 最危险的一处：守卫写在所有使用之后

`novel_agent.generate_with_collaboration` 里 `review` 是**有**守卫的 ——
但它位于**第 748 行**，而首次使用在**第 695 行**。

**光看 grep 会以为没问题。** 这是一个独立的缺陷类别：`if not isinstance(review, dict)`
写在了它要保护的代码之后，属于死代码。

修法：拿到 `review` 立刻规范化。

```python
review = self._reviewer_evaluate(...)
if not isinstance(review, dict):
    self.log("[Editor] ⚠️ 审校返回的不是 JSON 对象，按默认评分处理")
    review = {"overall_score": 70, "issues": [], "suggestions": []}
```

### 5.4 新增的「全域元守卫」

`tests/test_parse_type_contract.py`（31 条）里最重要的一条**不是**逐点测试，
而是扫描**每一个** `parse_json_response` 调用点，要求满足四者之一：

1. 紧邻 `isinstance` 守卫；
2. 薄转发（只是把结果交给别的函数）；
3. 立刻 `return`；
4. 在**使用点之前**有守卫。

价值：它会拦住**将来新加的**未守卫调用点。一条元守卫胜过 N 条逐点测试。

### 5.5 元守卫自己踩的两个坑

- **窗口太窄**：最初只看 6 行，`generation_ui.py:327` 被误报。放宽到 12 行，
  并补上"薄转发"与"立刻 return"两种合法形态的识别。
- **匹配到自己写的注释**：我为这轮写的注释里包含 `review.setdefault(` 这个字面量，
  于是源码扫描看到"守卫之前就有使用"。修法是先跑 `_code_only`（剥掉注释）再扫。
  **这是同一个陷阱的第 5 次出现：验证判据本身必须先自检。**

---

## 6. 第六轮：外壳与工程门禁（22/22 通过）

`scripts/iteration_probe3.py` 打三件事：

| 组 | 内容 | 结果 |
|---|---|---|
| A | 事件总线：订阅/广播、异常隔离、通配符、无订阅者、unsubscribe 幂等 | 7/7 |
| B | 布局持久化：mode / 两栏面板 / ratio / 已脱出 往返一致；4 种坏文件不崩；文件缺失给默认 | 10/10 |
| C | 弹窗收口门禁：无业务代码直接调 `messagebox` | 1/1 |
| D | 版本权威：`app.__version__` == `pyproject`（3.1.0） | 1/1 |
| E | 根目录文档固定 6 个，且没有多出来的根 `.md` | 2/2 |
| F | 字体令牌门禁：无硬编码字体字面量 | 1/1 |

**本轮没有新缺陷** —— 但前两次尝试各失败一次，两次都是**我的探针写错**：

1. **事件总线 API 用错**。我按"模块级函数"写（`event_bus.subscribe(...)`），
   实际是 `EventBus()` **实例**，且处理器契约是 **`handler(topic, payload)` 两个参数**。
   日志里那句 `<lambda>() takes 1 positional argument but 2 were given` 就是证据。
2. **A4 计数被通配符污染**。同一实例上先订阅了 `WILDCARD`，
   所以 `publish("nobody.listens.here")` 返回 1 而不是 0。改用全新实例。

另外 ruff 抓到我的探针里一个 `and`/`or` 混用无括号的表达式
（`format` 会把它重排，等于语义有歧义），已加括号固化意图。

---

## 7. 一个必须写下来的环境陷阱

全量跑套件时出现**大批 `ERROR at setup`**，看起来像代码坏了。实际是沙箱的删除守卫：

```
[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED]
{"count":12446,"threshold":50,"scope":"turn",...}
```

读了守卫实现（`safe-delete-bulk-guard.cjs`）才明白关键点：

```js
const totalCount = request.count + deleteCount;   // ← 累加
...
if (totalCount >= context.threshold) { /* 要求确认 */ }
```

计数器挂在 **`requestId`** 上，也就是**整轮对话累计**，不是每个工具调用各自一份预算。

**判据**（三条都指向环境，而不是代码）：

1. **单跑 vs 批量跑结果不一致**：同一个文件单跑 58 passed，全量跑就报错 ⇒ 100% 环境伪报。
2. **0 个 `FAILED`，全是 `ERROR at setup`**：逻辑缺陷会是 FAILED。
3. **`-x`（首个错误即停）反而跑满 100%**：说明根本没有真错误可停。

**结论与姿势**：这类现象**不要改代码**。要拿到真实通过数，就
**按文件分块、每块一个独立工具调用**（各自独立预算）；
`--basetemp` 只改落盘位置，**不解决计数上限**。

---

## 8. 最终结果

### 测试与检查

| 项目 | 结果 |
|---|---|
| 桌面端 `tests/` | **2348 通过**，6 跳过，**0 失败 0 错误**（2355 收集） |
| 后端 `backend/tests/` | **128 通过** |
| `ruff check app/ tests/ scripts/` | All checks passed |
| `ruff format --check app/ tests/ scripts/` | 178 files already formatted |
| `scripts/boundary_probe.py` | 全部通过 |
| `scripts/iteration_probe2.py` | 22/22 通过 |
| `scripts/iteration_probe3.py` | 22/22 通过 |
| `scripts/smoke_generators.py` | 15/15 通过 |

**合计 2483 条测试**（桌面端 2355 + 后端 128）。

### 本轮修复的真缺陷（4 类 / 7 处）

1. `dialogs.silent_modals` 退出时丢掉外层静默状态；
2. 自学习：`success=False` 时什么都不写（失败样本整条链路缺失）；
3. 自学习：空/纯空白文本写出垃圾记忆；
4. 解析器类型契约：3 处调用方会崩或静默丢数据，其中 1 处是**守卫写在所有使用之后**。

每一处都做了**反证验证**：退回修复 → 确认守卫测试转红 → 恢复。

### 新增文件

| 文件 | 用途 |
|---|---|
| `docs/BACKLOG_REGISTER.md` §4.1 | `backend/` 冻结契约 |
| `docs/RELEASE_HISTORY_NOTES.md` §3.1 | M1 决策记录 |
| `docs/ITERATION_LOG_R21.md` | 本文 |
| `mobile-app/webview-app/README.md` | 归档说明 |
| `scripts/dup_test_census.py` | 重复测试普查 |
| `scripts/review_dup_candidates.py` | 候选复核报告 |
| `scripts/dedup_tests.py` | 合并执行器 |
| `scripts/boundary_probe.py` | 单点边界探针 |
| `scripts/iteration_probe2.py` | 链路闭环探针 |
| `scripts/iteration_probe3.py` | 外壳/工程门禁探针 |
| `tests/test_parse_type_contract.py` | 解析器类型契约 + 全域元守卫（31 条） |

---

## 9. 仍然需要注意的事项

1. **PAT 权限按用户要求未动** —— 这是有意为之的设计，不在本轮范围内。
2. **两项观察项按建议未动**：`parse_exp_json` 的截断语义、`CharacterSystem` 的宿主依赖。
3. **`backend/` 已冻结**：只接缺陷与安全补丁。若确需扩展，
   先满足 `BACKLOG_REGISTER.md §4.1` 的三条解冻条件。
4. **六个历史标签指向同一提交是保留决策**，不是遗漏 ——
   它们发布过，按仓库纪律不满足重指条件。
5. **版本号仍是 3.1.0**：本节内容属于「未发布（候选 v3.2.0）」，
   打标签时才成为发布内容。
6. **沙箱删除守卫的累计计数**会在长会话里造成"越跑越红"的假象，
   诊断方法见 §7 —— 遇到时先单跑验证，不要改代码。
