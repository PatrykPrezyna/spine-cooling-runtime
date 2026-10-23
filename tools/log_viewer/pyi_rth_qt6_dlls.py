# Ensure bundled Qt6 DLLs are used before PyQt6.QtCore is imported.
# PyQt6 6.x keeps Qt6Core.dll in PyQt6/Qt6/bin, which Windows will not
# search unless it is on the DLL search path. Without this, a different
# Qt on PATH (for example Miniconda) can load and fail with
# "The specified procedure could not be found".

import os
import sys


def _add_dll_dir(path: str) -> None:
    if not path or not os.path.isdir(path):
        return
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(path)
    os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    meipass = sys._MEIPASS
    _add_dll_dir(meipass)
    _add_dll_dir(os.path.join(meipass, "PyQt6", "Qt6", "bin"))
