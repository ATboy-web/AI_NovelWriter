# -*- mode: python ; coding: utf-8 -*-
"""
AI模型服务 PyInstaller 打包配置
"""

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# 收集数据文件
datas = []
datas += collect_data_files('chromadb')
datas += collect_data_files('sentence_transformers')

# 收集子模块
hiddenimports = []
hiddenimports += collect_submodules('chromadb')
hiddenimports += collect_submodules('sentence_transformers')
hiddenimports += collect_submodules('fastapi')
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('pydantic')

# 添加自定义模块
hiddenimports += [
    'app.core.config',
    'app.core.model_manager',
    'app.core.inference_engine',
    'app.api.routes',
]

a = Analysis(
    ['../backend/ai-service/run.py'],
    pathex=['../backend/ai-service'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'PIL',
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
    name='AI_NovelService',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../icon.ico',
)
