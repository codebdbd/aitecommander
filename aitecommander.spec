# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Aite Commander."""

from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH)

# ── Resources to bundle ──────────────────────────────────────────────
datas = [
    # Database schema and migrations
    (str(ROOT / "app" / "models" / "schema.sql"), "app/models"),
    (str(ROOT / "app" / "models" / "migrations"), "app/models/migrations"),
    # Themes (theme.json manifests)
    (str(ROOT / "app" / "resources" / "themes"), "app/resources/themes"),
    # QSS stylesheets
    (str(ROOT / "app" / "resources" / "qss"), "app/resources/qss"),
    # UI icons (per-theme and shared)
    (str(ROOT / "app" / "resources" / "ui_icons"), "app/resources/ui_icons"),
    # Logo
    (str(ROOT / "app" / "resources" / "logo"), "app/resources/logo"),
    # Compiled translations
    (str(ROOT / "i18n" / "*.qm"), "i18n"),
    # Config files
    (str(ROOT / "app" / "config_data" / "app_config.json"), "app/config_data"),
    (str(ROOT / "app" / "config_data" / "logging_config.json"), "app/config_data"),
]

# ── Hidden imports (PyQt6 plugins, pywin32) ─────────────────────────
hiddenimports = [
    "PyQt6.QtWidgets",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.sip",
    "win32api",
    "win32com",
    "win32com.client",
    "pywintypes",
    "pythoncom",
    "win32timezone",
    "cloudscraper",
    "cachetools",
    "pyparsing",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
]

a = Analysis(
    [str(ROOT / "app" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "brotli",
        "brotlicffi",
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AiteCommander",
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
    icon=str(ROOT / "app" / "resources" / "app_icon.ico"),
    version_info=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AiteCommander",
)
