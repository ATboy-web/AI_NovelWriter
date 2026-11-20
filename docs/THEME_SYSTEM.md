# 主题系统（v3.4，2026-11-20）

> 三套可切换的极简主义视觉体系：**赛博朋克 / 废土末日 / 机械朋克**。
> 桌面端（Tk/ttk）与移动端（Kotlin Compose）共用同一套设计令牌。
> 本文档是"怎么用、怎么改、怎么守"的入口；取值权威在代码里，不在本文档。

## 1. 单一来源链条

```
app/theme_system.py            ← 唯一权威（纯数据，不 import tkinter）
  ├─ UIStyle.set_palette()     ← 原地更新 UIStyle.COLORS（保持对象同一性）
  │    └─ DesignTokens.refresh()  ← 派生快照同步刷新
  ├─ UIStyle.apply_theme(root, theme=…)  ← ttk 样式全量配置（含基础样式与状态映射）
  ├─ app/theme_switch.py       ← 已建控件树即时换肤（遍历改色）
  └─ scripts/sync_theme_tokens.py → ThemeTokens.kt（生成物，DO NOT EDIT）
       └─ Theme.kt 状态驱动 getter → 全部屏幕零改动换肤
```

**为什么原地更新**：全仓大量 `C = UIStyle.COLORS` 模块级别名。替换字典对象
会让别名指向旧调色板；`clear()+update()` 保持 `id()` 不变，别名即时生效。

**为什么移动端用 getter**：屏幕代码写的是 `Surface1` / `Primary400` 这类名字。
把名字背后的取值改成快照状态（`mutableStateOf`）驱动的 getter，读取发生在
组合期，状态一变所有读过令牌的组合自动重组 —— 不需要改任何屏幕。

## 2. 每套主题覆盖什么

| 层 | 令牌 | 说明 |
|---|---|---|
| 背景 | `bg_dark / bg_medium / bg_light / bg_card / bg_hover` | 五级色阶；`bg_light == bg_card` 是结构别名 |
| 文字 | `text_primary / secondary / muted / inverse` | 全部 ≥4.5:1（对全部背景） |
| 强调 | `accent / accent_light / accent_hover / accent_bg / accent_text` | 填充用深色保证白字/金字可读；亮色只做文字/焦点 |
| 语义 | `success / warning / error / info`（填充）+ `*_bg` + `*_text` | **填充跨主题恒定**；文字变体逐主题调亮 |
| 边框 | `border / border_light / border_focus` | 焦点环颜色随主题 |
| 悬停 | `hover / hover_light`（`hover == bg_hover` 别名） | tk 控件悬停 + ttk active 态 |
| 组件质感 | `STYLE_PARAMS`：内边距密度 / 边框粗细 / 行高 | 赛博紧凑、废土宽松、机械 2px 粗边框 |
| 间距 | `SPACING_SCALE`（2/4/8/12/16/24） | 三主题统一，4px 基准栅格 |
| 字体层级 | `TYPE_SCALE`（caption…display 七角色） | 桌面 px 与 FONT_ROLES 同值；移动 sp 同角色序列 |
| 交互状态 | ttk map：active/pressed/selected/disabled/focus/invalid | 含 `Error.TEntry` 校验错误态 |

**图标**：应用图标是文字字形（✕ ✔ ▲ 等），颜色走文字令牌，换肤遍历自动改色；
题材识别色（GenreColors / Accent*）属**内容语义**，不随界面主题变化。

## 3. 设计决策（改之前先读）

1. **三主题均深色底**：既有对比度守卫以深色背景为前提，`test_ui_style` 断言
   `bg_dark < text_primary`。废土用暖炭底而非浅色纸面，正是守住这条不变量。
2. **语义填充色恒定**：危险=红、成功=绿的识别不随主题漂移；变的是文字变体。
3. **同值不同键 = 换肤歧义**：换肤按"旧值→新值"映射。除结构别名
   （`bg_light/bg_card`、`hover/bg_hover`、各主题内 `accent_light/border_focus`）
   外，调色板内不得有两个键同值 —— `test_palette_swap_map_is_unambiguous` 钉住。
4. **间距/字阶跨主题统一**：极简主义要求同一套栅格与字阶；主题差异在色彩与质感。
5. **阅读器的 light/dark/sepia 是另一回事**：那是正文纸张模式（reader_ui），
   不是界面主题，两者互不干扰。

## 4. 怎么改 / 怎么加主题

1. 改 `app/theme_system.py`（加主题：THEMES / STYLE_PARAMS / THEME_META / THEME_IDS 四处）。
2. 跑 `python scripts/sync_theme_tokens.py` 重新生成 Kotlin 令牌。
3. 跑 `pytest tests/test_theme_system.py tests/test_ui_style.py tests/test_panel_ui_quality.py`。
4. 文字色不达标时用"最小提亮法"（向白插值直到 ≥4.6:1，留余量），不要换色相。
5. 版本号按铁律四处同步 + CHANGELOG；代码更新必须重打包 EXE。

## 5. 已知边界

- 手写 `padx/pady`（约 1177 处）不在本次换肤范围 —— 沿用项目既有的
  "令牌 + 棘轮"渐进迁移策略；ttk 样式内边距已按主题区分。
- `webview-app` 已归档冻结（M2 决策），未接入主题系统。
- 换肤遍历只改**命中旧调色板**的颜色；语义常量（"white"、"#ffd700" 等）不动。