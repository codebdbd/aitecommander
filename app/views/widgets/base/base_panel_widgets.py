"""Base classes for top panel widgets."""

import copy
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QSizePolicy, QToolButton

from app.utils.ui.icon.icon_resolver import get_default_icon_path
from app.views.widgets.link_button_mixin import LinkButtonMixin
from app.views.widgets.protocols import (
    AppConfigWidgetAdapter,
    UpdateContext,
    UpdateStatus,
    WidgetConfigProtocol,
)

if TYPE_CHECKING:
    from app.views.widgets.base.base_widgets import BasePanelWidget
else:
    # Runtime import to avoid circular dependency
    from app.views.widgets.base.base_widgets import BasePanelWidget

logger = logging.getLogger(__name__)
DEFAULT_PANEL_BATCH_INTERVAL_MS = 16


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
                from app.config_data.runtime_config import runtime_app_config as app_config

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
        self._populate_version = 0
        self._scheduled_populate_version = 0
        self._last_items: list[dict[str, Any]] = []
        self._update_status = UpdateStatus.IDLE
        self._update_context: Optional[UpdateContext] = None

        # FIX: Batched adjust() to avoid multiple layout recalculations during startup
        self._adjust_timer: Optional[QTimer] = None
        self._adjust_pending = False

        self._placeholder_enforced = False
        self._content_expected = False
        self._content_added = False

        # Size policy is inherited from BasePanelWidget: (Minimum, Fixed) for horizontal compression

    def set_data(self, items: list[dict[str, Any]]) -> None:
        """Sets panel data - to be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement set_data")

    def update_data(
        self,
        data: list[dict[str, Any]],
        options: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Unified lifecycle API: apply data and optionally request refresh."""
        _ = options
        try:
            self._update_status = UpdateStatus.UPDATING
            self._update_context = UpdateContext(item_count=len(data))
            self.set_data(data)
            return True
        except Exception:
            self._update_status = UpdateStatus.ERROR
            if self._update_context is not None:
                self._update_context.error_count += 1
            logger.exception("BaseTopPanelWidget: update_data failed")
            return False

    def get_update_status(self) -> UpdateStatus:
        """Return current panel update status."""
        return self._update_status

    def cancel_update(self) -> bool:
        """Cancel batched population and mark update as cancelled."""
        cancelled = False
        self._populate_version += 1
        self._scheduled_populate_version = self._populate_version
        if self._populate_timer and self._populate_timer.isActive():
            self._populate_timer.stop()
            cancelled = True
        if self._pending_items:
            self._pending_items = []
            cancelled = True
        self._create_button_func = None
        if cancelled:
            self.setUpdatesEnabled(True)
            self._update_status = UpdateStatus.CANCELLED
            if self._update_context is not None:
                self._update_context.is_cancelled = True
            self._sync_topbar_layout()
        return cancelled

    def clear_data(self) -> None:
        """Clear panel data via unified update API."""
        try:
            self.cancel_update()
            self.clear()
            self._clear_layout()
            self._update_status = UpdateStatus.IDLE
            self._sync_topbar_layout()
        except Exception:
            self._update_status = UpdateStatus.ERROR
            logger.exception("BaseTopPanelWidget: clear_data failed")

    def refresh(self) -> bool:
        """Request external refresh through unified signal."""
        try:
            self._emit_refresh_safely({})
            return True
        except Exception:
            self._update_status = UpdateStatus.ERROR
            logger.exception("BaseTopPanelWidget: refresh failed")
            return False

    def get_items(self) -> list[dict[str, Any]]:
        """Return a deep copy of the last items applied to the panel."""
        try:
            return copy.deepcopy(self._last_items)
        except Exception:
            return list(self._last_items)

    def update(self, *args, **kwargs) -> None:
        """Requests data update from external sources."""
        # Base implementation does nothing to avoid circular refresh paths
        super().update(*args, **kwargs)

    def clear(self) -> None:
        """Initiates clearing - to be implemented by subclasses if needed."""
        self._last_items = []

    def _sync_topbar_layout(self) -> None:
        """Synchronously recalculates top bar to avoid search size switching.
        
        FIX: Использует батчинг через QTimer для предотвращения множественных
        вызовов adjust() во время загрузки данных панелей.
        """
        try:
            # FIX: Отложить adjust() через таймер для батчинга
            if self._adjust_pending:
                return  # Уже запланирован
            
            self._adjust_pending = True
            
            if self._adjust_timer is None:
                self._adjust_timer = QTimer(self)
                self._adjust_timer.setSingleShot(True)
                self._adjust_timer.timeout.connect(self._execute_adjust)
            
            # Отложить на 10ms — достаточно для батчинга всех set_data()
            self._adjust_timer.start(10)
        except Exception:
            logger.debug("BaseTopPanelWidget: failed to schedule adjust", exc_info=True)
            self._adjust_pending = False
    
    def _execute_adjust(self) -> None:
        """Выполнить отложенный adjust()."""
        try:
            self._adjust_pending = False
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
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
                continue
            spacer = item.spacerItem()
            if spacer is not None:
                # Explicitly delete spacer to prevent memory leaks
                del spacer
        # Ensure placeholder width remains in effect while layout is empty
        self._ensure_placeholder_width(True)

    def _populate_panel(
        self,
        items: list[dict[str, Any]],
        create_button_func: Callable[[dict[str, Any]], Optional[QToolButton]],
    ) -> None:
        """Clear the panel and populate it with link buttons.

        IMPROVEMENT: Supports batched mode to prevent UI freezes. When
        ``batch_size`` > 0 the method uses asynchronous loading via ``QTimer``.
        """
        try:
            self._last_items = copy.deepcopy(items)
        except Exception:
            self._last_items = list(items)

        self._content_expected = bool(items)
        self._content_added = False
        self._update_status = UpdateStatus.UPDATING
        self._update_context = UpdateContext(item_count=len(items))

        # Keep placeholder width enforced while new data is being loaded
        self._ensure_placeholder_width(True)
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
        """Populate synchronously for small datasets.
        
        Uses setUpdatesEnabled(False) to prevent visual glitches during population.
        """
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
                    self._content_added = True
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
        self._populate_version += 1
        self._scheduled_populate_version = self._populate_version

        # FIX: Create timer with ``self`` as parent to ensure automatic cleanup
        if self._populate_timer is None:
            self._populate_timer = QTimer(self)
            self._populate_timer.setSingleShot(True)
            self._populate_timer.timeout.connect(self._process_scheduled_batch)
        elif self._populate_timer.isActive():
            self._populate_timer.stop()

        self._process_batch(self._populate_version)

    def _process_scheduled_batch(self) -> None:
        """Run a timer-scheduled batch for the currently scheduled data version."""
        self._process_batch(self._scheduled_populate_version)

    def _process_batch(self, expected_version: Optional[int] = None) -> None:
        """Process one batch of items.

        FIX: Checks ``isVisible()`` before processing to prevent calls after
        ``deleteLater()``.
        """
        if expected_version is not None and expected_version != self._populate_version:
            # Ignore outdated callback after a newer set_data() call.
            return

        # CRITICAL: Ensure the widget is still alive and visible
        if not self.isVisible() or not self._pending_items:
            self._finish_populate()
            return

        batch = self._pending_items[: self._batch_size]
        self._pending_items = self._pending_items[self._batch_size :]

        for i, link in enumerate(batch):
            try:
                if self._create_button_func is None:
                    break
                button = self._create_button_func(link)  # type: ignore[misc]
                if button is not None:
                    self.panel_layout.addWidget(button)
                    self._content_added = True
                else:
                    logger.debug(
                        "create_button_func returned None for element %d: %s",
                        i,
                        link.get("name", "Unknown"),
                    )
            except Exception:
                if self._update_context is not None:
                    self._update_context.error_count += 1
                logger.exception("Failed to create button for %s", link.get("name"))
                continue

        # Schedule next batch
        if self._pending_items and self._populate_timer:
            if self._update_context is not None:
                self._update_context.batch_count += 1
            self._scheduled_populate_version = self._populate_version
            self._populate_timer.start(DEFAULT_PANEL_BATCH_INTERVAL_MS)
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

        # Release placeholder width once content is available
        has_content = self._content_added or self._has_content_widgets()
        self._ensure_placeholder_width(not has_content)
        self._content_expected = False
        self._content_added = False
        self._update_status = UpdateStatus.COMPLETED

    def _has_content_widgets(self) -> bool:
        """Check whether the panel currently holds visible widgets."""
        for i in range(self.panel_layout.count()):
            item = self.panel_layout.itemAt(i)
            if item is None:
                continue
            if item.widget() is not None:
                return True
        return False

    def _ensure_placeholder_width(self, enforce: bool) -> None:
        """Enforce or release placeholder minimum width."""
        width = getattr(self, "_placeholder_min_width", 0)
        if not width:
            return
        if enforce and self._placeholder_enforced:
            return
        if not enforce and not self._placeholder_enforced:
            return
        try:
            self.setMinimumWidth(width if enforce else 0)
            self._placeholder_enforced = enforce
            self.updateGeometry()
        except Exception:
            logger.debug(
                "BaseTopPanelWidget: failed to adjust placeholder width",
                exc_info=True,
            )

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
        if self._adjust_timer and self._adjust_timer.isActive():
            self._adjust_timer.stop()
        super().closeEvent(event)
