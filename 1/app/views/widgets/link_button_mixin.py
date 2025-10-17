"""Mixin with common logic for creating link buttons and resolving icons.

Usage:
- The host class must provide `_get_default_icon_path()` which returns a
  ``pathlib.Path`` to the default icon (with caching).
- The mixin adds `_find_icon` and `_create_link_button` methods.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtCore import QCoreApplication, QSize
from PyQt6.QtWidgets import QSizePolicy, QToolButton

from app.config_data import app_config
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import (
    resolve_icon_for_link,
    resolve_icon_path,
)
from app.views.widgets.protocols import IconProviderProtocol

logger = logging.getLogger(__name__)

_TR_CONTEXT = "LinkButtonMixin"


def _tr(text: str) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text)


class LinkButtonMixin:
    """Mixin for creating link buttons with icon resolution.

    This mixin expects to be used with a class that implements IconProviderProtocol.
    """

    # Type hint for the host class
    if TYPE_CHECKING:

        def __init__(self: IconProviderProtocol) -> None: ...

    def _icon_provider(self) -> IconProviderProtocol:
        """Return host typed as ``IconProviderProtocol`` with validation."""

        provider = cast(IconProviderProtocol, self)
        if not hasattr(provider, "_get_default_icon_path"):
            raise NotImplementedError(
                "Host widget must implement _get_default_icon_path()"
            )
        return provider

    def _default_icon_path_str(self) -> str:
        """Return ``str`` path to the default icon."""

        provider = self._icon_provider()
        return str(provider._get_default_icon_path())

    def _find_icon(self, icon_path: str) -> str:
        """Return icon path via the common resolver with a fallback."""
        if not icon_path:
            return self._default_icon_path_str()
        try:
            resolved = resolve_icon_path(icon_path)
            return resolved or self._default_icon_path_str()
        except (OSError, FileNotFoundError, PermissionError) as e:
            logger.warning("Failed to resolve icon path '%s': %s", icon_path, e)
            return self._default_icon_path_str()
        except Exception as e:
            logger.exception(
                "Unexpected error while resolving icon '%s': %s", icon_path, e
            )
            return self._default_icon_path_str()

    def _create_link_button(self, link_data: dict[str, Any]) -> QToolButton:
        """Create a link button with an icon, synchronized with the table."""
        button = QToolButton()

        button_size = app_config.ui.get_top_panel_button_size()
        icon_size = app_config.ui.get_top_panel_icon_size()
        button.setFixedSize(button_size, button_size)
        button.setIconSize(QSize(icon_size[0], icon_size[1]))
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        try:
            resolved_path = self._find_icon(resolve_icon_for_link(link_data))
            icon = create_icon_from_path(resolved_path)
            # Fallback: if icon not created or is empty — use default
            if not icon or getattr(icon, "isNull", lambda: True)():
                fallback_path = self._default_icon_path_str()
                logger.warning(
                    "Icon not created/empty for link %r (path=%s). Using default: %s",
                    link_data.get("name"),
                    resolved_path,
                    fallback_path,
                )
                icon = create_icon_from_path(fallback_path)
            button.setIcon(icon)
            # Diagnostics of actual sizes and DPR
            try:
                from PyQt6.QtCore import QSize as _QSize
                from PyQt6.QtGui import QGuiApplication

                req_size = _QSize(icon_size[0], icon_size[1])
                actual = icon.actualSize(req_size)
                screen = QGuiApplication.primaryScreen()
                dpr = float(screen.devicePixelRatio()) if screen is not None else 1.0
                logger.debug(
                    "[TopBarIconDiag] name=%r path=%s req=%sx%s actual=%sx%s btn=%sx%s DPR=%.2f",
                    link_data.get("name"),
                    resolved_path,
                    req_size.width(),
                    req_size.height(),
                    actual.width(),
                    actual.height(),
                    button.size().width(),
                    button.size().height(),
                    dpr,
                )
            except Exception as diag_exc:
                logging.debug(
                    "[TopBarIconDiag] failed to log diagnostics: %s", diag_exc
                )
        except Exception as e:
            logger.warning(
                "Failed to create icon for link '%s': %s",
                link_data.get("name", "Unknown"),
                e,
            )
            # Ensure visual feedback — set default icon
            try:
                fallback_path = self._default_icon_path_str()
                button.setIcon(create_icon_from_path(fallback_path))
            except Exception:
                pass

        button.setToolTip(link_data.get("name", _tr("Unknown link")))
        return button
