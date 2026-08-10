# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for portable FareverAtlas.exe (Windows onefile)."""

from __future__ import annotations

import os
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parents[1]
APP_DIR = ROOT / "app"
ASSETS_DIR = ROOT / "assets"
BRIDGE_CANDIDATES = (
    ROOT / "native_bridge" / "farever-atlas-bridge.exe",
    ROOT / "native_bridge" / "target" / "release" / "farever-atlas-bridge.exe",
    ROOT
    / "native_bridge"
    / "target"
    / "x86_64-pc-windows-gnu"
    / "release"
    / "farever-atlas-bridge.exe",
)

bridge_src = next((path for path in BRIDGE_CANDIDATES if path.is_file()), None)
if bridge_src is None:
    raise SystemExit(
        "Bridge binary missing. Build with native_bridge/build.sh or place "
        "native_bridge/farever-atlas-bridge.exe before packaging."
    )

datas = [
    (str(ASSETS_DIR), "assets"),
    (str(bridge_src), "native_bridge"),
]

hiddenimports = [
    "farever_atlas",
    "farever_atlas.cli",
    "farever_atlas.portable",
    "farever_atlas.controller",
    "farever_atlas.telemetry",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
]

# App uses Core/Gui/Widgets only (SVG/WebP via Qt imageformat plugins, not QtSvg API).
# Excludes keep Addons / tooling stacks out even if the build venv is contaminated.
excludes = [
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuick3D",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtLocation",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSerialBus",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtDesigner",
    "PySide6.QtTest",
    "PySide6.QtHttpServer",
    "PySide6.QtRemoteObjects",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtNetworkAuth",
    "PySide6.QtNetwork",
    "PIL",
    "Pillow",
    "numpy",
    "matplotlib",
]

block_cipher = None

a = Analysis(
    [str(SPEC_DIR / "entry.py")],
    pathex=[str(APP_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="FareverAtlas",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
