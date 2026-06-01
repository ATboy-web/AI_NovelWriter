# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['app.api.new_features_routes', 'app.vector_store', 'app.vector_store.vector_manager', 'app.consistency_checker', 'app.consistency_checker.consistency_checker', 'app.finalization', 'app.finalization.finalization_manager', 'app.dialogue', 'app.dialogue.dialogue_manager', 'app.story_flow', 'app.story_flow.story_flow_manager', 'app.style_transfer', 'app.style_transfer.style_transfer_manager', 'app.description_library', 'app.description_library.description_manager', 'app.bridge_library', 'app.bridge_library.bridge_manager', 'app.generators', 'app.generators.novel_generator', 'app.core', 'app.core.config', 'app.api', 'app.api.routes', 'fastapi', 'uvicorn', 'pydantic', 'httpx'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    icon=['..\\..\\icon.ico'],
)
