# -*- mode: python ; coding: utf-8 -*-
"""
小说生成服务 PyInstaller 打包配置
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

# 添加自定义模块（所有app子包必须显式列出）
hiddenimports += [
    'app',
    'app.main',
    'app.core',
    'app.core.config',
    'app.generators',
    'app.generators.novel_generator',
    'app.api',
    'app.api.routes',
    'app.api.new_features_routes',
    'app.vector_store',
    'app.vector_store.vector_manager',
    'app.consistency_checker',
    'app.consistency_checker.consistency_checker',
    'app.finalization',
    'app.finalization.finalization_manager',
    'app.dialogue',
    'app.dialogue.dialogue_manager',
    'app.story_flow',
    'app.story_flow.story_flow_manager',
    'app.style_transfer',
    'app.style_transfer.style_transfer_manager',
    'app.description_library',
    'app.description_library.description_manager',
    'app.bridge_library',
    'app.bridge_library.bridge_manager',
]

a = Analysis(
    ['../backend/novel-service/run.py'],
    pathex=['../backend/novel-service'],
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
    name='NovelGenerator',
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
