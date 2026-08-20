# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: Windows log viewer with no Python install required."""

from pathlib import Path

import PyQt6

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
PYQT_BIN = Path(PyQt6.__file__).resolve().parent / "Qt6" / "bin"

# QtCore.pyd loads Qt6Core.dll from PyQt6/Qt6/bin. Copy the load-time
# DLLs to the bundle root as well so Windows finds them.
_FLAT_DLLS = (
    "Qt6Core.dll",
    "Qt6Gui.dll",
    "Qt6Widgets.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "vcruntime140_threads.dll",
    "concrt140.dll",
    "opengl32sw.dll",
)
flat_binaries = []
for name in _FLAT_DLLS:
    dll = PYQT_BIN / name
    if dll.is_file():
        flat_binaries.append((str(dll), "."))

a = Analysis(
    [str(SRC / "log_analyzer.py")],
    pathex=[str(SRC)],
    binaries=flat_binaries,
    datas=[],
    hiddenimports=[
        "cooling_power",
        "fault_catalog",
        "gui",
        "session_logs",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.sip",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "packaging" / "pyi_rth_qt6_dlls.py")],
    excludes=[
        "matplotlib",
        "pandas",
        "numpy",
        "PIL",
        "tkinter",
        "usb",
        "serial",
        "adafruit_blinka",
        "adafruit_platformdetect",
        "adafruit_circuitpython_ads1x15",
        "pigpio",
        "RPi",
        "smbus2",
    ],
    noarchive=False,
)

# Qt6Core.dll needs Windows inbox ICU (System32\icuuc.dll). PyInstaller
# otherwise pulls Miniconda's ICU 78, whose exports are version-suffixed
# and fail with "The specified procedure could not be found".
a.binaries = [
    dest_src
    for dest_src in a.binaries
    if not (
        Path(dest_src[0]).name.lower().startswith("icu")
        and "miniconda" in str(dest_src[1]).lower()
    )
]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SpineCoolingLogViewer",
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
