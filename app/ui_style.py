"""
UI样式管理模块 - 现代化UI样式
AI小说创作工坊 v2.0 设计系统
"""

import tkinter as tk
from tkinter import ttk


class UIStyle:
    """现代化UI样式 - 深色主题设计系统"""
    
    # ═══════════════════════════════════════════
    # 设计令牌 (Design Tokens)
    # ═══════════════════════════════════════════
    
    # 颜色系统 - 深色主题 v3.0
    COLORS = {
        # 背景色阶
        'bg_dark': '#0f0f1a',        # 主背景 - 最深
        'bg_medium': '#16162a',      # 次背景 - 面板
        'bg_light': '#1e1e38',       # 浅背景 - 卡片
        'bg_card': '#1e1e38',        # 卡片背景
        'bg_hover': '#252540',       # 悬停状态
        
        # 主色调 - 紫色系
        'accent': '#534ab7',         # 主色调
        'accent_light': '#a78bfa',   # 浅紫色
        'accent_hover': '#6a62d0',   # 悬停色
        'accent_bg': '#2d1b69',      # 紫色背景
        
        # 语义色
        'success': '#0f6e56',        # 成功绿
        'success_bg': '#064e3b',     # 成功背景
        'warning': '#f59e0b',        # 警告黄
        'warning_bg': '#78350f',     # 警告背景
        'error': '#ef4444',          # 错误红
        'error_bg': '#7f1d1d',       # 错误背景
        'info': '#3b82f6',           # 信息蓝
        'info_bg': '#1e3a5f',        # 信息背景
        
        # 文字色阶
        'text_primary': '#e0e0f0',   # 主文字
        'text_secondary': '#a0a0b0', # 次文字
        'text_muted': '#606080',     # 弱文字
        'text_inverse': '#ffffff',   # 反色文字
        
        # 边框色
        'border': '#2a2a40',         # 默认边框
        'border_light': '#3a3a55',   # 浅边框
        'border_focus': '#534ab7',   # 聚焦边框
        
        # 悬停背景
        'hover': '#252540',          # 悬停背景
        'hover_light': '#2a2a45',    # 浅悬停
    }
    
    # 字体系统
    FONTS = {
        'family': '微软雅黑',
        'family_mono': 'Consolas',
        'size_xs': 9,      # 辅助文字
        'size_sm': 10,     # 小文字
        'size_base': 11,   # 正文
        'size_lg': 13,     # 标题
        'size_xl': 15,     # 大标题
        'size_xxl': 18,    # 超大标题
    }
    
    # 间距系统 (4px 基准)
    SPACING = {
        'xs': 2,    # 2px
        'sm': 4,    # 4px
        'md': 8,    # 8px
        'lg': 12,   # 12px
        'xl': 16,   # 16px
        'xxl': 24,  # 24px
    }
    
    # 圆角系统
    RADIUS = {
        'sm': 4,    # 小组件
        'md': 6,    # 中组件
        'lg': 8,    # 大组件
        'xl': 12,   # 卡片
        'full': 999, # 胶囊
    }
    
    @classmethod
    def apply_theme(cls, root):
        """应用主题到根窗口"""
        style = ttk.Style()
        style.theme_use('clam')
        
        C = cls.COLORS
        F = cls.FONTS
        
        # 配置全局样式
        root.configure(bg=C['bg_dark'])
        
        # ═══════ Frame 样式 ═══════
        style.configure('Dark.TFrame', background=C['bg_dark'])
        style.configure('Card.TFrame', background=C['bg_card'])
        style.configure('Medium.TFrame', background=C['bg_medium'])
        style.configure('Accent.TFrame', background=C['accent_bg'])
        
        # ═══════ Label 样式 ═══════
        style.configure('Dark.TLabel', 
                       background=C['bg_dark'],
                       foreground=C['text_primary'],
                       font=(F['family'], F['size_base']))
        style.configure('Title.TLabel',
                       background=C['bg_dark'],
                       foreground=C['text_primary'],
                       font=(F['family'], F['size_xl'], 'bold'))
        style.configure('Heading.TLabel',
                       background=C['bg_dark'],
                       foreground=C['accent_light'],
                       font=(F['family'], F['size_lg'], 'bold'))
        style.configure('Subtitle.TLabel',
                       background=C['bg_dark'],
                       foreground=C['text_secondary'],
                       font=(F['family'], F['size_base']))
        style.configure('Accent.TLabel',
                       background=C['bg_dark'],
                       foreground=C['accent_light'],
                       font=(F['family'], F['size_base']))
        style.configure('Success.TLabel',
                       background=C['bg_dark'],
                       foreground=C['success'],
                       font=(F['family'], F['size_base']))
        style.configure('Warning.TLabel',
                       background=C['bg_dark'],
                       foreground=C['warning'],
                       font=(F['family'], F['size_base']))
        style.configure('Error.TLabel',
                       background=C['bg_dark'],
                       foreground=C['error'],
                       font=(F['family'], F['size_base']))
        style.configure('Muted.TLabel',
                       background=C['bg_dark'],
                       foreground=C['text_muted'],
                       font=(F['family'], F['size_sm']))
        
        # ═══════ Button 样式 ═══════
        # 主要按钮 - 紫色
        style.configure('Accent.TButton',
                       background=C['accent'],
                       foreground='white',
                       font=(F['family'], F['size_base'], 'bold'),
                       padding=(20, 10))
        style.map('Accent.TButton',
                 background=[('active', C['accent_hover']),
                           ('pressed', C['accent_hover']),
                           ('disabled', C['bg_light'])],
                 foreground=[('disabled', C['text_muted'])])
        
        # 次要按钮 - 灰色
        style.configure('Secondary.TButton',
                       background=C['bg_light'],
                       foreground=C['text_primary'],
                       font=(F['family'], F['size_base']),
                       padding=(16, 8))
        style.map('Secondary.TButton',
                 background=[('active', C['hover_light']),
                           ('pressed', C['hover']),
                           ('disabled', C['bg_dark'])],
                 foreground=[('disabled', C['text_muted'])])
        
        # 成功按钮 - 绿色
        style.configure('Success.TButton',
                       background=C['success'],
                       foreground='white',
                       font=(F['family'], F['size_base'], 'bold'),
                       padding=(20, 10))
        style.map('Success.TButton',
                 background=[('active', '#059669'),
                           ('pressed', '#047857')])
        
        # 危险按钮 - 红色
        style.configure('Danger.TButton',
                       background=C['error'],
                       foreground='white',
                       font=(F['family'], F['size_base'], 'bold'),
                       padding=(16, 8))
        style.map('Danger.TButton',
                 background=[('active', '#dc2626'),
                           ('pressed', '#b91c1c')])
        
        # 幽灵按钮 - 透明
        style.configure('Ghost.TButton',
                       background=C['bg_dark'],
                       foreground=C['accent_light'],
                       font=(F['family'], F['size_base']),
                       padding=(12, 6))
        style.map('Ghost.TButton',
                 background=[('active', C['hover']),
                           ('pressed', C['bg_light'])])
        
        # ═══════ Notebook 样式 ═══════
        style.configure('Dark.TNotebook',
                       background=C['bg_dark'],
                       borderwidth=0,
                       padding=[4, 4])
        style.configure('Dark.TNotebook.Tab',
                       background=C['bg_medium'],
                       foreground=C['text_secondary'],
                       padding=[20, 10],
                       font=(F['family'], F['size_base']))
        style.map('Dark.TNotebook.Tab',
                 background=[('selected', C['accent']),
                           ('active', C['hover_light'])],
                 foreground=[('selected', 'white'),
                           ('active', C['text_primary'])])
        
        # ═══════ Entry 样式 ═══════
        style.configure('Dark.TEntry',
                       fieldbackground=C['bg_medium'],
                       foreground=C['text_primary'],
                       insertcolor=C['text_primary'],
                       bordercolor=C['border'],
                       lightcolor=C['border_light'],
                       darkcolor=C['border'],
                       font=(F['family'], F['size_base']),
                       padding=[10, 8])
        style.map('Dark.TEntry',
                 fieldbackground=[('focus', C['bg_light']),
                                ('disabled', C['bg_dark'])],
                 bordercolor=[('focus', C['border_focus'])],
                 foreground=[('disabled', C['text_muted'])])
        
        # ═══════ Combobox 样式 ═══════
        style.configure('Dark.TCombobox',
                       fieldbackground=C['bg_medium'],
                       foreground=C['text_primary'],
                       bordercolor=C['border'],
                       arrowcolor=C['text_secondary'],
                       font=(F['family'], F['size_base']),
                       padding=[10, 8])
        style.map('Dark.TCombobox',
                 fieldbackground=[('focus', C['bg_light']),
                                ('readonly', C['bg_medium'])],
                 bordercolor=[('focus', C['border_focus'])],
                 arrowcolor=[('focus', C['accent_light'])])
        
        # ═══════ Checkbutton 样式 ═══════
        style.configure('Dark.TCheckbutton',
                       background=C['bg_dark'],
                       foreground=C['text_primary'],
                       font=(F['family'], F['size_base']),
                       indicatorcolor=C['bg_medium'])
        style.map('Dark.TCheckbutton',
                 background=[('active', C['bg_dark'])],
                 indicatorcolor=[('selected', C['accent']),
                               ('pressed', C['accent_hover'])])
        
        # ═══════ Radiobutton 样式 ═══════
        style.configure('Dark.TRadiobutton',
                       background=C['bg_dark'],
                       foreground=C['text_primary'],
                       font=(F['family'], F['size_base']),
                       indicatorcolor=C['bg_medium'])
        style.map('Dark.TRadiobutton',
                 background=[('active', C['bg_dark'])],
                 indicatorcolor=[('selected', C['accent'])])
        
        # ═══════ LabelFrame 样式 ═══════
        style.configure('Card.TLabelframe',
                       background=C['bg_card'],
                       foreground=C['text_primary'],
                       bordercolor=C['border'],
                       font=(F['family'], F['size_base'], 'bold'))
        style.configure('Card.TLabelframe.Label',
                       background=C['bg_card'],
                       foreground=C['accent_light'],
                       font=(F['family'], F['size_base'], 'bold'))
        
        # ═══════ Separator 样式 ═══════
        style.configure('Dark.TSeparator',
                       background=C['border'])
        
        # ═══════ Scrollbar 样式 ═══════
        style.configure('Dark.Vertical.TScrollbar',
                       background=C['bg_medium'],
                       troughcolor=C['bg_dark'],
                       bordercolor=C['bg_dark'],
                       arrowcolor=C['text_muted'],
                       relief='flat')
        style.map('Dark.Vertical.TScrollbar',
                 background=[('active', C['hover_light']),
                           ('pressed', C['accent'])])
        
        style.configure('Dark.Horizontal.TScrollbar',
                       background=C['bg_medium'],
                       troughcolor=C['bg_dark'],
                       bordercolor=C['bg_dark'],
                       arrowcolor=C['text_muted'],
                       relief='flat')
        
        # ═══════ Progressbar 样式 ═══════
        style.configure('Accent.Horizontal.TProgressbar',
                       background=C['accent'],
                       troughcolor=C['bg_medium'],
                       bordercolor=C['bg_dark'],
                       lightcolor=C['accent_light'],
                       darkcolor=C['accent_hover'])
        
        # ═══════ Scale 样式 ═══════
        style.configure('Dark.TScale',
                       background=C['bg_dark'],
                       troughcolor=C['bg_medium'],
                       bordercolor=C['bg_dark'])
        
        # ═══════ Spinbox 样式 ═══════
        style.configure('Dark.TSpinbox',
                       fieldbackground=C['bg_medium'],
                       foreground=C['text_primary'],
                       bordercolor=C['border'],
                       arrowcolor=C['text_secondary'],
                       font=(F['family'], F['size_base']),
                       padding=[10, 8])
        
        return style
    
    @classmethod
    def create_styled_button(cls, parent, text, command=None, style='Accent', **kwargs):
        """创建样式化按钮"""
        C = cls.COLORS
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            font=(cls.FONTS['family'], cls.FONTS['size_base']),
            relief=tk.FLAT,
            cursor='hand2',
            **kwargs
        )
        
        if style == 'Accent':
            btn.configure(bg=C['accent'], fg='white', activebackground=C['accent_hover'])
        elif style == 'Secondary':
            btn.configure(bg=C['bg_light'], fg=C['text_primary'], activebackground=C['hover_light'])
        elif style == 'Success':
            btn.configure(bg=C['success'], fg='white', activebackground='#059669')
        elif style == 'Danger':
            btn.configure(bg=C['error'], fg='white', activebackground='#dc2626')
        elif style == 'Ghost':
            btn.configure(bg=C['bg_dark'], fg=C['accent_light'], activebackground=C['hover'])
        
        return btn
    
    @classmethod
    def create_styled_entry(cls, parent, **kwargs):
        """创建样式化输入框"""
        C = cls.COLORS
        entry = tk.Entry(
            parent,
            font=(cls.FONTS['family'], cls.FONTS['size_base']),
            bg=C['bg_medium'],
            fg=C['text_primary'],
            insertbackground=C['text_primary'],
            relief=tk.FLAT,
            **kwargs
        )
        entry.configure(highlightbackground=C['border'], highlightcolor=C['border_focus'], highlightthickness=1)
        return entry
    
    @classmethod
    def create_styled_text(cls, parent, **kwargs):
        """创建样式化文本框"""
        C = cls.COLORS
        text = tk.Text(
            parent,
            font=(cls.FONTS['family'], cls.FONTS['size_base']),
            bg=C['bg_card'],
            fg=C['text_primary'],
            insertbackground=C['text_primary'],
            selectbackground=C['accent'],
            selectforeground='white',
            relief=tk.FLAT,
            padx=16,
            pady=16,
            spacing1=2,
            spacing3=2,
            undo=True,
            **kwargs
        )
        return text
    
    @classmethod
    def create_styled_listbox(cls, parent, **kwargs):
        """创建样式化列表框"""
        C = cls.COLORS
        listbox = tk.Listbox(
            parent,
            bg=C['bg_card'],
            fg=C['text_secondary'],
            font=(cls.FONTS['family'], cls.FONTS['size_sm']),
            selectbackground=C['accent'],
            selectforeground='white',
            relief=tk.FLAT,
            highlightthickness=0,
            borderwidth=0,
            **kwargs
        )
        return listbox
