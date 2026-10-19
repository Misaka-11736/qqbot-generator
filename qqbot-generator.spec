# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件、无控制台、带图标和版本信息。"""

from pathlib import Path

ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "src" / "qqbot_core" / "prompts"), "qqbot_core/prompts"),
    (str(ROOT / "assets"), "assets"),
]

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["numpy", "faster_whisper", "edge_tts", "ctranslate2", "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "setuptools", "pip"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="QQBotGenerator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icon.ico"),
    version=str(ROOT / "version_info.txt"),
)
