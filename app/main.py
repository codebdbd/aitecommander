"""Application entry point."""

from __future__ import annotations

import os
import sys

# Ensure sys.stdout and sys.stderr are non-None streams in PyInstaller windowed (--noconsole) mode
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# Add sys._MEIPASS to Windows DLL search directories in PyInstaller frozen mode
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    try:
        os.add_dll_directory(sys._MEIPASS)
        pywin_dir = os.path.join(sys._MEIPASS, "pywin32_system32")
        if os.path.isdir(pywin_dir):
            os.add_dll_directory(pywin_dir)
    except Exception:
        pass

# Prevent incomplete brotli/brotlicffi package from causing AttributeError in urllib3
for _b_mod in ("brotlicffi", "brotli"):
    try:
        _m = __import__(_b_mod)
        if not hasattr(_m, "error"):
            sys.modules[_b_mod] = None
    except Exception:
        sys.modules[_b_mod] = None

# Enable C-level traceback for segfaults if stderr is available
try:
    import faulthandler
    if sys.stderr is not None:
        faulthandler.enable()
except Exception:
    pass

# Fix for PyQt6 + pywin32 COM uninitialization crash on Windows exit
sys.coinit_flags = 2  # COINIT_APARTMENTTHREADED
try:
    import pythoncom
    pythoncom.CoInitialize()
except ImportError:
    pass

from app.core.constants import AppConstants
from app.core.error_handler import GlobalErrorHandler
from app.core.log_manager import LogManager
from app.startup.runtime import run

LogManager.setup()
GlobalErrorHandler.install()

APP_NAME = AppConstants.APP_NAME


def main() -> int:
    """Run the Qt application."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
