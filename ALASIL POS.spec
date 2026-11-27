# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

bcrypt_datas, bcrypt_binaries, bcrypt_hiddenimports = collect_all("bcrypt")
crypto_datas, crypto_binaries, crypto_hiddenimports = collect_all("cryptography")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=bcrypt_binaries + crypto_binaries,
    datas=bcrypt_datas + crypto_datas,
    hiddenimports=bcrypt_hiddenimports + crypto_hiddenimports,
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
    [],
    exclude_binaries=True,
    name="ALASIL POS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ALASIL POS",
)
