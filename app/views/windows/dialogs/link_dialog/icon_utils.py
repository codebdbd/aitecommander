"""Icon utilities for the link dialog."""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QCoreApplication

from app.utils.ui.icon.path_service import icon_path_service

logger = logging.getLogger(__name__)

_TR_CONTEXT = "LinkDialogIconUtils"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


class IconErrorKind(Enum):
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    OS_ERROR = "os_error"
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
    """Try to create `QIcon` and return a typed result.

    Critical situations (permissions/OS errors) may raise when
    `raise_on_critical=True`.
    """
    if not icon_path_str:
        return IconResult(
            False,
            None,
            None,
            IconErrorKind.INVALID_PATH,
            None,
            _tr("Icon path is empty"),
        )

    candidates: list[Path]
    try:
        p = Path(icon_path_str)
        candidates = [p]
    except Exception as e:
        # Invalid path format
        if raise_on_critical:
            raise
        return IconResult(
            False,
            None,
            None,
            IconErrorKind.INVALID_PATH,
            e,
            _tr("Invalid path: {path}").format(path=icon_path_str),
        )

    # Append relative candidates
    try:
        candidates.append(icon_path_service.get_user_icons_dir() / icon_path_str)
    except (OSError, PermissionError) as e:
        if raise_on_critical:
            raise
        return IconResult(
            False,
            None,
            None,
            IconErrorKind.OS_ERROR,
            e,
            _tr("Failed to access user icons directory"),
        )
    try:
        candidates.append(icon_path_service.get_ui_icons_dir() / icon_path_str)
    except (OSError, PermissionError) as e:
        if raise_on_critical:
            raise
        return IconResult(
            False,
            None,
            None,
            IconErrorKind.OS_ERROR,
            e,
            _tr("Failed to access UI icons directory"),
        )

    # Find first existing candidate
    try:
        for c in candidates:
            try:
                if c.exists():
                    # `QIcon` does not throw, but keep for potential checks
                    return IconResult(True, QIcon(str(c)), c, None, None, "")
            except PermissionError as e:
                if raise_on_critical:
                    raise
                return IconResult(
                    False,
                    None,
                    c,
                    IconErrorKind.PERMISSION_DENIED,
                    e,
                    _tr("No access to file: {path}").format(path=c),
                )
            except OSError as e:
                if raise_on_critical:
                    raise
                return IconResult(
                    False,
                    None,
                    c,
                    IconErrorKind.OS_ERROR,
                    e,
                    _tr("OS error while checking file: {path}").format(path=c),
                )
    except Exception as e:
        if raise_on_critical:
            raise
        return IconResult(
            False,
            None,
            None,
            IconErrorKind.UNEXPECTED_ERROR,
            e,
            _tr("Unexpected error: {error}").format(error=e),
        )

    # Nothing found
    return IconResult(
        False,
        None,
        None,
        IconErrorKind.NOT_FOUND,
        None,
        _tr("Icon not found: {path}").format(path=icon_path_str),
    )


def make_icon(icon_path_str: str) -> Optional[QIcon]:
    """Create `QIcon` from absolute path or icons directories.

    Return `QIcon` or `None` and log detailed failure reasons:
    - not_found: path missing in all checked locations
    - permission_denied: access denied to file/directory
    - os_error: OS error while checking
    - invalid_path: invalid path format
    - unexpected_error: other exceptions
    """
    result = make_icon_result(icon_path_str, raise_on_critical=False)
    if result.success:
        return result.icon

    # Detailed logging per error kind
    if result.error_kind == IconErrorKind.NOT_FOUND:
        logger.info("Icon not found: %s", icon_path_str)
    elif result.error_kind == IconErrorKind.PERMISSION_DENIED:
        logger.warning("No access to icon '%s': %s", icon_path_str, result.message)
    elif result.error_kind == IconErrorKind.OS_ERROR:
        logger.warning(
            "OS error while accessing icon '%s': %s", icon_path_str, result.message
        )
    elif result.error_kind == IconErrorKind.INVALID_PATH:
        logger.warning(
            "Invalid icon path '%s': %s", icon_path_str, result.message
        )
    elif result.error_kind == IconErrorKind.UNEXPECTED_ERROR:
        logger.exception(
            "Unexpected error while creating icon '%s': %s",
            icon_path_str,
            result.message,
        )

    return None
