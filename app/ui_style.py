"""
UI样式管理模块 - 现代化UI样式
AI小说创作工坊 设计系统（v3.4 起为三主题可切换体系）

调色板的**唯一权威**在 `app/theme_system.py`（赛博朋克 / 废土末日 / 机械朋克）。
`UIStyle.COLORS` 是**当前激活主题**的调色板：`set_palette()` 原地更新它
（保持字典对象同一性 —— 全仓 `C = UIStyle.COLORS` 的模块级别名依赖这一点），
`apply_theme()` 据此配置全部 ttk 样式。换肤遍历见 `app/theme_switch.py`。
"""

# D4：`import tkinter as tk` 随四个 `create_styled_*` 工厂一起移除 ——
# 本模块现在只用 `ttk`（`ttk.Style()` 配置全局主题）。
from tkinter import ttk

from . import theme_system


class UIStyle:
    """现代化UI样式 - 多主题设计系统（默认深色：赛博朋克）"""

    #: 当前激活主题 id（theme_system.THEME_IDS 之一）
    ACTIVE_THEME = theme_system.DEFAULT_THEME

    @classmethod
    def set_palette(cls, theme_id: str) -> str:
        """激活一套主题调色板，返回归一后的主题 id。

        **原地更新** COLORS（clear+update），不替换字典对象 ——
        各面板 `C = UIStyle.COLORS` 的别名必须立即看到新值。
        同时刷新 DesignTokens 的派生快照（单一来源链条不断）。
        """
        tid = theme_system.normalize_theme(theme_id)
        cls.COLORS.clear()
        cls.COLORS.update(theme_system.THEMES[tid])
        cls.ACTIVE_THEME = tid
        # 延迟导入：design_tokens 在模块级 import 本模块，顶层互引会成环
        from .design_tokens import DesignTokens

        DesignTokens.refresh()
        return tid

    # ═══════════════════════════════════════════
    # 设计令牌 (Design Tokens)
    # ═══════════════════════════════════════════

    # 颜色系统 - 深色主题 v3.0
    COLORS = {
        # 背景色阶
        "bg_dark": "#0f0f1a",  # 主背景 - 最深
        "bg_medium": "#16162a",  # 次背景 - 面板
        "bg_light": "#1e1e38",  # 浅背景 - 卡片
        "bg_card": "#1e1e38",  # 卡片背景
        "bg_hover": "#252540",  # 悬停状态
        # 主色调 - 紫色系
        "accent": "#534ab7",  # 主色调
        "accent_light": "#a78bfa",  # 浅紫色
        "accent_hover": "#6a62d0",  # 悬停色
        "accent_bg": "#2d1b69",  # 紫色背景
        # 语义色
        # ⚠️ 基色是**填充色**（配白字用，v3.4.1 起全部满足白字 ≥4.5:1），
        # 不要拿它们当深色背景上的文字色 —— 深色背景上的语义文字请用下面的 `*_text` 变体。
        # 取值唯一权威在 theme_system._SEMANTIC_FILLS，此处默认值须与其一致。
        "success": "#0f6e56",  # 成功绿（填充，白字 6.20）
        "success_bg": "#064e3b",  # 成功背景
        "warning": "#a16207",  # 警告琥珀（填充，白字 4.92；v3.4.1 由 #f59e0b 加深）
        "warning_bg": "#78350f",  # 警告背景
        "error": "#dc2626",  # 错误红（填充，白字 4.83；v3.4.1 由 #ef4444 加深）
        "error_bg": "#7f1d1d",  # 错误背景
        "info": "#1e40af",  # 信息蓝（填充，白字 8.72；v3.4.1 由 #3b82f6 加深）
        "info_bg": "#1e3a5f",  # 信息背景
        # 语义色的**文字变体**：实测在 bg_dark/bg_medium/bg_card/bg_hover 上**全部 ≥4.5:1**
        # （2026-09-16 用最小提亮法算出，保持色相不变；见 `tests/test_ui_contrast.py`）
        "accent_text": "#8c86cf",  # 最差 4.53
        "success_text": "#16a27e",  # 最差 4.59
        "info_text": "#4c8df7",  # 最差 4.56
        "error_text": "#f15b5b",  # 最差 4.51
        "warning_text": "#f59e0b",  # 最差 6.90（深底文字用；与填充色 #a16207 不同值）
        # 文字色阶
        "text_primary": "#e0e0f0",  # 主文字（12.4:1 起）
        "text_secondary": "#a0a0b0",  # 次文字（6.3:1 起）
        #: 弱文字/提示 —— 2026-09-16 由 `#606080` 提亮：原值在 `bg_dark` 上仅 3.16:1、
        #: `bg_card` 上 2.68:1（低于 4.5:1 可读底线）⇒ 全应用 15 个面板的提示文字都发灰难认。
        #: 只提亮、不改色相，现在最差 4.54:1。这是"一处改动改善全部面板"的那一处。
        "text_muted": "#8c8ca8",
        "text_inverse": "#ffffff",  # 反色文字
        # 边框色
        "border": "#2a2a40",  # 默认边框
        "border_light": "#3a3a55",  # 浅边框
        "border_focus": "#534ab7",  # 聚焦边框
        # 悬停背景
        "hover": "#252540",  # 悬停背景
        "hover_light": "#2a2a45",  # 浅悬停
    }

    # 字体系统
    FONTS = {
        "family": "微软雅黑",
        "family_mono": "Consolas",
        "size_xs": 9,  # 辅助文字
        "size_sm": 10,  # 小文字
        "size_base": 11,  # 正文
        "size_lg": 13,  # 标题
        "size_xl": 15,  # 大标题
        "size_xxl": 18,  # 超大标题
    }

    #: 控件 `font=` 的**角色令牌** → Tk 字体元组。
    #:
    #: 用法：`tk.Label(parent, text="…", font=UIStyle.font("label"))`
    #:
    #: 为什么按"角色"而不是按"值"命名：`("微软雅黑", 9)` 出现在说明文字上是「辅助」、
    #: 出现在按钮上是「按钮文字」—— 语义不同，将来调主题时改的也是语义
    #: （改值等于什么都没说）。括号里的数字是 2026-09-16 实测的用量，最大的几个先纳入。
    #:
    #: ⚠️ 迁移现状：全仓仍有 **460 处字面 `font=(...)`**（31 个文件），因此
    #: 这里只提供**新代码与增量迁移**要用的角色；`tests/test_font_token_ratchet.py`
    #: 用"棘轮"保证字面用法**只减不增**，等到清零即可把断言收紧为"全局禁止"。
    FONT_ROLES = {
        "caption": ("微软雅黑", 8),
        "caption_bold": ("微软雅黑", 8, "bold"),
        "label": ("微软雅黑", 9),  # 137 处
        "label_bold": ("微软雅黑", 9, "bold"),  # 16 处
        "body": ("微软雅黑", 10),  # 104 处
        "body_bold": ("微软雅黑", 10, "bold"),  # 22 处
        "subtitle": ("微软雅黑", 11),
        "subtitle_bold": ("微软雅黑", 11, "bold"),
        "title": ("微软雅黑", 12, "bold"),  # 15 处
        "heading": ("微软雅黑", 14, "bold"),
        "display": ("微软雅黑", 16),
        #: 历史上写作 `font=("", 11, "bold")`：空字体族 = 沿用 Tk 系统默认字体
        "default_bold": ("", 11, "bold"),  # 13 处
        "mono": ("Consolas", 10),
        "mono_small": ("Consolas", 9),
        #: 空字体族 = 沿用 Tk 系统默认字体（历史上写作 `font=("", 10)`）
        "system": ("", 10),
        "system_bold": ("", 10, "bold"),
        # ── 以下 6 个角色为"字面量全量令牌化"补齐（2026-09-17）──
        # 它们原本散落在各模块，用量不大但**必须**有令牌，否则棘轮永远清不了零。
        # 取值与替换前的字面量逐一相等，属等值替换（视觉零变化）。
        "micro": ("微软雅黑", 7),  # 比 caption 更小的角标
        "title_plain": ("微软雅黑", 12),  # 非粗体的 12px 标题
        "heading_small": ("微软雅黑", 13, "bold"),  # 介于 title 与 heading 之间
        "heading_plain": ("微软雅黑", 14),  # 非粗体小节标题
        "mono_small_bold": ("Consolas", 9, "bold"),  # 等宽强调
        #: 品牌/启动页大字（英文大写用 Arial 比中文黑体更合适）
        "logo": ("Arial", 18, "bold"),
    }

    @classmethod
    def font(cls, role: str = "body") -> tuple:
        """取角色令牌对应的 Tk 字体元组；未知角色**回落**到 `body`。

        为什么不抛错：字体是表现层，一个拼错的角色名不该让整个面板构建失败
        （`TestPanelColorTokensExist` 存在的理由正是"颜色键写错会让面板建到一半崩"）。
        但拼错不会静默通过 —— `test_font_role_names_are_all_declared` 扫全仓
        `UIStyle.font("x")` 的字面参数，不在 `FONT_ROLES` 里就直接失败。
        """
        return cls.FONT_ROLES.get(role, cls.FONT_ROLES["body"])

    # 间距系统 (4px 基准)
    SPACING = {
        "xs": 2,  # 2px
        "sm": 4,  # 4px
        "md": 8,  # 8px
        "lg": 12,  # 12px
        "xl": 16,  # 16px
        "xxl": 24,  # 24px
    }

    # 圆角系统
    RADIUS = {
        "sm": 4,  # 小组件
        "md": 6,  # 中组件
        "lg": 8,  # 大组件
        "xl": 12,  # 卡片
        "full": 999,  # 胶囊
    }

    @classmethod
    def apply_theme(cls, root, theme=None):
        """应用主题到根窗口。

        `theme` 传入主题 id 时先激活对应调色板（`set_palette`）；
        不传则按当前激活调色板重新配置样式（换肤 / 初始化共用这一条路径）。
        可重复调用：ttk 样式是全局注册表，重配置即对既有控件生效。
        """
        if theme is not None:
            cls.set_palette(theme)
        style = ttk.Style()
        style.theme_use("clam")

        C = cls.COLORS
        F = cls.FONTS
        P = theme_system.STYLE_PARAMS[cls.ACTIVE_THEME]

        # 配置全局样式
        root.configure(bg=C["bg_dark"])

        # ═══════ Frame 样式 ═══════
        style.configure("Dark.TFrame", background=C["bg_dark"])
        style.configure("Card.TFrame", background=C["bg_card"])
        style.configure("Medium.TFrame", background=C["bg_medium"])
        style.configure("Accent.TFrame", background=C["accent_bg"])

        # ═══════ Label 样式 ═══════
        style.configure(
            "Dark.TLabel", background=C["bg_dark"], foreground=C["text_primary"], font=(F["family"], F["size_base"])
        )
        style.configure(
            "Title.TLabel",
            background=C["bg_dark"],
            foreground=C["text_primary"],
            font=(F["family"], F["size_xl"], "bold"),
        )
        style.configure(
            "Heading.TLabel",
            background=C["bg_dark"],
            foreground=C["accent_light"],
            font=(F["family"], F["size_lg"], "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=C["bg_dark"],
            foreground=C["text_secondary"],
            font=(F["family"], F["size_base"]),
        )
        style.configure(
            "Accent.TLabel", background=C["bg_dark"], foreground=C["accent_light"], font=(F["family"], F["size_base"])
        )
        style.configure(
            "Success.TLabel", background=C["bg_dark"], foreground=C["success_text"], font=(F["family"], F["size_base"])
        )
        style.configure(
            "Warning.TLabel", background=C["bg_dark"], foreground=C["warning_text"], font=(F["family"], F["size_base"])
        )
        style.configure(
            "Error.TLabel", background=C["bg_dark"], foreground=C["error_text"], font=(F["family"], F["size_base"])
        )
        style.configure(
            "Muted.TLabel", background=C["bg_dark"], foreground=C["text_muted"], font=(F["family"], F["size_sm"])
        )

        # ═══════ Button 样式 ═══════
        # 主要按钮 - 紫色
        style.configure(
            "Accent.TButton",
            background=C["accent"],
            foreground="white",
            font=(F["family"], F["size_base"], "bold"),
            padding=P["primary_pad"],
        )
        style.map(
            "Accent.TButton",
            background=[("active", C["accent_hover"]), ("pressed", C["accent_hover"]), ("disabled", C["bg_light"])],
            foreground=[("disabled", C["text_muted"])],
        )

        # 次要按钮 - 灰色
        style.configure(
            "Secondary.TButton",
            background=C["bg_light"],
            foreground=C["text_primary"],
            font=(F["family"], F["size_base"]),
            padding=P["secondary_pad"],
        )
        style.map(
            "Secondary.TButton",
            background=[("active", C["hover_light"]), ("pressed", C["hover"]), ("disabled", C["bg_dark"])],
            foreground=[("disabled", C["text_muted"])],
        )

        # 成功按钮 - 绿色
        style.configure(
            "Success.TButton",
            background=C["success"],
            foreground="white",
            font=(F["family"], F["size_base"], "bold"),
            padding=P["primary_pad"],
        )
        style.map(
            "Success.TButton",
            background=[
                ("active", theme_system.SEMANTIC_STATES["success"]["active"]),
                ("pressed", theme_system.SEMANTIC_STATES["success"]["pressed"]),
                ("disabled", C["bg_light"]),
            ],
            foreground=[("disabled", C["text_muted"])],
        )

        # 危险按钮 - 红色
        style.configure(
            "Danger.TButton",
            background=C["error"],
            foreground="white",
            font=(F["family"], F["size_base"], "bold"),
            padding=P["secondary_pad"],
        )
        style.map(
            "Danger.TButton",
            background=[
                ("active", theme_system.SEMANTIC_STATES["error"]["active"]),
                ("pressed", theme_system.SEMANTIC_STATES["error"]["pressed"]),
                ("disabled", C["bg_light"]),
            ],
            foreground=[("disabled", C["text_muted"])],
        )

        # 幽灵按钮 - 透明
        style.configure(
            "Ghost.TButton",
            background=C["bg_dark"],
            foreground=C["accent_text"],
            font=(F["family"], F["size_base"]),
            padding=P["ghost_pad"],
        )
        style.map(
            "Ghost.TButton",
            background=[("active", C["hover"]), ("pressed", C["bg_light"]), ("disabled", C["bg_dark"])],
            foreground=[("disabled", C["text_muted"])],
        )

        # ═══════ Notebook 样式 ═══════
        style.configure("Dark.TNotebook", background=C["bg_dark"], borderwidth=0, padding=[4, 4])
        style.configure(
            "Dark.TNotebook.Tab",
            background=C["bg_medium"],
            foreground=C["text_secondary"],
            padding=list(P["tab_pad"]),
            font=(F["family"], F["size_base"]),
        )
        style.map(
            "Dark.TNotebook.Tab",
            background=[("selected", C["accent"]), ("active", C["hover_light"]), ("disabled", C["bg_medium"])],
            foreground=[("selected", "white"), ("active", C["text_primary"]), ("disabled", C["text_muted"])],
        )

        # ═══════ Entry 样式 ═══════
        style.configure(
            "Dark.TEntry",
            fieldbackground=C["bg_medium"],
            foreground=C["text_primary"],
            insertcolor=C["text_primary"],
            bordercolor=C["border"],
            lightcolor=C["border_light"],
            darkcolor=C["border"],
            borderwidth=P["borderwidth"],
            font=(F["family"], F["size_base"]),
            padding=list(P["entry_pad"]),
        )
        style.map(
            "Dark.TEntry",
            fieldbackground=[("focus", C["bg_light"]), ("disabled", C["bg_dark"]), ("invalid", C["error_bg"])],
            bordercolor=[("focus", C["border_focus"]), ("invalid", C["error"])],
            foreground=[("disabled", C["text_muted"])],
        )

        # 错误态输入框（校验失败时显式指定此样式）
        style.configure(
            "Error.TEntry",
            fieldbackground=C["error_bg"],
            foreground=C["text_primary"],
            insertcolor=C["text_primary"],
            bordercolor=C["error"],
            lightcolor=C["error"],
            darkcolor=C["error"],
            borderwidth=P["borderwidth"],
            font=(F["family"], F["size_base"]),
            padding=list(P["entry_pad"]),
        )
        style.map(
            "Error.TEntry",
            bordercolor=[("focus", C["error_text"])],
            foreground=[("disabled", C["text_muted"])],
        )

        # ═══════ Combobox 样式 ═══════
        style.configure(
            "Dark.TCombobox",
            fieldbackground=C["bg_medium"],
            foreground=C["text_primary"],
            bordercolor=C["border"],
            arrowcolor=C["text_secondary"],
            borderwidth=P["borderwidth"],
            font=(F["family"], F["size_base"]),
            padding=list(P["entry_pad"]),
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("focus", C["bg_light"]), ("readonly", C["bg_medium"]), ("disabled", C["bg_dark"])],
            bordercolor=[("focus", C["border_focus"]), ("invalid", C["error"])],
            arrowcolor=[("focus", C["accent_light"]), ("disabled", C["text_muted"])],
            foreground=[("disabled", C["text_muted"])],
        )

        # ═══════ Checkbutton 样式 ═══════
        style.configure(
            "Dark.TCheckbutton",
            background=C["bg_dark"],
            foreground=C["text_primary"],
            font=(F["family"], F["size_base"]),
            indicatorcolor=C["bg_medium"],
        )
        style.map(
            "Dark.TCheckbutton",
            background=[("active", C["bg_dark"]), ("disabled", C["bg_dark"])],
            foreground=[("disabled", C["text_muted"])],
            indicatorcolor=[("selected", C["accent"]), ("pressed", C["accent_hover"]), ("disabled", C["bg_medium"])],
        )

        # ═══════ Radiobutton 样式 ═══════
        style.configure(
            "Dark.TRadiobutton",
            background=C["bg_dark"],
            foreground=C["text_primary"],
            font=(F["family"], F["size_base"]),
            indicatorcolor=C["bg_medium"],
        )
        style.map(
            "Dark.TRadiobutton",
            background=[("active", C["bg_dark"]), ("disabled", C["bg_dark"])],
            foreground=[("disabled", C["text_muted"])],
            indicatorcolor=[("selected", C["accent"]), ("disabled", C["bg_medium"])],
        )

        # ═══════ LabelFrame 样式 ═══════
        style.configure(
            "Card.TLabelframe",
            background=C["bg_card"],
            foreground=C["text_primary"],
            bordercolor=C["border"],
            font=(F["family"], F["size_base"], "bold"),
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=C["bg_card"],
            foreground=C["accent_light"],
            font=(F["family"], F["size_base"], "bold"),
        )

        # ═══════ Separator 样式 ═══════
        style.configure("Dark.TSeparator", background=C["border"])

        # ═══════ Scrollbar 样式 ═══════
        style.configure(
            "Dark.Vertical.TScrollbar",
            background=C["bg_medium"],
            troughcolor=C["bg_dark"],
            bordercolor=C["bg_dark"],
            arrowcolor=C["text_muted"],
            relief="flat",
        )
        style.map("Dark.Vertical.TScrollbar", background=[("active", C["hover_light"]), ("pressed", C["accent"])])

        style.configure(
            "Dark.Horizontal.TScrollbar",
            background=C["bg_medium"],
            troughcolor=C["bg_dark"],
            bordercolor=C["bg_dark"],
            arrowcolor=C["text_muted"],
            relief="flat",
        )
        style.map("Dark.Horizontal.TScrollbar", background=[("active", C["hover_light"]), ("pressed", C["accent"])])

        # ═══════ Progressbar 样式 ═══════
        style.configure(
            "Accent.Horizontal.TProgressbar",
            background=C["accent"],
            troughcolor=C["bg_medium"],
            bordercolor=C["bg_dark"],
            lightcolor=C["accent_light"],
            darkcolor=C["accent_hover"],
        )

        # ═══════ Scale 样式 ═══════
        style.configure("Dark.TScale", background=C["bg_dark"], troughcolor=C["bg_medium"], bordercolor=C["bg_dark"])

        # ═══════ Spinbox 样式 ═══════
        style.configure(
            "Dark.TSpinbox",
            fieldbackground=C["bg_medium"],
            foreground=C["text_primary"],
            bordercolor=C["border"],
            arrowcolor=C["text_secondary"],
            borderwidth=P["borderwidth"],
            font=(F["family"], F["size_base"]),
            padding=list(P["entry_pad"]),
        )
        style.map(
            "Dark.TSpinbox",
            fieldbackground=[("focus", C["bg_light"]), ("disabled", C["bg_dark"])],
            bordercolor=[("focus", C["border_focus"])],
            foreground=[("disabled", C["text_muted"])],
            arrowcolor=[("disabled", C["text_muted"])],
        )

        # ═══════ 基础样式（未显式指定 style 的 ttk 控件也落在主题内）═══════
        # v3.4 前只有 Dark.* 命名样式，未指定 style 的控件退回 clam 默认浅色，
        # 全靠 polish_legacy 事后补救。这里把基础样式一并配置，
        # 新建控件**默认即主题**，润色只负责 tk 经典控件。
        style.configure("TFrame", background=C["bg_dark"])
        style.configure(
            "TLabel", background=C["bg_dark"], foreground=C["text_primary"], font=(F["family"], F["size_base"])
        )
        style.configure(
            "TButton",
            background=C["bg_light"],
            foreground=C["text_primary"],
            font=(F["family"], F["size_base"]),
            padding=list(P["secondary_pad"]),
            borderwidth=P["borderwidth"],
        )
        style.map(
            "TButton",
            background=[("active", C["hover_light"]), ("pressed", C["hover"]), ("disabled", C["bg_dark"])],
            foreground=[("disabled", C["text_muted"])],
        )
        style.configure(
            "TEntry",
            fieldbackground=C["bg_medium"],
            foreground=C["text_primary"],
            insertcolor=C["text_primary"],
            bordercolor=C["border"],
            lightcolor=C["border_light"],
            darkcolor=C["border"],
            borderwidth=P["borderwidth"],
            font=(F["family"], F["size_base"]),
            padding=list(P["entry_pad"]),
        )
        style.map(
            "TEntry",
            fieldbackground=[("focus", C["bg_light"]), ("disabled", C["bg_dark"]), ("invalid", C["error_bg"])],
            bordercolor=[("focus", C["border_focus"]), ("invalid", C["error"])],
            foreground=[("disabled", C["text_muted"])],
        )
        style.configure(
            "TCombobox",
            fieldbackground=C["bg_medium"],
            foreground=C["text_primary"],
            bordercolor=C["border"],
            arrowcolor=C["text_secondary"],
            borderwidth=P["borderwidth"],
            font=(F["family"], F["size_base"]),
            padding=list(P["entry_pad"]),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("focus", C["bg_light"]), ("readonly", C["bg_medium"]), ("disabled", C["bg_dark"])],
            bordercolor=[("focus", C["border_focus"])],
            arrowcolor=[("focus", C["accent_light"]), ("disabled", C["text_muted"])],
            foreground=[("disabled", C["text_muted"])],
        )
        style.configure(
            "TCheckbutton", background=C["bg_dark"], foreground=C["text_primary"], font=(F["family"], F["size_base"])
        )
        style.map(
            "TCheckbutton",
            background=[("active", C["bg_dark"])],
            foreground=[("disabled", C["text_muted"])],
            indicatorcolor=[("selected", C["accent"]), ("pressed", C["accent_hover"])],
        )
        style.configure(
            "TRadiobutton", background=C["bg_dark"], foreground=C["text_primary"], font=(F["family"], F["size_base"])
        )
        style.map(
            "TRadiobutton",
            background=[("active", C["bg_dark"])],
            foreground=[("disabled", C["text_muted"])],
            indicatorcolor=[("selected", C["accent"])],
        )
        style.configure("TLabelframe", background=C["bg_card"], foreground=C["text_primary"], bordercolor=C["border"])
        style.configure(
            "TLabelframe.Label", background=C["bg_card"], foreground=C["accent_text"], font=cls.font("label_bold")
        )
        style.configure("TNotebook", background=C["bg_dark"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=C["bg_medium"],
            foreground=C["text_secondary"],
            padding=list(P["tab_pad"]),
            font=(F["family"], F["size_base"]),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", C["accent"]), ("active", C["hover_light"])],
            foreground=[("selected", "white"), ("active", C["text_primary"]), ("disabled", C["text_muted"])],
        )
        style.configure(
            "Treeview",
            background=C["bg_card"],
            fieldbackground=C["bg_card"],
            foreground=C["text_primary"],
            rowheight=P["tree_row_height"],
            borderwidth=0,
            font=cls.font("label"),
        )
        style.configure(
            "Treeview.Heading",
            background=C["bg_medium"],
            foreground=C["text_secondary"],
            relief="flat",
            font=cls.font("label_bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", C["accent"])],
            foreground=[("selected", "white")],
        )
        style.map("Treeview.Heading", background=[("active", C["hover_light"])])
        style.configure(
            "Vertical.TScrollbar",
            background=C["bg_medium"],
            troughcolor=C["bg_dark"],
            bordercolor=C["bg_dark"],
            arrowcolor=C["text_muted"],
            relief="flat",
        )
        style.map("Vertical.TScrollbar", background=[("active", C["hover_light"]), ("pressed", C["accent"])])
        style.configure(
            "Horizontal.TScrollbar",
            background=C["bg_medium"],
            troughcolor=C["bg_dark"],
            bordercolor=C["bg_dark"],
            arrowcolor=C["text_muted"],
            relief="flat",
        )
        style.map("Horizontal.TScrollbar", background=[("active", C["hover_light"]), ("pressed", C["accent"])])
        style.configure(
            "Horizontal.TProgressbar",
            background=C["accent"],
            troughcolor=C["bg_medium"],
            bordercolor=C["bg_dark"],
            lightcolor=C["accent_light"],
            darkcolor=C["accent_hover"],
        )
        style.configure("TScale", background=C["bg_dark"], troughcolor=C["bg_medium"], bordercolor=C["bg_dark"])
        style.configure(
            "TSpinbox",
            fieldbackground=C["bg_medium"],
            foreground=C["text_primary"],
            bordercolor=C["border"],
            arrowcolor=C["text_secondary"],
            font=(F["family"], F["size_base"]),
            padding=list(P["entry_pad"]),
        )
        style.configure("TSeparator", background=C["border"])
        style.configure("TPanedwindow", background=C["bg_dark"])

        return style

    # D4（2026-09-17）：删除 `create_styled_button` / `create_styled_entry` /
    # `create_styled_text` / `create_styled_listbox` 四个工厂方法。
    # 理由（三条都经实测确认，缺一不可）：
    # 1. **全仓零引用**：`app/`、`tests/`、`scripts/`、`installer/`、`backend/`
    #    五处共 0 命中（定义本身除外），也无 getattr/command= 之类的动态调用；
    # 2. **是第二套视觉来源**：项目已确立 `app/panels/ui_kit.py` 为唯一视觉来源
    #    （card/toolbar/empty_state/…），保留这四只会在两处各写一遍配色，
    #    正是"同一事实写两处必然漂移"的高发区；
    # 3. **绕过字体令牌门禁**：它们用 `font=(cls.FONTS["family"], cls.FONTS["size_base"])`
    #    拼字面量，而全仓 385 处硬编码已统一迁到 `UIStyle.font(<角色>)`，
    #    门禁要求"全仓不得再有字面量" —— 这四只属于漏网。
