"""
导航和菜单管理模块
"""

import tkinter as tk
from tkinter import messagebox


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
        create_menu.add_command(label="生成角色传记", command=self.app._generate_character_biography)
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
