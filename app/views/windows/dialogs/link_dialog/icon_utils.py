"""Icon utilities for the link dialog."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QIcon

from app.utils.ui.icon.loading_service import icon_loading_service

logger = logging.getLogger(__name__)

_TR_CONTEXT = "LinkDialogIconUtils"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


class IconErrorKind(Enum):
    NOT_FOUND = "not_found"
    INVALID_PATH = "invalid_path"
    UNEXPECTED_ERROR = "unexpected_error"


@dataclass
class IconResult:
    success: bool
    icon: Optional[QIcon]
    resolved_path: Optional[Path]
    error_kind: Optional[IconErrorKind] = None
    error: Optional[Exception] = None
    message: str = ""


def make_icon_result(
    icon_path_str: str, *, raise_on_critical: bool = False
) -> IconResult:
    """Resolve an icon path and return a typed result for link dialog consumers."""
    del raise_on_critical

    sanitized = str(icon_path_str or "").strip()
    if not sanitized:
        return IconResult(
            False,
            None,
            None,
            IconErrorKind.INVALID_PATH,
            None,
            _tr("Icon path is empty"),
        )

    try:
        resolved = icon_loading_service.resolve_existing_path(sanitized)
    except Exception as exc:  # noqa: BLE001
        return IconResult(
            False,
            None,
            None,
            IconErrorKind.UNEXPECTED_ERROR,
            exc,
            _tr("Unexpected error: {error}").format(error=exc),
        )

    if not resolved:
        return IconResult(
            False,
            None,
            None,
            IconErrorKind.NOT_FOUND,
            None,
            _tr("Icon not found: {path}").format(path=sanitized),
        )

    icon = icon_loading_service.get_path_icon(resolved)
    if icon.isNull():
        return IconResult(
            False,
            None,
            Path(resolved),
            IconErrorKind.NOT_FOUND,
            None,
            _tr("Icon not found: {path}").format(path=sanitized),
        )

    return IconResult(True, icon, Path(resolved), None, None, "")


def make_icon(icon_path_str: str) -> Optional[QIcon]:
    result = make_icon_result(icon_path_str, raise_on_critical=False)
    if result.success:
        return result.icon

    if result.error_kind == IconErrorKind.NOT_FOUND:
        logger.info("Icon not found: %s", icon_path_str)
    elif result.error_kind == IconErrorKind.INVALID_PATH:
        logger.warning("Invalid icon path '%s': %s", icon_path_str, result.message)
    elif result.error_kind == IconErrorKind.UNEXPECTED_ERROR:
        logger.exception(
            "Unexpected error while creating icon '%s': %s",
            icon_path_str,
            result.message,
        )
    return None


def get_cached_icon(icon_path_str: str) -> Optional[QIcon]:
    icon = make_icon(icon_path_str or "")
    if icon is None or icon.isNull():
        return None
    return icon

