"""Base classes for top panel widgets."""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QSizePolicy

from app.utils.ui.icon.icon_resolver import get_default_icon_path
from app.views.base_widgets import BasePanelWidget
from app.views.link_button_mixin import LinkButtonMixin

logger = logging.getLogger(__name__)


class BaseTopPanelWidget(BasePanelWidget, LinkButtonMixin):
    """Base class for all top panel widgets with common signals and behavior."""

    # Unified signals
    actionRequested: pyqtSignal = pyqtSignal(object)
    refreshRequested: pyqtSignal = pyqtSignal(object)
    clearRequested: pyqtSignal = pyqtSignal()

    def __init__(self, main_window=None):
        super().__init__()
        self._main_window = main_window
        self._default_icon_path: Optional[Path] = None

        # Size policy наследуется из BasePanelWidget: (Minimum, Fixed) для горизонтального сжатия

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
            logger.debug(
                "BaseTopPanelWidget: topbar adjust failed", exc_info=True
            )

    def _emit_action_safely(self, action_data: Dict[str, Any]) -> None:
        """Safely emits actionRequested signal with error handling."""
        try:
            self.actionRequested.emit(action_data)
        except Exception as exc:
            logger.error("BaseTopPanelWidget: failed to emit actionRequested: %s", exc)

    def _emit_refresh_safely(self, refresh_data: Dict[str, Any]) -> None:
        """Safely emits refreshRequested signal with error handling."""
        try:
            self.refreshRequested.emit(refresh_data)
        except Exception as exc:
            logger.error("BaseTopPanelWidget: failed to emit refreshRequested: %s", exc)

    def _get_default_icon_path(self) -> Path:
        """Returns path to default icon with caching."""
        if self._default_icon_path is None:
            self._default_icon_path = get_default_icon_path()
        return self._default_icon_path

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
        create_button_func: Callable[[Dict[str, Any]], Optional[object]],
    ) -> None:
        """Clears panel and populates with link buttons."""
        self.setUpdatesEnabled(False)
        try:
            self._clear_layout()

            for i, link in enumerate(items):
                try:
                    button = create_button_func(link)
                except Exception:
                    # Detailed diagnostics for easier debugging
                    link_info = {
                        "index": i,
                        "id": link.get("id", "Unknown"),
                        "name": link.get("name", "Unknown"),
                        "url": link.get("url", "Unknown")[:50]
                        if link.get("url")
                        else "Unknown",
                    }
                    logger.exception(
                        "Failed to create button for panel element %s", link_info
                    )
                    continue

                if button is not None:
                    self.panel_layout.addWidget(button)
                else:
                    logger.debug(
                        "create_button_func returned None for element %d: %s",
                        i,
                        link.get("name", "Unknown"),
                    )

            try:
                if self.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding:
                    self.panel_layout.addStretch()
            except (AttributeError, RuntimeError) as e:
                logger.warning("Failed to add stretch to layout: %s", e)
                
            # Сброс максимальной ширины после заполнения панели
            try:
                self.setMaximumWidth(16777215)  # Максимальное значение ширины
            except Exception:
                logger.debug(
                    "BaseTopPanelWidget: setMaximumWidth failed after populate",
                    exc_info=True,
                )
        finally:
            self.setUpdatesEnabled(True)
            try:
                self.updateGeometry()
            except Exception:
                logger.debug(
                    "BaseTopPanelWidget: updateGeometry failed after populate",
                    exc_info=True,
                )
