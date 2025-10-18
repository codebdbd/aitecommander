from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QDir

_REGISTERED = False


def qInitResources() -> None:
    """Expose translation files via Qt search path."""
    global _REGISTERED
    if _REGISTERED:
        return
    base = Path(__file__).resolve().parent
    QDir.addSearchPath("i18n", str(base))
    _REGISTERED = True


def qCleanupResources() -> None:
    """Qt does not support removing search paths; track state only."""
    global _REGISTERED
    _REGISTERED = False
