"""TopBar controller - thin UI coordination layer.

This module implements the Controller pattern, separating UI event handling
from business logic. The controller coordinates between services and the view.
"""

from __future__ import annotations

import logging
import threading
from typing import Any
from weakref import WeakSet

from PyQt6.QtCore import QEvent, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QLayout, QLineEdit, QWidget

from ..models.layout_context import LayoutContext
from ..models.panel_state import PanelDefinition, PanelState
from ..models.types import PanelLabel, TopBarWindow
from ..services.config_service import TopBarSettings
from ..services.layout_service import TopBarLayoutService
from ..services.panel_visibility_manager import PanelVisibilityManager
from ..services.search_manager import SearchWidgetManager
from ..services.separator_service import SeparatorVisibilityService
from ..utils.qt_utils import is_deleted as _sip_isdeleted

logger = logging.getLogger(__name__)


class TopBarController(QObject):
    """Thin UI controller for top-bar layout coordination.
    
    Responsibilities:
    - Handle Qt events (resize, show/hide)
    - Coordinate layout computation via services
    - Apply results to widgets
    - Emit signals for UI updates
    
    Does NOT contain:
    - Business logic (delegated to services)
    - Direct widget manipulation (delegated to managers)
    - Configuration parsing (delegated to config service)
    """

    layoutAdjusted = pyqtSignal(dict)
    narrowModeChanged = pyqtSignal(bool)
    searchWidthChanged = pyqtSignal(int)

    def __init__(
        self,
        window: TopBarWindow,
        settings: TopBarSettings,
        *,
        layout_service: TopBarLayoutService,
        visibility_manager: PanelVisibilityManager,
        separator_service: SeparatorVisibilityService,
        search_manager: SearchWidgetManager,
        panel_definitions: tuple[PanelDefinition, ...],
        panel_labels: tuple[str, ...],
    ) -> None:
        """Initialize controller with injected dependencies.
        
        Args:
            window: Main window containing top-bar widgets
            settings: Configuration settings
            layout_service: Service for layout computation
            visibility_manager: Manager for panel visibility
            separator_service: Service for separator visibility
            search_manager: Manager for search widget
            panel_definitions: Panel configuration definitions
            panel_labels: Tuple of panel label strings
        """
        super().__init__(window)
        self.window = window
        self._settings = settings
        
        # Injected services
        self._layout_service = layout_service
        self._visibility_manager = visibility_manager
        self._separator_service = separator_service
        self._search_manager = search_manager
        
        # Panel configuration
        self._panel_definitions = panel_definitions
        self._panel_labels = panel_labels
        
        # State tracking
        self._last_applied: tuple[int, ...] | None = None
        self._narrow_mode_active = False
        self._adjust_lock = threading.Lock()
        self._adjust_running = False
        
        # Event handling
        self._watched_panels: WeakSet[QObject] = WeakSet()
        self._container_widget: QWidget | None = None
        
        # Throttling
        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.timeout.connect(self._run_adjust)
        
        self._install_event_filters()
        if hasattr(self.window, "shown"):
            try:
                self.window.shown.connect(self._schedule_initial_adjust)
            except (AttributeError, TypeError, RuntimeError):
                pass

    def _schedule_initial_adjust(self) -> None:
        """Defer the first top bar adjust to avoid blocking the first post-show loop."""
        try:
            if self._throttle_timer.isActive():
                return
            self._throttle_timer.start(0)
        except Exception:
            self.adjust()

    def adjust(self) -> None:
        """Trigger layout adjustment (throttled)."""
        if self._throttle_timer.isActive():
            return

        if not self._acquire_adjust_lock():
            return

        try:
            self._perform_adjust()
        finally:
            with self._adjust_lock:
                self._adjust_running = False

    def _acquire_adjust_lock(self) -> bool:
        """Acquire lock for adjustment operation."""
        with self._adjust_lock:
            if self._adjust_running:
                return False
            self._adjust_running = True
            return True

    def _perform_adjust(self) -> None:
        """Perform layout adjustment using services."""
        ctx = self._prepare_layout_context()
        if not ctx:
            return

        # Compute layout via service
        result = self._layout_service.compute(
            ctx,
            panel_states=ctx.panel_states,
            panel_labels=self._panel_labels,
            last_applied=self._last_applied,
            narrow_threshold=self._settings.narrow_threshold,
        )

        # Apply results via managers
        applied = self._apply_layout_result(ctx, result.counts)
        
        # Update UI state
        self._sync_narrow_mode(result.is_narrow)
        
        # Emit signal
        self.layoutAdjusted.emit(applied)

    def _prepare_layout_context(self) -> LayoutContext | None:
        """Prepare layout context from current window state."""
        container = self._get_container_widget()
        if not container:
            return None
            
        if container.width() <= 0 or not container.isVisible():
            search = self._safe_get(self.window, "search")
            self._search_manager.freeze_width(search, self._settings.min_search_width)
            return None

        top_bar = self._get_top_bar()
        if not isinstance(top_bar, QLayout):
            return None

        search_widget = self._safe_get(self.window, "search")
        search_qt = search_widget if isinstance(search_widget, QLineEdit) else None
        panel_states = self._collect_panel_states()
        
        if not panel_states:
            return None

        width = container.width()
        effective_width = self._compute_effective_width(width)

        return LayoutContext(
            container=container,
            width=width,
            effective_width=effective_width,
            min_search_width=self._settings.min_search_width,
            top_bar=top_bar,
            search=search_qt,
            panel_states=tuple(panel_states),
        )

    def _apply_layout_result(
        self, ctx: LayoutContext, counts: dict[str, int]
    ) -> dict[str, int]:
        """Apply layout computation results to widgets."""
        # Apply visibility counts
        applied = self._visibility_manager.apply_counts(ctx.panel_states, counts)
        
        # Finalize layout
        self._finalize_layout(ctx, applied)
        
        # Update last applied state
        self._last_applied = tuple(applied.get(label, 0) for label in self._panel_labels)
        
        return applied

    def _finalize_layout(
        self, ctx: LayoutContext, applied_counts: dict[str, int]
    ) -> None:
        """Finalize layout with margins, stretches, separators, and search."""
        top_bar = ctx.top_bar
        search = ctx.search
        
        # Set margins
        side = self._settings.side_spacing
        self._set_top_bar_margins(top_bar, side, 0, side, 0)
        
        # Enforce stretches
        self._search_manager.enforce_stretches(top_bar, search)
        
        # Update separators
        panel_widgets_map = self._separator_service.build_panel_widgets_map(
            self.window, self._panel_labels
        )
        self._separator_service.update_separators(
            top_bar,
            applied_counts,
            search is not None,
            panel_widgets_map,
        )
        
        # Clamp search width
        new_min_width = self._search_manager.clamp_width(
            ctx, applied_counts, self._settings.min_search_width
        )
        if new_min_width is not None:
            self.searchWidthChanged.emit(new_min_width)

    def _sync_narrow_mode(self, is_narrow: bool) -> None:
        """Synchronize narrow mode state and emit signal if changed."""
        if self._narrow_mode_active == is_narrow:
            return
        self._narrow_mode_active = is_narrow
        self.narrowModeChanged.emit(is_narrow)

    def _collect_panel_states(self) -> list[PanelState]:
        """Collect current panel states from window."""
        panel_states: list[PanelState] = []
        for definition in self._panel_definitions:
            widget = self._safe_get(self.window, definition.attr_name)
            widget_qt = widget if isinstance(widget, QWidget) else None
            buttons = self._visibility_manager.iter_buttons(
                widget_qt, definition.button_object_name
            )
            max_visible = max(0, int(definition.max_visible))
            min_visible = max(0, min(int(definition.min_visible), max_visible))

            if definition.label == PanelLabel.QUICK.value:
                fixed = len(buttons)
                max_visible = fixed
                min_visible = fixed
                
            panel_states.append(
                PanelState(
                    definition=definition,
                    widget=widget_qt,
                    buttons=buttons,
                    min_visible=min_visible,
                    max_visible=max_visible,
                )
            )
        return panel_states

    def _install_event_filters(self) -> None:
        """Install event filters on relevant widgets."""
        for attr_name in [
            "top_bar_host",
            "content_container",
            "quick_add_widget",
            "fav_widget",
            "recent_links_widget",
        ]:
            widget = self._safe_get(self.window, attr_name)
            if isinstance(widget, QWidget) and widget not in self._watched_panels:
                widget.installEventFilter(self)
                self._watched_panels.add(widget)
                
        if isinstance(self.window, QWidget) and not _sip_isdeleted(self.window):
            self.window.installEventFilter(self)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Handle resize and visibility events."""
        container = self._container_widget
        if obj not in (container, self.window) and obj not in self._watched_panels:
            return super().eventFilter(obj, event)

        if event.type() == QEvent.Type.Resize:
            if obj in (container, self.window):
                if not self._throttle_timer.isActive():
                    self._throttle_timer.start(self._settings.throttle_interval_ms)
        elif event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
            if obj in self._watched_panels:
                if not self._throttle_timer.isActive():
                    self._throttle_timer.start(self._settings.throttle_interval_ms)

        return super().eventFilter(obj, event)

    def _run_adjust(self) -> None:
        """Callback for throttle timer."""
        self.adjust()

    def _get_container_widget(self) -> QWidget | None:
        """Get top bar container widget."""
        if self._container_widget and not _sip_isdeleted(self._container_widget):
            return self._container_widget
        self._container_widget = self._safe_get(
            self.window, "top_bar_host"
        ) or self._safe_get(self.window, "content_container")
        return self._container_widget

    def _get_top_bar(self) -> QLayout | None:
        """Get top bar layout."""
        for attr in ["top_bar_host", "content_container"]:
            host = self._safe_get(self.window, attr)
            if isinstance(host, QWidget):
                layout = host.layout()
                if layout:
                    return layout
        return None

    def _safe_get(self, obj: Any | None, name: str) -> Any | None:
        """Safely get attribute from object."""
        if obj is None or (isinstance(obj, QObject) and _sip_isdeleted(obj)):
            return None
        try:
            return getattr(obj, name, None)
        except RuntimeError:
            return None

    def _compute_effective_width(self, width: int) -> int:
        """Compute effective width considering window constraints."""
        try:
            win_width = int(getattr(self.window, "width", lambda: width)())
            return min(width, win_width) if win_width > 0 else width
        except Exception:
            return width

    def _set_top_bar_margins(
        self, top_bar: QLayout, left: int, top: int, right: int, bottom: int
    ) -> None:
        """Set top bar layout margins."""
        try:
            m = top_bar.contentsMargins()
            if (
                m.left() == left
                and m.top() == top
                and m.right() == right
                and m.bottom() == bottom
            ):
                return
            top_bar.setContentsMargins(left, top, right, bottom)
        except Exception:
            logger.debug("TopBarController: failed to update margins", exc_info=True)

    def cleanup(self) -> None:
        """Cleanup resources and event filters."""
        for panel in list(self._watched_panels):
            try:
                if not _sip_isdeleted(panel):
                    panel.removeEventFilter(self)
            except (RuntimeError, AttributeError):
                pass

        if isinstance(self.window, QWidget) and not _sip_isdeleted(self.window):
            try:
                self.window.removeEventFilter(self)
            except (RuntimeError, AttributeError):
                pass

        self._watched_panels.clear()
        self._container_widget = None
        
        if self._throttle_timer:
            self._throttle_timer.stop()
