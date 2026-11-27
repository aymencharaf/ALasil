# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

project_root = Path(SPECPATH).resolve()
script_path = project_root / "ALASIL ACTIV" / "license_gen.py"

crypto_datas, crypto_binaries, crypto_hidden = collect_all("cryptography")

hidden = crypto_hidden
hidden += collect_submodules("PySide6.QtCore")
hidden += collect_submodules("PySide6.QtGui")
hidden += collect_submodules("PySide6.QtWidgets")

a = Analysis(
    [str(script_path)],
    pathex=[str(project_root), str(script_path.parent)],
    binaries=crypto_binaries,
    datas=crypto_datas,
    hiddenimports=hidden,
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
    name="ALASIL_License_Gen",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
