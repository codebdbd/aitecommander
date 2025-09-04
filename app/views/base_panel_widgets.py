"""Base classes for top panel widgets."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from PyQt6.QtCore import pyqtSignal, QSize
from PyQt6.QtWidgets import QSizePolicy, QToolButton

from app.config_data import app_config
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import get_default_icon_path, resolve_icon_for_link, resolve_icon_path
from app.views.base_widgets import BasePanelWidget


class BaseTopPanelWidget(BasePanelWidget):
    """Base class for all top panel widgets with common signals and behavior."""

    # Unified signals
    actionRequested: pyqtSignal = pyqtSignal(object)
    refreshRequested: pyqtSignal = pyqtSignal(object)
    clearRequested: pyqtSignal = pyqtSignal()

    def __init__(self, main_window=None):
        super().__init__()
        self._main_window = main_window
        self._default_icon_path: Optional[Path] = None
        
        # Common size policy for all top panel widgets
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_data(self, items: List[Dict[str, Any]]) -> None:
        """Sets panel data - to be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement set_data")

    def update(self) -> None:
        """Requests data update from external sources."""
        # Base implementation does nothing to avoid circular refresh paths
        return

    def clear(self) -> None:
        """Initiates clearing - to be implemented by subclasses if needed."""
        pass

    def _sync_topbar_layout(self) -> None:
        """Synchronously recalculates top bar to avoid search size switching."""
        try:
            mgr = getattr(self._main_window, "_topbar_manager", None)
            if mgr:
                mgr.adjust()
        except Exception:
            pass

    def _emit_action_safely(self, action_data: Dict[str, Any]) -> None:
        """Safely emits actionRequested signal with error handling."""
        try:
            self.actionRequested.emit(action_data)
        except Exception as exc:
            logging.error("BaseTopPanelWidget: failed to emit actionRequested: %s", exc)

    def _emit_refresh_safely(self, refresh_data: Dict[str, Any]) -> None:
        """Safely emits refreshRequested signal with error handling."""
        try:
            self.refreshRequested.emit(refresh_data)
        except Exception as exc:
            logging.error("BaseTopPanelWidget: failed to emit refreshRequested: %s", exc)

    def _get_default_icon_path(self) -> Path:
        """Returns path to default icon with caching."""
        if self._default_icon_path is None:
            self._default_icon_path = get_default_icon_path()
        return self._default_icon_path

    def _find_icon(self, icon_path: str) -> str:
        """Returns icon path through common resolver with fallback."""
        if not icon_path:
            return str(self._get_default_icon_path())
        try:
            resolved = resolve_icon_path(icon_path)
            return resolved or str(self._get_default_icon_path())
        except (OSError, FileNotFoundError, PermissionError) as e:
            logging.warning("Failed to resolve icon path '%s': %s", icon_path, e)
            return str(self._get_default_icon_path())
        except Exception as e:
            logging.exception("Unexpected error resolving icon '%s': %s", icon_path, e)
            return str(self._get_default_icon_path())

    def _create_link_button(self, link_data: Dict[str, Any]) -> QToolButton:
        """Creates a link button with icon synchronized with table."""
        button = QToolButton()

        button_size = app_config.ui.get_top_panel_button_size()
        icon_size = app_config.ui.get_top_panel_icon_size()
        button.setFixedSize(button_size, button_size)
        button.setIconSize(QSize(icon_size[0], icon_size[1]))
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        try:
            resolved_path = self._find_icon(resolve_icon_for_link(link_data))
            icon = create_icon_from_path(resolved_path)
            # Fallback: if icon not created or empty - use default
            if not icon or getattr(icon, "isNull", lambda: True)():
                fallback_path = str(self._get_default_icon_path())
                logging.warning(
                    "Icon not created/empty for link %r (path=%s). Using default: %s",
                    link_data.get("name"),
                    resolved_path,
                    fallback_path,
                )
                icon = create_icon_from_path(fallback_path)
            button.setIcon(icon)
        except Exception as e:
            logging.warning("Failed to create icon for link '%s': %s", link_data.get("name", "Unknown"), e)
            # Guarantee visual feedback - set default icon
            try:
                fallback_path = str(self._get_default_icon_path())
                button.setIcon(create_icon_from_path(fallback_path))
            except Exception:
                pass

        button.setToolTip(link_data.get("name", "Unknown link"))
        return button

    def _clear_layout(self):
        """Safely clears layout of widgets."""
        while self.panel_layout.count():
            item = self.panel_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _populate_panel(
        self,
        items: List[Dict[str, Any]],
        create_button_func: Callable[[Dict[str, Any]], Optional[QToolButton]],
    ) -> None:
        """Clears panel and populates with link buttons."""
        self._clear_layout()

        for i, link in enumerate(items):
            try:
                button = create_button_func(link)
            except Exception:
                # Detailed diagnostics for easier debugging
                link_info = {
                    'index': i,
                    'id': link.get('id', 'Unknown'),
                    'name': link.get('name', 'Unknown'),
                    'url': link.get('url', 'Unknown')[:50] if link.get('url') else 'Unknown'
                }
                logging.exception(
                    "Failed to create button for panel element %s", 
                    link_info
                )
                continue

            if button is not None:
                self.panel_layout.addWidget(button)
            else:
                logging.debug("create_button_func returned None for element %d: %s", i, link.get('name', 'Unknown'))

        try:
            if self.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding:
                self.panel_layout.addStretch()
        except (AttributeError, RuntimeError) as e:
            logging.warning("Failed to add stretch to layout: %s", e)
