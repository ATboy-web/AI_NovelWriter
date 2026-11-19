"""
导航和菜单管理模块
"""

import tkinter as tk


class NavigationManager:
    """菜单和导航栏管理"""

    def __init__(self, app):
        self.app = app

    def create_menu(self):
        """创建菜单栏"""
        menubar = tk.Menu(self.app.root)
        self.app.root.config(menu=menubar)

        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="新建小说", command=self.app._new_novel)
        file_menu.add_command(label="打开小说", command=self.app._open_novel)
        file_menu.add_separator()
        file_menu.add_command(label="续写当前小说", command=self.app._continue_novel)
        file_menu.add_command(label="续写第二部", command=self.app._create_sequel)
        file_menu.add_command(label="衍生同人作品", command=self.app._create_spinoff)
        file_menu.add_separator()
        file_menu.add_command(label="导出TXT", command=self.app._export_txt)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.app._on_close)

        # 创作菜单
        create_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="创作", menu=create_menu)
        create_menu.add_command(label="仿写风格", command=self.app._style_imitation)
        create_menu.add_separator()
        # 「生成角色传记」原先弹出自己的 Toplevel，而「角色传记」面板（biography）
        # 已有同名能力（AI 生成传记 / 保存 / 导出 / 转为故事线）。同一功能两套界面，
        # 所以菜单项改为**跳到面板**，而不是再维护一个独立弹窗。
        create_menu.add_command(
            label="生成角色传记",
            command=lambda: self.app._open_panel("biography"),
        )
        # 「补全角色人设」：自动检测出来的新角色只落骨架（category/faction/首现章），
        # 人设字段是空的，而后续章节的上下文注入读的正是这些字段。
        # ⚠️ 这个入口必须放在**菜单**里：角色卡片区在左栏滚动区底部
        # （内容高 1733px、可视 852px），放在那里用户根本翻不到。
        create_menu.add_command(label="补全角色人设", command=self.app._enrich_all_empty_characters)
        create_menu.add_command(label="生成书籍简介", command=self.app._generate_synopsis)

        # 设置菜单
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设置", menu=settings_menu)
        settings_menu.add_command(label="AI配置", command=self.app._show_settings)

        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="使用说明", command=self.app._show_help)
        help_menu.add_command(label="关于", command=self.app._show_about)
