"""Сервис оркестрации layout adjustment."""
from __future__ import annotations

import logging
import threading
from collections.abc import Iterable
from contextlib import contextmanager
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

from PyQt6.QtWidgets import QLineEdit, QWidget

from ....common.constants import Timeout
from ..models.layout_context import LayoutContext
from ..models.panel_state import PanelState

if TYPE_CHECKING:
    from ..models.types import TopBarWindow
    from .hysteresis_service import HysteresisService
    from .narrow_mode_service import NarrowModeService
    from .panel_visibility_manager import PanelVisibilityManager
    from .search_manager import SearchWidgetManager
    from .separator_service import SeparatorVisibilityService
    from .visibility_solver import VisibilitySolver
    from .widget_accessor import WidgetAccessor

logger = logging.getLogger(__name__)


class InitializationState(Enum):
    """Состояние инициализации layout."""

    NOT_STARTED = auto()
    WAITING_FOR_DATA = auto()
    DATA_READY = auto()
    LAYOUT_APPLIED = auto()


class LayoutOrchestrator:
    """Координирует процесс layout adjustment."""

    def __init__(
        self,
        window: TopBarWindow,
        widget_accessor: WidgetAccessor,
        visibility_manager: PanelVisibilityManager,
        visibility_solver: VisibilitySolver,
        search_manager: SearchWidgetManager,
        separator_service: SeparatorVisibilityService,
        hysteresis_service: HysteresisService,
        narrow_mode_service: NarrowModeService,
        panel_definitions: tuple,
        panel_labels: tuple[str, ...],
        min_search_width: int,
        narrow_threshold: int,
        log_info: bool,
        slow_adjust_threshold_ms: float,
        side_spacing: int,
        manager_ref: Any = None,
    ) -> None:
        self.window = window
        self._manager_ref = manager_ref
        self._widget_accessor = widget_accessor
        self._visibility_manager = visibility_manager
        self._visibility_solver = visibility_solver
        self._search_manager = search_manager
        self._separator_service = separator_service
        self._hysteresis_service = hysteresis_service
        self._narrow_mode_service = narrow_mode_service
        self._panel_definitions = panel_definitions
        self._panel_labels = panel_labels
        self._min_search_width = min_search_width
        self._narrow_threshold = narrow_threshold
        self._log_info = log_info
        self._slow_adjust_threshold_ms = slow_adjust_threshold_ms
        self._side_spacing = side_spacing

        # State
        self._init_state = InitializationState.NOT_STARTED
        self._adjust_lock = threading.Lock()
        self._adjust_running = False
        self._narrow_mode_active = False
        self._last_applied: tuple[int, ...] | None = None
        self._data_ready_timeout_ms = Timeout.DATA_READY_FALLBACK

    def acquire_adjust_lock(self) -> bool:
        """Попытаться захватить блокировку для adjust."""
        with self._adjust_lock:
            if self._adjust_running:
                return False
            self._adjust_running = True
            return True

    def release_adjust_lock(self) -> None:
        """Освободить блокировку adjust."""
        with self._adjust_lock:
            self._adjust_running = False

    def perform_adjust(self, measure_operation_context) -> tuple[dict[str, int], bool, int | None] | None:
        """Выполнить layout adjustment. Возвращает (applied_counts, is_narrow, new_search_width) или None."""
        if self._init_state == InitializationState.WAITING_FOR_DATA:
            logger.debug(
                "LayoutOrchestrator: skipping adjust - waiting for data (state=%s)",
                self._init_state,
            )
            return None

        with measure_operation_context("adjust", self._slow_adjust_threshold_ms):
            ctx = self._prepare_layout_context()
            if not ctx:
                return None

            if ctx.effective_width <= self._narrow_threshold:
                applied = self._handle_narrow_mode(ctx)
                new_width = self._clamp_search_width(ctx, applied)
                return applied, self._narrow_mode_active, new_width
            else:
                applied = self._handle_normal_mode(ctx)
                new_width = self._clamp_search_width(ctx, applied)
                return applied, self._narrow_mode_active, new_width

    def _prepare_layout_context(self) -> LayoutContext | None:
        """Подготовить контекст для layout adjustment."""
        container = self._widget_accessor.get_container_widget()
        if not container:
            return None
        if container.width() <= 0 or not container.isVisible():
            self._narrow_mode_service.freeze_search_width()
            return None

        top_bar = self._widget_accessor.get_top_bar()
        if top_bar is None:
            return None

        search_widget = self._widget_accessor.safe_get(self.window, "search")
        search_qt = search_widget if isinstance(search_widget, QLineEdit) else None
        panel_states = self.collect_panel_states()
        if not panel_states:
            return None

        width = container.width()
        effective_width = self._compute_effective_width(width)

        return LayoutContext(
            container=container,
            width=width,
            effective_width=effective_width,
            min_search_width=self._min_search_width,
            top_bar=top_bar,
            search=search_qt,
            panel_states=tuple(panel_states),
        )

    def _handle_narrow_mode(self, ctx: LayoutContext) -> dict[str, int]:
        """Обработать narrow mode."""
        counts = {}
        for state in ctx.panel_states:
            if state.definition.label == "quick":
                counts[state.definition.label] = len(state.buttons)
            else:
                counts[state.definition.label] = state.min_visible

        applied = self._apply_counts(ctx, ctx.panel_states, counts)
        self._finalize_regular_layout(ctx, applied)

        is_narrow = all(
            value == 0 for label, value in applied.items() if label != "quick"
        )
        if is_narrow:
            self._narrow_mode_service.apply_narrow_mode(ctx.top_bar, ctx.search)

        if is_narrow != self._narrow_mode_active:
            self._narrow_mode_active = is_narrow

        return applied

    def _handle_normal_mode(self, ctx: LayoutContext) -> dict[str, int]:
        """Обработать normal mode."""
        counts = self._visibility_solver.compute_visible_counts(ctx)
        counts = self._hysteresis_service.apply_hysteresis(
            ctx, counts, self._last_applied, self._panel_labels
        )

        if "fav" in counts and 0 < counts["fav"] < 5:
            counts["fav"] = 0

        applied = self._apply_counts(ctx, ctx.panel_states, counts)
        self._finalize_regular_layout(ctx, applied)

        if self._init_state == InitializationState.DATA_READY:
            self._init_state = InitializationState.LAYOUT_APPLIED
            logger.debug("LayoutOrchestrator: state transition -> LAYOUT_APPLIED")

        if self._narrow_mode_active and any(v > 0 for v in applied.values()):
            self._narrow_mode_active = False

        return applied

    def _apply_counts(
        self,
        ctx: LayoutContext,
        panel_states: Iterable[PanelState],
        counts: dict[str, int],
    ) -> dict[str, int]:
        """Применить counts к панелям."""
        try:
            from app.utils.ui.updates import suspend_updates
        except (ImportError, AttributeError) as e:
            logger.debug("suspend_updates not available: %s", e)
            suspend_updates = None

        applied: dict[str, int] = {}

        def _apply() -> None:
            nonlocal applied
            self._log_layout_snapshot(ctx, counts)
            applied = self._visibility_manager.apply_counts(panel_states, counts)

        if suspend_updates is not None and isinstance(ctx.container, QWidget):
            try:
                with suspend_updates(ctx.container):
                    _apply()
            except Exception:
                _apply()
        else:
            _apply()

        self._last_applied = self._counts_tuple(applied)
        return applied

    def _finalize_regular_layout(
        self, ctx: LayoutContext, applied_counts: dict[str, int]
    ) -> None:
        """Финализировать regular layout."""
        top_bar = ctx.top_bar
        search = ctx.search
        self._narrow_mode_service.set_top_bar_margins(
            top_bar, self._side_spacing, 0, self._side_spacing, 0
        )
        self._search_manager.enforce_stretches(top_bar, search)
        self._update_separators_visibility(
            top_bar,
            applied_counts,
            search is not None,
        )
        self._clamp_search_width(ctx, applied_counts)

        if self._log_info:
            applied_repr = ", ".join(
                f"{label}={applied_counts.get(label, 0)}"
                for label in self._panel_labels
            )
            logger.info(
                "[TopBar] visible: %s; min_search=%s",
                applied_repr,
                self._min_search_width,
            )

    def collect_panel_states(self) -> list[PanelState]:
        """Собрать состояния всех панелей (публичный метод)."""
        panel_states: list[PanelState] = []
        for definition in self._panel_definitions:
            widget = self._widget_accessor.safe_get(self.window, definition.attr_name)
            widget_qt = widget if isinstance(widget, QWidget) else None
            buttons = self._visibility_manager.iter_buttons(
                widget_qt, definition.button_object_name
            )
            max_visible = self._safe_int_attr(definition.max_attr, default=0)
            min_visible = self._safe_int_attr(definition.min_attr, default=0)
            min_visible = max(0, min(min_visible, max_visible))

            if definition.label == "quick":
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

    def _counts_tuple(self, counts: dict[str, int]) -> tuple[int, ...]:
        """Преобразовать counts в tuple."""
        return tuple(counts.get(label, 0) for label in self._panel_labels)

    def _compute_effective_width(self, width: int) -> int:
        """Вычислить эффективную ширину."""
        try:
            win_width = int(getattr(self.window, "width", lambda: width)())
            return min(width, win_width) if win_width > 0 else width
        except Exception:
            return width

    def _log_layout_snapshot(
        self, ctx: LayoutContext, counts: dict[str, int]
    ) -> None:
        """Логировать snapshot layout."""
        if logger.isEnabledFor(logging.DEBUG):
            try:
                logger.debug(
                    "LayoutOrchestrator: layout snapshot - width=%d effective=%d counts=%s",
                    ctx.width,
                    ctx.effective_width,
                    counts,
                )
            except Exception:
                logger.debug(
                    "LayoutOrchestrator: failed to log snapshot",
                    exc_info=True,
                )

    def _clamp_search_width(
        self, ctx: LayoutContext, applied_counts: dict[str, int]
    ) -> int | None:
        """Ограничить ширину search widget."""
        return self._search_manager.clamp_width(
            ctx, applied_counts, self._min_search_width
        )

    def _update_separators_visibility(
        self,
        top_bar,
        applied_counts: dict[str, int],
        has_search: bool,
    ) -> None:
        """Обновить видимость separators."""
        panel_widgets_map = self._separator_service.build_panel_widgets_map(
            self.window, self._panel_labels
        )
        self._separator_service.update_separators(
            top_bar,
            applied_counts,
            has_search,
            panel_widgets_map,
        )

    def _safe_int_attr(self, name: str, default: int = 0) -> int:
        """Безопасно получить int атрибут."""
        try:
            # Получаем атрибут из manager_ref, а не из window
            obj = self._manager_ref if self._manager_ref else self.window
            value = getattr(obj, name)
            return int(value)
        except (AttributeError, ValueError, TypeError):
            return default
        except Exception as e:
            logger.debug("Unexpected error reading attribute '%s': %s", name, e)
            return default

    # State management
    def get_init_state(self) -> InitializationState:
        """Получить текущее состояние инициализации."""
        return self._init_state

    def set_init_state(self, state: InitializationState) -> None:
        """Установить состояние инициализации."""
        self._init_state = state

    def is_narrow_mode_active(self) -> bool:
        """Проверить активен ли narrow mode."""
        return self._narrow_mode_active

    def set_narrow_mode_active(self, active: bool) -> None:
        """Установить флаг narrow mode."""
        self._narrow_mode_active = active

    def get_last_applied(self) -> tuple[int, ...] | None:
        """Получить последние примененные counts."""
        return self._last_applied
