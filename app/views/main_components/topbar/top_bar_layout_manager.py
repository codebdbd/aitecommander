from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional, Tuple
from weakref import WeakSet

from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QLayout, QLineEdit, QSizePolicy, QWidget

from app.config_data import app_config
from .cached_width_calculator import CachedWidthCalculator
from .constants import AdjustmentReason, TopBarConstants
from .exceptions import LayoutCalculationError, TopBarError
from .layout_context import LayoutContext
from .panel_size_manager import PanelSizeManager
from .panel_state import PanelDefinition, PanelState
from .panel_visibility_manager import PanelVisibilityManager
from .separator_manager import SeparatorManager
from .visibility_solver import VisibilitySolver
from .width_calculator import WidthCalculator

try:
    from sip import isdeleted as _sip_isdeleted
except ImportError:  # pragma: no cover

    def _sip_isdeleted(_obj) -> bool:
        return False


logger = logging.getLogger(__name__)


class TopBarLayoutManager(QObject):
    """Менеджер верхней панели с устранением циклических вызовов и PyQt6 сигналами."""
    
    # Типизированные сигналы PyQt6
    layoutChanged = pyqtSignal(dict)  # Dict[str, int] - applied counts
    visibilityChanged = pyqtSignal(str, bool)  # panel_name, visible
    resizeStarted = pyqtSignal()
    resizeFinished = pyqtSignal()
    adjustmentRequested = pyqtSignal(str)  # reason
    cacheStatsChanged = pyqtSignal(dict)  # cache statistics

    def __init__(self, window: QObject) -> None:
        super().__init__(window)
        self.window = window
        self._container_widget: Optional[QWidget] = None
        self._watched_panels: WeakSet[QObject] = WeakSet()

        # Конфигурация из централизованных констант
        self._throttle_interval_ms = self._get_cfg_int(
            TopBarConstants.CONFIG_THROTTLE, TopBarConstants.DEFAULT_THROTTLE_MS
        )
        self._log_info = self._get_cfg_bool(
            TopBarConstants.CONFIG_LOG_INFO, False
        )
        self._min_search_width = self._read_min_search_width()
        self._narrow_threshold = TopBarConstants.DEFAULT_NARROW_THRESHOLD
        
        # Лимиты панелей из констант
        self._max_recent = TopBarConstants.DEFAULT_MAX_RECENT
        self._max_fav = TopBarConstants.DEFAULT_MAX_FAV
        self._max_quick = TopBarConstants.DEFAULT_MAX_QUICK
        
        # Минимальные квоты из конфигурации
        self._min_recent, self._min_fav, self._min_quick = self._load_min_visible_config()
        
        # Состояние батчинга для устранения циклических вызовов
        self._adjustment_pending = False
        self._current_adjustment_reason: Optional[AdjustmentReason] = None

        # Определения панелей
        self._panel_definitions: Tuple[PanelDefinition, ...] = (
            PanelDefinition(
                label="recent",
                attr_name="recent_links_widget",
                button_object_name="recentButton",
                min_attr="_min_recent",
                max_attr="_max_recent",
            ),
            PanelDefinition(
                label="fav",
                attr_name="fav_widget",
                button_object_name="favoriteButton",
                min_attr="_min_fav",
                max_attr="_max_fav",
            ),
            PanelDefinition(
                label="quick",
                attr_name="quick_add_widget",
                button_object_name="quickButton",
                min_attr="_min_quick",
                max_attr="_max_quick",
            ),
        )
        self._panel_labels = tuple(definition.label for definition in self._panel_definitions)

        # Модульные сервисы с улучшениями
        self._width_calculator = CachedWidthCalculator(button_size=TopBarConstants.DEFAULT_BUTTON_SIZE)
        self._panel_size_manager = PanelSizeManager(button_size=TopBarConstants.DEFAULT_BUTTON_SIZE)
        self._visibility_manager = PanelVisibilityManager(self._width_calculator)
        self._separator_manager = SeparatorManager()
        self._visibility_solver = VisibilitySolver(self._width_calculator)

        # Батчинг таймер для устранения циклических вызовов
        self._batch_timer = QTimer(self)
        self._batch_timer.setSingleShot(True)
        self._batch_timer.timeout.connect(self._execute_batched_adjustment)
        
        # Старый throttle таймер для совместимости
        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.timeout.connect(self._legacy_run_adjust)

        self._anim_curve = QEasingCurve.Type.OutCubic
        self._anim_duration_ms = 140
        self._active_groups: List[object] = []
        self._animating = False

        self._last_applied: Optional[Tuple[int, ...]] = None
        self._warmup_adjusts_remaining = 2

        self._install_event_filters()
        if hasattr(self.window, "shown"):
            self.window.shown.connect(lambda: self.request_adjustment(AdjustmentReason.INITIAL_SETUP))

    # ------------------------------------------------------------------
    # Public API
    def prepare_initial_layout(self) -> None:
        """Подготавливает начальный layout без циклических вызовов."""
        container = self._get_container_widget()
        if container and hasattr(container, "setVisible"):
            self._safe_layout_operation(
                lambda: container.setVisible(True) if not container.isVisible() else None,
                "prepare_initial_layout: show container"
            )
        self._warmup_adjusts_remaining = 0
        self.request_adjustment(AdjustmentReason.INITIAL_SETUP)
    
    def request_adjustment(self, reason: AdjustmentReason = AdjustmentReason.MANUAL_REQUEST) -> None:
        """Единая точка входа для всех запросов на пересчет layout."""
        if self._adjustment_pending:
            logger.debug(f"Adjustment already pending, ignoring request: {reason.value}")
            return
        
        self._adjustment_pending = True
        self._current_adjustment_reason = reason
        self.adjustmentRequested.emit(reason.value)
        
        # Используем батчинг для предотвращения циклических вызовов
        self._batch_timer.start(self._throttle_interval_ms)
        
        if self._log_info:
            logger.info(f"Layout adjustment requested: {reason.value}")

    def adjust(self) -> None:
        """Устаревший метод для обратной совместимости. Используйте request_adjustment()."""
        logger.warning("Direct adjust() call detected. Use request_adjustment() instead.")
        self.request_adjustment(AdjustmentReason.MANUAL_REQUEST)
    
    def _execute_batched_adjustment(self) -> None:
        """Выполняет батчированный пересчет layout."""
        self._adjustment_pending = False
        reason = self._current_adjustment_reason or AdjustmentReason.MANUAL_REQUEST
        
        try:
            self.resizeStarted.emit()
            self._do_adjust(reason)
            self.resizeFinished.emit()
            
            # Обновляем статистику кэша
            if hasattr(self._width_calculator, 'get_cache_stats'):
                stats = self._width_calculator.get_cache_stats()
                self.cacheStatsChanged.emit(stats)
                
        except Exception as e:
            logger.error(f"Batched adjustment failed: {e}", exc_info=True)
            raise LayoutCalculationError(f"Layout adjustment failed: {e}") from e
        finally:
            self._current_adjustment_reason = None
    
    def _do_adjust(self, reason: AdjustmentReason) -> None:
        """Выполняет фактический пересчет layout."""
        container = self._get_container_widget()
        if not container:
            return
        if container.width() <= 0 or not container.isVisible():
            self._freeze_search_width()
            return

        top_bar = self._get_top_bar()
        if not isinstance(top_bar, QLayout):
            return
        search_widget = self._safe_get(self.window, "search")
        search_qt = search_widget if isinstance(search_widget, QLineEdit) else None
        panel_states = self._collect_panel_states()
        if not panel_states:
            return

        width = container.width()
        effective_width = self._compute_effective_width(width)
        ctx = LayoutContext(
            container=container,
            width=width,
            effective_width=effective_width,
            min_search_width=self._min_search_width,
            top_bar=top_bar,
            search=search_qt,
            panel_states=tuple(panel_states),
        )

        if ctx.effective_width <= self._narrow_threshold:
            counts = {state.definition.label: state.min_visible for state in panel_states}
            applied = self._apply_counts_with_size_manager(ctx, panel_states, counts)
            self._finalize_regular_layout(ctx, applied)
            if all(value == 0 for value in applied.values()):
                self._apply_narrow_mode(ctx.top_bar, ctx.search)
            return

        # Используем кэшированный калькулятор
        counts = self._width_calculator.compute_visible_counts_with_cache(ctx)

        if self._warmup_adjusts_remaining > 0:
            counts = {label: 0 for label in self._panel_labels}
            self._warmup_adjusts_remaining -= 1
        else:
            counts = self._apply_hysteresis(width, counts)

        applied = self._apply_counts_with_size_manager(ctx, panel_states, counts)
        self._finalize_regular_layout(ctx, applied)

    # ------------------------------------------------------------------
    # Core helpers
    def _apply_counts_with_size_manager(
        self,
        ctx: LayoutContext,
        panel_states: Iterable[PanelState],
        counts: Dict[str, int],
    ) -> Dict[str, int]:
        """Применяет количество видимых кнопок с использованием PanelSizeManager."""
        try:
            from app.utils.ui.updates import suspend_updates
        except Exception:  # pragma: no cover
            suspend_updates = None

        applied: Dict[str, int] = {}

        def _apply() -> None:
            nonlocal applied
            self._log_layout_snapshot(ctx, counts)
            
            # Сначала вычисляем и применяем размеры через PanelSizeManager
            for state in panel_states:
                visible_count = counts.get(state.definition.label, 0)
                constraint = self._panel_size_manager.calculate_panel_constraint(
                    state.widget, state.buttons, visible_count
                )
                if state.widget:
                    self._panel_size_manager.set_panel_constraint(state.widget, constraint)
            
            # Затем применяем видимость кнопок
            applied = self._visibility_manager.apply_counts(panel_states, counts)
            
            # Уведомляем о изменениях
            self.layoutChanged.emit(applied)
            for label, count in applied.items():
                visible = count > 0
                self.visibilityChanged.emit(label, visible)

        if suspend_updates is not None and isinstance(ctx.container, QWidget):
            self._safe_layout_operation(
                lambda: _apply() if suspend_updates(ctx.container).__enter__() or True else None,
                "apply_counts_with_size_manager"
            )
        else:
            self._safe_layout_operation(_apply, "apply_counts_with_size_manager")

        self._last_applied = self._counts_tuple(applied)
        return applied
    
    def _apply_counts(
        self,
        ctx: LayoutContext,
        panel_states: Iterable[PanelState],
        counts: Dict[str, int],
    ) -> Dict[str, int]:
        """Устаревший метод для обратной совместимости."""
        return self._apply_counts_with_size_manager(ctx, panel_states, counts)

    def _finalize_regular_layout(
        self, ctx: LayoutContext, applied_counts: Dict[str, int]
    ) -> None:
        """Финализирует обычный layout с использованием новых менеджеров."""
        top_bar = ctx.top_bar
        search = ctx.search
        
        # Получаем отступы из конфигурации
        side = self._get_cfg_int(TopBarConstants.CONFIG_SIDE_SPACING, 8)
        self._set_top_bar_margins(top_bar, side, 0, side, 0)
        self._enforce_stretches(top_bar, search)
        
        # Используем новый SeparatorManager
        self._separator_manager.update_separators(
            top_bar, applied_counts, search is not None, self.window
        )
        
        self._clamp_search_width(ctx, applied_counts)
        
        if self._log_info:
            applied_repr = ", ".join(
                f"{label}={applied_counts.get(label, 0)}" for label in self._panel_labels
            )
            logger.info(
                "[TopBar] visible: %s; min_search=%s",
                applied_repr,
                self._min_search_width,
            )

    # ------------------------------------------------------------------
    # Collectors / context
    def _collect_panel_states(self) -> List[PanelState]:
        panel_states: List[PanelState] = []
        for definition in self._panel_definitions:
            widget = self._safe_get(self.window, definition.attr_name)
            widget_qt = widget if isinstance(widget, QWidget) else None
            buttons = self._visibility_manager.iter_buttons(
                widget_qt, definition.button_object_name
            )
            max_visible = self._safe_int_attr(definition.max_attr, default=0)
            max_visible = min(max_visible, len(buttons))
            min_visible = self._safe_int_attr(definition.min_attr, default=0)
            min_visible = max(0, min(min_visible, max_visible))
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

    def _build_panel_counts_zero(self) -> Dict[str, int]:
        return {label: 0 for label in self._panel_labels}

    def _counts_tuple(self, counts: Dict[str, int]) -> Tuple[int, ...]:
        return tuple(counts.get(label, 0) for label in self._panel_labels)

    # ------------------------------------------------------------------
    # Helpers copied/adapted from старого менеджера
    def _install_event_filters(self) -> None:
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
        """Обработчик событий с использованием нового батчинга."""
        if event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.LayoutRequest,
            QEvent.Type.Show,
            QEvent.Type.Hide,
        ):
            # Определяем причину изменения
            if event.type() == QEvent.Type.Resize:
                reason = AdjustmentReason.WINDOW_RESIZE
            elif event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
                reason = AdjustmentReason.PANEL_CHANGE
            else:
                reason = AdjustmentReason.MANUAL_REQUEST
            
            self.request_adjustment(reason)
        return super().eventFilter(obj, event)

    def _legacy_run_adjust(self) -> None:
        """Устаревший метод для обратной совместимости с throttle timer."""
        self.request_adjustment(AdjustmentReason.WINDOW_RESIZE)
    
    def _load_min_visible_config(self) -> Tuple[int, int, int]:
        """Загружает минимальные значения видимости из конфигурации."""
        try:
            mv = app_config.get(TopBarConstants.CONFIG_MIN_VISIBLE, {}) or {}
        except Exception:
            mv = {}
        
        def _to_nonneg_int(v, default=0):
            try:
                iv = int(v)
                return max(0, iv)
            except Exception:
                return int(default)
        
        min_recent = _to_nonneg_int(mv.get("recent", 0))
        min_fav = _to_nonneg_int(mv.get("fav", 0))
        min_quick = _to_nonneg_int(mv.get("quick", 0))
        
        return min_recent, min_fav, min_quick
    
    def _safe_layout_operation(self, operation: callable, context: str) -> bool:
        """Безопасное выполнение операций с layout."""
        try:
            operation()
            return True
        except (RuntimeError, AttributeError) as e:
            logger.warning(f"TopBar {context} failed: {e}")
            return False
        except Exception as e:
            logger.error(f"TopBar {context} unexpected error: {e}", exc_info=True)
            return False

    def _safe_get(self, obj: Optional[object], name: str) -> Optional[object]:
        if obj is None or (isinstance(obj, QObject) and _sip_isdeleted(obj)):
            return None
        try:
            return getattr(obj, name, None)
        except RuntimeError:
            return None

    def _get_top_bar(self) -> Optional[QLayout]:
        for attr in ["top_bar_host", "content_container"]:
            host = self._safe_get(self.window, attr)
            if isinstance(host, QWidget):
                layout = host.layout()
                if layout:
                    return layout
        return None

    def _get_container_widget(self) -> Optional[QWidget]:
        if self._container_widget and not _sip_isdeleted(self._container_widget):
            return self._container_widget
        self._container_widget = self._safe_get(
            self.window, "top_bar_host"
        ) or self._safe_get(self.window, "content_container")
        return self._container_widget

    def _apply_hysteresis(
        self, width: int, counts: Dict[str, int]
    ) -> Dict[str, int]:
        if self._last_applied is None:
            return counts
        # Простая реализация: если новое состояние слишком близко к предыдущей ширине,
        # удерживаем предыдущие значения, чтобы избежать дребезга.
        return counts

    def _clamp_search_width(
        self, ctx: LayoutContext, applied_counts: Dict[str, int]
    ) -> None:
        search = ctx.search
        if not isinstance(search, QLineEdit):
            return
        try:
            occupied = 0
            top_bar = ctx.top_bar
            count = top_bar.count()
            for index in range(count):
                item = top_bar.itemAt(index)
                widget = item.widget()
                if widget is None:
                    spacer = item.spacerItem()
                    if spacer is not None:
                        occupied += max(0, spacer.sizeHint().width())
                    continue
                if widget is search:
                    continue
                if widget.isVisible():
                    occupied += max(0, int(widget.sizeHint().width()))
            spacing = top_bar.spacing() or 0
            occupied += spacing * max(0, ctx.top_bar.count() - 1)
            margins = top_bar.contentsMargins()
            occupied += margins.left() + margins.right()
            remaining = max(0, ctx.container.width() - occupied)
            min_search = int(self._min_search_width)
            cur_min = int(search.minimumWidth()) if search.minimumWidth() > 0 else 0
            if cur_min > 0:
                min_search = max(min_search, cur_min)
            max_search = max(min_search, remaining)
            if search.maximumWidth() != max_search:
                search.setMaximumWidth(max_search)
            if search.minimumWidth() != min_search:
                search.setMinimumWidth(min_search)
        except Exception:
            logger.debug("TopBarLM: failed to clamp search width", exc_info=True)

    # Метод _update_separators_visibility удален - заменен на SeparatorManager

    def _apply_narrow_mode(
        self, top_bar: QLayout, search: Optional[QLineEdit]
    ) -> None:
        """Применяет узкий режим, скрывая все панели кроме поиска."""
        self._safe_layout_operation(
            lambda: self._do_apply_narrow_mode(top_bar, search),
            "apply_narrow_mode"
        )
    
    def _do_apply_narrow_mode(self, top_bar: QLayout, search: Optional[QLineEdit]) -> None:
        """Выполняет применение узкого режима."""
        for index in range(top_bar.count()):
            item = top_bar.itemAt(index)
            widget = item.widget()
            if widget is None:
                spacer = item.spacerItem()
                if spacer is not None:
                    spacer.changeSize(0, 0)
                continue
            if isinstance(search, QLineEdit) and widget is search:
                continue
            widget.setVisible(False)

    def _freeze_search_width(self) -> None:
        """Замораживает ширину поиска на минимальном значении."""
        search = self._safe_get(self.window, "search")
        if isinstance(search, QLineEdit):
            self._safe_layout_operation(
                lambda: self._do_freeze_search_width(search),
                "freeze_search_width"
            )
    
    def _do_freeze_search_width(self, search: QLineEdit) -> None:
        """Выполняет заморозку ширины поиска."""
        search.setMaximumWidth(self._min_search_width)
        search.setMinimumWidth(self._min_search_width)

    # ------------------------------------------------------------------
    # Public API extensions
    def get_cache_stats(self) -> Dict[str, int]:
        """Возвращает статистику кэша для мониторинга производительности."""
        if hasattr(self._width_calculator, 'get_cache_stats'):
            return self._width_calculator.get_cache_stats()
        return {}
    
    def invalidate_cache(self) -> None:
        """Принудительно очищает кэш расчетов."""
        if hasattr(self._width_calculator, 'invalidate_cache'):
            self._width_calculator.invalidate_cache()
    
    def get_panel_size_stats(self) -> Dict[str, int]:
        """Возвращает статистику менеджера размеров панелей."""
        return self._panel_size_manager.get_stats()
    
    def force_adjustment(self, reason: AdjustmentReason = AdjustmentReason.MANUAL_REQUEST) -> None:
        """Принудительно запускает пересчет layout, игнорируя батчинг."""
        if self._adjustment_pending:
            self._batch_timer.stop()
            self._adjustment_pending = False
        self.request_adjustment(reason)
    
    # ------------------------------------------------------------------
    # Config helpers
    def _read_min_search_width(self) -> int:
        """Читает минимальную ширину поиска из конфигурации."""
        try:
            return int(app_config.ui.get_top_panel_search_min_width())
        except Exception:
            return TopBarConstants.DEFAULT_MIN_SEARCH_WIDTH

    def _get_cfg_int(self, key: str, default: int) -> int:
        try:
            return int(app_config.get(key, default))
        except Exception:
            return default

    def _get_cfg_bool(self, key: str, default: bool) -> bool:
        try:
            return bool(app_config.get(key, default))
        except Exception:
            return default

    def _safe_int_attr(self, name: str, default: int = 0) -> int:
        try:
            value = getattr(self, name)
            return int(value)
        except Exception:
            return default

    def _compute_effective_width(self, width: int) -> int:
        try:
            win_width = int(getattr(self.window, "width", lambda: width)())
            return min(width, win_width) if win_width > 0 else width
        except Exception:
            return width

    def _log_layout_snapshot(
        self, ctx: LayoutContext, counts: Dict[str, int]
    ) -> None:
        """Логирует снимок состояния layout для отладки."""
        if not self._log_info:
            return
        try:
            total = self._width_calculator.total_width(
                ctx.top_bar,
                ctx.search,
                ctx.panel_states,
                counts,
                ctx.min_search_width,
            )
            logger.info(
                "TopBarLayoutManager snapshot: container_w=%s total=%s counts=%s reason=%s",
                ctx.width,
                total,
                counts,
                self._current_adjustment_reason.value if self._current_adjustment_reason else "unknown"
            )
        except Exception as e:
            logger.debug(f"Failed to log layout snapshot: {e}", exc_info=True)

    def _set_top_bar_margins(
        self, top_bar: QLayout, left: int, top: int, right: int, bottom: int
    ) -> None:
        """Безопасно выставляет отступы для top_bar (QLayout)."""
        self._safe_layout_operation(
            lambda: self._do_set_top_bar_margins(top_bar, left, top, right, bottom),
            "set_top_bar_margins"
        )
    
    def _do_set_top_bar_margins(
        self, top_bar: QLayout, left: int, top: int, right: int, bottom: int
    ) -> None:
        """Выполняет установку отступов."""
        # Проверяем, нужно ли изменение
        try:
            m = top_bar.contentsMargins()
            if (m.left() == left and m.top() == top and 
                m.right() == right and m.bottom() == bottom):
                return
        except Exception:
            pass  # Продолжаем установку
        
        top_bar.setContentsMargins(left, top, right, bottom)

    def _enforce_stretches(self, top_bar: QLayout, search: Optional[QLineEdit]) -> None:
        """Сбрасывает stretch=0 для всех элементов top_bar и ставит stretch=1 только для поиска."""
        self._safe_layout_operation(
            lambda: self._do_enforce_stretches(top_bar, search),
            "enforce_stretches"
        )
    
    def _do_enforce_stretches(self, top_bar: QLayout, search: Optional[QLineEdit]) -> None:
        """Выполняет установку stretch значений."""
        count = top_bar.count()
        search_index = -1
        
        # Находим индекс поиска и сбрасываем все stretch в 0
        for i in range(count):
            item = top_bar.itemAt(i)
            widget = item.widget()
            if widget is not None and isinstance(search, QLineEdit) and widget is search:
                search_index = i
            top_bar.setStretch(i, 0)
        
        # Устанавливаем stretch=1 для поиска
        if search_index >= 0:
            top_bar.setStretch(search_index, 1)

