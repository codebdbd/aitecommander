"""Base classes for top panel widgets."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QSizePolicy, QToolButton

from app.utils.ui.icon.icon_resolver import get_default_icon_path
from app.views.widgets.link_button_mixin import LinkButtonMixin
from app.views.widgets.protocols import AppConfigWidgetAdapter, WidgetConfigProtocol

if TYPE_CHECKING:
    from app.views.widgets.base.base_widgets import BasePanelWidget
else:
    # Runtime import to avoid circular dependency
    from app.views.widgets.base.base_widgets import BasePanelWidget

logger = logging.getLogger(__name__)


class BaseTopPanelWidget(BasePanelWidget, LinkButtonMixin):
    """Base class for all top panel widgets with common signals and behavior."""

    # Unified signals
    actionRequested: pyqtSignal = pyqtSignal(object)
    refreshRequested: pyqtSignal = pyqtSignal(object)
    clearRequested: pyqtSignal = pyqtSignal()

    def __init__(
        self,
        main_window=None,
        config: Optional[WidgetConfigProtocol] = None,
        batch_size: int = 0,
    ):
        """Initialize base top panel widget.

        Args:
            main_window: Reference to main window
            config: Configuration provider (if None, uses app_config adapter)
            batch_size: If > 0, enables batched population to prevent UI freezes
        """
        super().__init__()
        self._main_window = main_window
        self._default_icon_path: Optional[Path] = None

        # IMPROVEMENT: Configuration dependency injection
        if config is None:
            try:
                from app.config_data import app_config

                config = AppConfigWidgetAdapter(app_config)
            except (ImportError, AttributeError) as e:
                logger.warning("Failed to load app_config, using None: %s", e)
        self._config = config

        # FIX: Batched loading with QTimer leak protection
        self._batch_size = max(0, batch_size)
        self._populate_timer: Optional[QTimer] = None
        self._pending_items: list[dict[str, Any]] = []
        self._create_button_func: Optional[
            Callable[[dict[str, Any]], Optional[QToolButton]]
        ] = None

        # Size policy is inherited from BasePanelWidget: (Minimum, Fixed) for horizontal compression

    def set_data(self, items: list[dict[str, Any]]) -> None:
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
            logger.debug("BaseTopPanelWidget: topbar adjust failed", exc_info=True)

    def _emit_action_safely(self, action_data: dict[str, Any]) -> None:
        """Safely emits actionRequested signal with error handling."""
        try:
            self.actionRequested.emit(action_data)
        except Exception as exc:
            logger.error("BaseTopPanelWidget: failed to emit actionRequested: %s", exc)

    def _emit_refresh_safely(self, refresh_data: dict[str, Any]) -> None:
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
        """Safely clears layout of widgets and spacers.

        FIX: Also removes ``QSpacerItem`` instances to prevent leaks.
        """
        while self.panel_layout.count():
            item = self.panel_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.spacerItem():
                # Explicitly delete spacer to prevent memory leaks
                del item

    def _populate_panel(
        self,
        items: list[dict[str, Any]],
        create_button_func: Callable[[dict[str, Any]], Optional[QToolButton]],
    ) -> None:
        """Clear the panel and populate it with link buttons.

        IMPROVEMENT: Supports batched mode to prevent UI freezes. When
        ``batch_size`` > 0 the method uses asynchronous loading via ``QTimer``.
        """
        self._clear_layout()

        if self._batch_size > 0:
            self._populate_batched(items, create_button_func)
        else:
            self._populate_sync(items, create_button_func)

    def _populate_sync(
        self,
        items: list[dict[str, Any]],
        create_func: Callable[[dict[str, Any]], Optional[QToolButton]],
    ) -> None:
        """Populate synchronously for small datasets."""
        self.setUpdatesEnabled(False)
        try:
            for i, link in enumerate(items):
                try:
                    button = create_func(link)
                except Exception:
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
        finally:
            self._finish_populate()

    def _populate_batched(
        self,
        items: list[dict[str, Any]],
        create_func: Callable[[dict[str, Any]], Optional[QToolButton]],
    ) -> None:
        """Populate using batches to prevent UI freezes.

        FIX: Uses ``QTimer`` with ``isVisible()`` checks to avoid callbacks on
        destroyed widgets.
        """
        self._pending_items = list(items)
        self._create_button_func = create_func
        self.setUpdatesEnabled(False)

        # FIX: Create timer with ``self`` as parent to ensure automatic cleanup
        if self._populate_timer is None:
            self._populate_timer = QTimer(self)
            self._populate_timer.setSingleShot(True)
            self._populate_timer.timeout.connect(self._process_batch)

        self._process_batch()

    def _process_batch(self) -> None:
        """Process one batch of items.

        FIX: Checks ``isVisible()`` before processing to prevent calls after
        ``deleteLater()``.
        """
        # CRITICAL: Ensure the widget is still alive and visible
        if not self.isVisible() or not self._pending_items:
            self._finish_populate()
            return

        batch = self._pending_items[: self._batch_size]
        self._pending_items = self._pending_items[self._batch_size :]

        for i, link in enumerate(batch):
            try:
                button = self._create_button_func(link)
                if button:
                    self.panel_layout.addWidget(button)
            except Exception:
                logger.exception("Failed to create button for %s", link.get("name"))
                continue

            if button is not None:
                self.panel_layout.addWidget(button)
            else:
                logger.debug(
                    "create_button_func returned None for element %d: %s",
                    i,
                    link.get("name", "Unknown"),
                )

        # Schedule next batch
        if self._pending_items and self._populate_timer:
            self._populate_timer.start(0)
        else:
            self._finish_populate()

    def _finish_populate(self) -> None:
        """Finalize population."""
        try:
            if self.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding:
                self.panel_layout.addStretch()
        except (AttributeError, RuntimeError) as e:
            logger.warning("Failed to add stretch to layout: %s", e)

        self.setUpdatesEnabled(True)

        try:
            self.updateGeometry()
        except (RuntimeError, AttributeError) as e:
            logger.debug("updateGeometry failed: %s", e)

        # Cleanup
        self._pending_items = []
        self._create_button_func = None

    def closeEvent(self, event) -> None:
        """Cancel pending batches on close.

        FIX: Stops the timer on close to prevent callbacks on a destroyed widget.
        """
        if self._populate_timer and self._populate_timer.isActive():
            self._populate_timer.stop()
            logger.debug("BaseTopPanelWidget: cancelled pending populate batches")
        super().closeEvent(event)
