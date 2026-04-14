from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QIcon

from app.utils.ui.icon.loading_service import icon_loading_service
from app.utils.ui.qt.gui_exec import run_in_gui_thread_async


def _is_theme_icon_path(candidate: str) -> bool:
    """Return True if icon path refers to a theme-relative or resource icon."""
    trimmed = candidate.strip()
    if not trimmed:
        return False

    if trimmed.startswith((":/", "qrc:/", "qresource:", "appres:")):
        return True

    lowered = trimmed.lower()
    if lowered.startswith(("file://", "http://", "https://")):
        return False

    if trimmed.startswith(("/", "\\")):
        return False

    if len(trimmed) > 1 and trimmed[1] == ":":
        return False

    ext = Path(trimmed).suffix.lower()
    if ext and ext not in (".svg", ".svgz"):
        return False

    # Reuse existing validation logic for theme icon names.
    try:
        from app.utils.ui.icon.cache_manager import _validate_icon_name
    except Exception:
        return False
    return _validate_icon_name(trimmed)


def get_icon(icon_path: Optional[str], *, source: str = "icon_service") -> QIcon:
    """Return QIcon for the given path using current cache/resolver rules."""
    if not icon_path:
        return QIcon()

    path = icon_path.strip()
    if not path:
        return QIcon()

    try:
        from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
    except Exception:
        icon_cache = None

    if icon_cache is not None and _is_theme_icon_path(path):
        try:
            icon = icon_cache.get_icon(path, source=source)
            if icon is not None and not icon.isNull():
                return icon
        except Exception:
            # fall through to path-based resolution
            pass

    return icon_loading_service.get_path_icon(path)


async def get_icon_async(icon_path: Optional[str], *, source: str = "icon_service") -> QIcon:
    """Async wrapper that executes icon creation in GUI thread."""
    return await run_in_gui_thread_async(lambda: get_icon(icon_path, source=source))
