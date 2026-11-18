# -*- mode: python ; coding: utf-8 -*-
"""
小说创作应用 PyInstaller 打包配置
"""

a = Analysis(
    ['../novel_app.py'],
    pathex=['..'],
    binaries=[],
    datas=[
        ('../novel_data', 'novel_data'),
    ],
    hiddenimports=[
        # ⚠️ 这里只需列「**动态导入**的目标」：PyInstaller 会静态跟踪 `import x`，
        # 但 `importlib.import_module("app.xxx")` 用的是字符串，分析器看不见。
        # 本仓的动态导入点只有三处（`app/__init__._safe_import`、
        # `app/panels/legacy.py`、`app/panels/registry.py`），对应下面三组条目。
        'app',
        'app.config',
        'app.ai_client',
        'app.image_generator',
        'app.scene_detector',
        'app.memory_manager',
        'app.note_manager',
        'app.fullscreen_writer',
        'app.novel_agent',
        'app.reading_manager',
        'app.ui_style',
        'app.writing_skills',
        'app.writing_skills_panel',
        # P2-1 巨石拆分产生的功能域 Mixin
        'app.shell_ui',
        'app.lifecycle_ui',
        'app.generation_ui',
        'app.character_ui',
        'app.outline_ui',
        'app.chapter_ui',
        'app.editor_ui',
        'app.reader_ui',
        'app.timeline_ui',
        'app.toolkit_ui',
        'app.persistence_ui',
        'app.note_ui',
        'app.parsing',
        # v3 P4 面板框架（registry 按字符串导入原生面板模块）
        'app.events',
        'app.events.bus',
        'app.panels',
        'app.panels.base',
        'app.panels.registry',
        'app.panels.legacy',
        'app.panels.host',
        # v3 P4b 原生面板（registry.NATIVE_PANEL_MODULES 按字符串导入）
        'app.panels.timeline_panel',
        'app.panels.biography_panel',
        'app.panels.lineage_panel',
        # 插图工坊面板（同上是按字符串导入，必须显式列出，否则打包后少一块）
        'app.panels.illustration_panel',
        # 插件中心面板（同上；插件系统本身由 app.writing_skills 静态 import）
        'app.panels.plugin_panel',
        'app.plugin_system',
        # MCP 服务器面板（同上；mcp_system 由 app.novel_agent 延迟 import，
        # 延迟 import 不产生静态依赖 ⇒ 必须显式列出，否则打包后少一块）
        'app.panels.mcp_panel',
        'app.mcp_system',
        # 技能库面板（同上；skill_library 只被面板与 novel_agent 延迟 import）
        'app.panels.skill_library_panel',
        'app.skill_library',
        # 回炉重造：面板 + 核心状态机（面板模块级 import，静态可见，但显式列出更稳）
        'app.panels.rework_panel',
        'app.rework',
        # 写作预设（把技能规则装配成阶段/体裁/长度三个维度的能力单元）。
        # 由 novel_agent 与技能库面板延迟 import ⇒ 必须显式列出。
        'app.writing_presets',
        # 风格 DNA / 语义候选 / 文本度量：均由上面两个模块**延迟 import**，
        # 静态分析看不到 ⇒ 必须显式列出，否则 EXE 里"按钮在、功能静默失效"。
        'app.style_dna',
        'app.semantic_candidates',
        # 评审落盘与一致性校验：同样由 novel_agent / generation_ui 延迟 import
        'app.review_store',
        'app.consistency',
        'app.text_stats',
        'app.timeline_store',
        'app.lineage',
        # v2 面板模块（legacy.py 按字符串导入）
        'app.panels.elements_panel',
        'app.panels.bridges_panel',
        'app.panels.descriptions_panel',
        'app.panels.dialogue_panel',
        'app.panels.story_flow_panel',
        'app.panels.style_panel',
        'app.panels.adapt_panel',
        'app.panels.websearch_panel',
        'app.panels.memory_viz_panel',
        'app.panels.summary_mgmt_panel',
        'app.panels.batch_ops_panel',
        'app.panels.chapter_analysis_panel',
        'app.storage',
        'app.novel_toolkit',
        'app.character_system',
        'app.format_converter',
        'app.cloud_storage',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.simpledialog',
        'tkinter.scrolledtext',
        'httpx',
        'json',
        'threading',
        'webbrowser',
        'loguru',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'PIL',
        'numpy',
        'pandas',
        'chromadb',
        'sentence_transformers',
        'fastapi',
        'uvicorn',
        'pydantic',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='../AI_NovelWriter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 改为False隐藏控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../icon.ico',
)
