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


# Fix for PyQt6 + pywin32 COM uninitialization crash on Windows exit
sys.coinit_flags = 2  # COINIT_APARTMENTTHREADED
try:
    import pythoncom
    pythoncom.CoInitialize()
except ImportError:
    pass

from app.core.constants import AppConstants

APP_NAME = AppConstants.APP_NAME


def _handle_early_cli_exit() -> int | None:
    """Handle CLI-only flags before importing GUI/PyQt runtime modules."""
    if not any(arg in {"--version", "-h", "--help"} for arg in sys.argv[1:]):
        return None

    from app.startup.argument_parser import parse_arguments

    try:
        parse_arguments()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 0
        return int(code)
    return 0


def main() -> int:
    """Run the Qt application."""
    early_exit_code = _handle_early_cli_exit()
    if early_exit_code is not None:
        return early_exit_code

    from app.core.error_handler import GlobalErrorHandler
    from app.startup.runtime import run

    GlobalErrorHandler.install()
    return run()


if __name__ == "__main__":
    code = main()
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    sys.exit(code)
