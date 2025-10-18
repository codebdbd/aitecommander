from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QDir

_REGISTERED = False


def qInitResources() -> None:
    """Expose application static assets via Qt search path."""
    global _REGISTERED
    if _REGISTERED:
        return
    base = Path(__file__).resolve().parent
    QDir.addSearchPath("appres", str(base))
    _REGISTERED = True


def qCleanupResources() -> None:
    """Reset registration state (Qt lacks API to remove search path)."""
    global _REGISTERED
    _REGISTERED = False
