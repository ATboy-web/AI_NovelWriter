# -*- mode: python ; coding: utf-8 -*-
"""
小说创作应用 PyInstaller 打包配置
"""

a = Analysis(
    ['../novel_app.py'],
    pathex=['..'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'novel_toolkit',
        'character_system',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'httpx',
        'json',
        'threading',
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
    name='AI_NovelWriter',
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
