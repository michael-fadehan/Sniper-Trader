# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['sniper_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('logo.png', '.'), ('logo.ico', '.'), ('Turbo User Manual (v1).pdf', '.'), ('Product Requirements Document.pdf', '.'), ('venv/Lib/site-packages/coincurve/libsecp256k1.dll', 'coincurve')],
    hiddenimports=[],
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
    name='sniper_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['logo.ico'],
)
