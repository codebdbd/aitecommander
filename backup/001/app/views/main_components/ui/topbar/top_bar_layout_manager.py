"""Менеджер верхней панели с адаптивным layout.

УЛУЧШЕНИЕ: Использует ResourceManager для гарантированной очистки ресурсов,
константы вместо магических чисел и строгую типизацию через Protocol.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from enum import Enum, auto
from typing import Any, Dict, Iterable, List, Optional, Tuple, TYPE_CHECKING
from weakref import WeakSet

from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QLayout, QLineEdit, QSizePolicy, QWidget

from ...common.constants import Timeout, Size, PerformanceLimit
from ...common.decorators import require_main_thread
from ...common.resource_manager import ResourceManager
from .config_protocol import TopBarConfigProtocol, AppConfigAdapter
from .layout_context import LayoutContext
from .panel_state import PanelDefinition, PanelState
from .panel_visibility_manager import PanelVisibilityManager
from .visibility_solver import VisibilitySolver
from .width_calculator import WidthCalculator
from .types import PanelLabel, ButtonObjectName, TopBarWindow

if TYPE_CHECKING:
    from PyQt6.QtCore import QParallelAnimationGroup

try:
    from sip import isdeleted as _sip_isdeleted
except ImportError:  

    def _sip_isdeleted(_obj) -> bool:
        return False

logger = logging.getLogger(__name__)


class InitializationState(Enum):
    """Состояния инициализации TopBarLayoutManager.
    
    ИСПРАВЛЕНИЕ: Добавлен enum для явного управления состояниями инициализации,
    заменяет разрозненные флаги _data_ready, _warmup_adjusts_remaining.
    """
    NOT_STARTED = auto()      # Менеджер создан, но не инициализирован
    WAITING_FOR_DATA = auto() # Ожидание загрузки данных в панели
    DATA_READY = auto()       # Данные загружены, можно выполнять adjust
    LAYOUT_APPLIED = auto()   # Первый успешный adjust выполнен


class TopBarLayoutManager(QObject):
    """Менеджер верхней панели, использующий модульные сервисы.
    
    Signals:
        layoutAdjusted: Испускается после успешного пересчета layout с информацией о видимых кнопках
        narrowModeChanged: Испускается при переходе в/из узкого режима
        searchWidthChanged: Испускается при изменении ширины поиска
    """
    
    # ИСПРАВЛЕНИЕ: Добавлены сигналы для уведомления о изменениях состояния
    layoutAdjusted = pyqtSignal(dict)  # {label: visible_count}
    narrowModeChanged = pyqtSignal(bool)  # True = narrow mode active
    searchWidthChanged = pyqtSignal(int)  # new min width

    # УЛУЧШЕНИЕ: Используем константы из constants.py
    DEFAULT_THROTTLE_MS = Timeout.THROTTLE_RESIZE
    DEFAULT_LOG_INFO = False
    DEFAULT_MIN_SEARCH_WIDTH = 148  # fallback, читается из config в __init__
    DEFAULT_MAX_RECENT = 10
    DEFAULT_MAX_FAV = 10
    DEFAULT_MAX_QUICK = 6
    DEFAULT_MIN_RECENT = 0
    DEFAULT_MIN_FAV = 0
    DEFAULT_MIN_QUICK = 0
    DEFAULT_NARROW_THRESHOLD = Size.NARROW_MODE_THRESHOLD
    
    # УЛУЧШЕНИЕ: Используем константы из constants.py
    MIN_PANEL_WIDTH = Size.MIN_PANEL_WIDTH
    MAX_WIDGET_WIDTH = Size.MAX_WIDGET_WIDTH
    MIN_SEARCH_WIDTH_RANGE = (Size.MIN_SEARCH_WIDTH, 500)
    
    MAX_VISIBLE_BUTTONS = Size.MAX_VISIBLE_BUTTONS
    MIN_VISIBLE_BUTTONS = 0
    MAX_SEARCH_WIDTH = Size.MAX_SEARCH_WIDTH
    MIN_SEARCH_WIDTH_ABSOLUTE = Size.MIN_SEARCH_WIDTH
    HYSTERESIS_THRESHOLD_BASE = Size.HYSTERESIS_THRESHOLD
    HYSTERESIS_SPACING_MULTIPLIER = 2
    SEPARATOR_SPACING_VISIBLE = 4
    SEPARATOR_SPACING_HIDDEN = 0
    
    SLOW_ADJUST_THRESHOLD_MS = PerformanceLimit.SLOW_ADJUST_THRESHOLD
    SLOW_CLAMP_THRESHOLD_MS = PerformanceLimit.SLOW_CLAMP_THRESHOLD

    def __init__(
        self, 
        window: TopBarWindow, 
        config: Optional[TopBarConfigProtocol] = None
    ) -> None:
        """Initialize TopBarLayoutManager.
        
        ИСПРАВЛЕНИЕ: Добавлен dependency injection для конфигурации.
        
        Args:
            window: Main window implementing TopBarWindow protocol with required attributes
            config: Configuration provider (если None, используется app_config через адаптер)
        
        Example:
            >>> # Использование с реальной конфигурацией
            >>> from app.config_data import app_config
            >>> manager = TopBarLayoutManager(window, AppConfigAdapter(app_config))
            >>> 
            >>> # Использование с mock конфигурацией для тестов
            >>> mock_config = MockTopBarConfig(button_size=24)
            >>> manager = TopBarLayoutManager(window, mock_config)
        """
        super().__init__(window)  # type: ignore[arg-type]
        self.window = window
        self._container_widget: Optional[QWidget] = None
        self._watched_panels: WeakSet[QObject] = WeakSet()
        
        # УЛУЧШЕНИЕ: Инициализируем ResourceManager для управления ресурсами
        self._resource_manager = ResourceManager("TopBarLayoutManager")

        # ИСПРАВЛЕНИЕ: Dependency injection - используем переданную конфигурацию
        # или создаем адаптер для app_config (обратная совместимость)
        if config is None:
            from app.config_data import app_config
            config = AppConfigAdapter(app_config)
        self._config = config

        self._throttle_interval_ms = self._config.get_throttle_ms()
        self._log_info = self._config.get_log_info()
        self._min_search_width = self._config.get_search_min_width()
        self._narrow_threshold = self.DEFAULT_NARROW_THRESHOLD

        self._max_recent = self.DEFAULT_MAX_RECENT
        self._max_fav = self.DEFAULT_MAX_FAV
        self._max_quick = self.DEFAULT_MAX_QUICK

        # ИСПРАВЛЕНИЕ: Используем DI конфигурацию для min_visible
        self._min_recent = self._validate_config_int(
            self._config.get_min_visible("recent"), 
            self.DEFAULT_MIN_RECENT, 
            self.MIN_VISIBLE_BUTTONS, 
            self.MAX_VISIBLE_BUTTONS,
            "topbar.min_visible.recent"
        )
        self._min_fav = self._validate_config_int(
            self._config.get_min_visible("fav"), 
            self.DEFAULT_MIN_FAV, 
            self.MIN_VISIBLE_BUTTONS, 
            self.MAX_VISIBLE_BUTTONS,
            "topbar.min_visible.fav"
        )
        self._min_quick = self._validate_config_int(
            self._config.get_min_visible("quick"), 
            self.DEFAULT_MIN_QUICK, 
            self.MIN_VISIBLE_BUTTONS, 
            self.MAX_VISIBLE_BUTTONS,
            "topbar.min_visible.quick"
        )

        self._panel_definitions: Tuple[PanelDefinition, ...] = (
            PanelDefinition(
                label=PanelLabel.RECENT.value,
                attr_name="recent_links_widget",
                button_object_name=ButtonObjectName.RECENT.value,
                min_attr="_min_recent",
                max_attr="_max_recent",
            ),
            PanelDefinition(
                label=PanelLabel.FAVORITES.value,
                attr_name="fav_widget",
                button_object_name=ButtonObjectName.FAVORITE.value,
                min_attr="_min_fav",
                max_attr="_max_fav",
            ),
            PanelDefinition(
                label=PanelLabel.QUICK.value,
                attr_name="quick_add_widget",
                button_object_name=ButtonObjectName.QUICK.value,
                min_attr="_min_quick",
                max_attr="_max_quick",
            ),
        )
        self._panel_labels = tuple(definition.label for definition in self._panel_definitions)

        # ИСПРАВЛЕНИЕ: Используем DI конфигурацию для button_size
        btn_size = self._config.get_button_size()
        self._width_calculator = WidthCalculator(button_size=btn_size)
        # ИСПРАВЛЕНИЕ: Передаем window как parent для AccessibilityManager
        parent_widget = window if isinstance(window, QWidget) else None
        self._visibility_manager = PanelVisibilityManager(self._width_calculator, parent_widget)
        self._visibility_solver = VisibilitySolver(self._width_calculator)

        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.timeout.connect(self._run_adjust)
        
        # УЛУЧШЕНИЕ: Автоматическая регистрация (cleanup_func определяется автоматически)
        self._resource_manager.register_resource(self._throttle_timer)

        self._anim_curve = QEasingCurve.Type.OutCubic
        self._anim_duration_ms = 140
        self._active_groups: List[QParallelAnimationGroup] = []
        self._animating = False

        self._last_applied: Optional[Tuple[int, ...]] = None
        
        # ИСПРАВЛЕНИЕ: Используем enum вместо разрозненных флагов
        self._init_state = InitializationState.NOT_STARTED
        
        self._adjust_running = False
        self._narrow_mode_active = False  # Отслеживание состояния узкого режима
        
        # Трекинг подключенных сигналов для корректной очистки
        self._signal_connections: List[Tuple[QObject, str, object]] = []
        
        # УЛУЧШЕНИЕ: Используем константу для таймаута
        self._data_ready_timeout_ms = Timeout.DATA_READY_FALLBACK

        self._install_event_filters()
        if hasattr(self.window, "shown"):
            self._connect_signal(self.window, "shown", self.adjust)

    def _connect_signal(self, obj: QObject, signal_name: str, slot: object) -> None:
        """Безопасное подключение сигнала с трекингом для последующей очистки.
        
        Args:
            obj: Объект, содержащий сигнал
            signal_name: Имя сигнала (атрибут объекта)
            slot: Слот для подключения
        """
        try:
            signal = getattr(obj, signal_name, None)
            if signal is not None:
                signal.connect(slot)
                self._signal_connections.append((obj, signal_name, slot))
                logger.debug(f"TopBarLM: connected signal {signal_name}")
        except (AttributeError, TypeError, RuntimeError) as e:
            logger.debug(f"TopBarLM: failed to connect signal {signal_name}: {e}")
    
    @contextmanager
    def _measure_operation(self, operation: str, threshold_ms: float):
        """Context manager для измерения производительности операций.
        
        ИСПРАВЛЕНИЕ: Добавлен для мониторинга производительности критичных операций.
        
        Args:
            operation: Название операции для логирования
            threshold_ms: Порог в миллисекундах, выше которого логируется предупреждение
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = (time.perf_counter() - start) * 1000
            if duration > threshold_ms:
                logger.warning(
                    f"TopBarLM: slow {operation}: {duration:.1f}ms (threshold: {threshold_ms}ms)"
                )
            elif self._log_info:
                logger.info(f"TopBarLM: {operation}: {duration:.1f}ms")
    
    def mark_data_ready(self) -> None:
        """Вызывается после загрузки данных в панели.
        
        ОПТИМИЗАЦИЯ: Плавно показываем панель через анимацию opacity.
        """
        if self._init_state == InitializationState.DATA_READY:
            logger.debug("TopBarLM: data already marked as ready, ignoring duplicate call")
            return
        
        if self._init_state == InitializationState.LAYOUT_APPLIED:
            logger.debug("TopBarLM: layout already applied, ignoring mark_data_ready")
            return
            
        self._init_state = InitializationState.DATA_READY
        logger.debug("TopBarLM: state transition -> DATA_READY")
        
        # Мгновенно показываем панель
        if hasattr(self, '_opacity_effect') and self._opacity_effect:
            try:
                self._opacity_effect.setOpacity(1.0)
                logger.debug("TopBarLM: container opacity set to 1")
            except Exception as e:
                logger.debug("TopBarLM: failed to set opacity: %s", e)
        
        self.adjust()
    
    def _schedule_data_ready_fallback(self) -> None:
        """Планирует fallback для mark_data_ready на случай, если данные не загрузятся.
        
        ИСПРАВЛЕНИЕ: Добавлен таймаут для предотвращения бесконечного ожидания.
        Если данные не загрузятся в течение _data_ready_timeout_ms, принудительно
        устанавливаем состояние DATA_READY и запускаем adjust.
        """
        def _fallback():
            if self._init_state == InitializationState.WAITING_FOR_DATA:
                logger.warning(
                    "TopBarLM: data_ready timeout (%dms) expired, forcing state transition",
                    self._data_ready_timeout_ms
                )
                self._init_state = InitializationState.DATA_READY
                self.adjust()
        
        QTimer.singleShot(self._data_ready_timeout_ms, _fallback)

    def prepare_initial_layout(self) -> None:
        """Подготавливает начальный layout и переводит в состояние ожидания данных.
        
        ОПТИМИЗАЦИЯ: Используем opacity=0 для скрытия панели до загрузки данных.
        """
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        
        container = self._get_container_widget()
        if container:
            try:
                # Устанавливаем opacity=0 чтобы скрыть панель до загрузки
                effect = QGraphicsOpacityEffect(container)
                effect.setOpacity(0.0)
                container.setGraphicsEffect(effect)
                self._opacity_effect = effect  # Сохраняем для mark_data_ready
                logger.debug("TopBarLM: container opacity set to 0")
            except Exception as e:
                logger.debug("TopBarLM: failed to set opacity effect: %s", e)
        
        # Переходим в состояние ожидания данных
        if self._init_state == InitializationState.NOT_STARTED:
            self._init_state = InitializationState.WAITING_FOR_DATA
            logger.debug("TopBarLM: state transition -> WAITING_FOR_DATA")

    @require_main_thread
    def adjust(self) -> None:
        """Пересчитывает layout верхней панели.
        
        ИСПРАВЛЕНИЕ: Добавлены метрики производительности для мониторинга.
        ИСПРАВЛЕНИЕ: Thread safety гарантируется декоратором @require_main_thread.
        """
        
        if self._throttle_timer.isActive():
            return
        if self._adjust_running:
            return
        
        # ИСПРАВЛЕНИЕ: Защита от race condition через проверку состояния
        # Пропускаем adjust, если еще ожидаем загрузки данных
        if self._init_state == InitializationState.WAITING_FOR_DATA:
            logger.debug("TopBarLM: skipping adjust - waiting for data (state=%s)", self._init_state)
            return

        # ИСПРАВЛЕНИЕ: Измеряем производительность всей операции adjust
        with self._measure_operation("adjust", self.SLOW_ADJUST_THRESHOLD_MS):
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
                # ОПТИМИЗАЦИЯ: QuickAdd всегда остается видимым
                counts = {}
                for state in panel_states:
                    if state.definition.label == "quick":
                        # QuickAdd не скрываем
                        counts[state.definition.label] = len(state.buttons)
                    else:
                        counts[state.definition.label] = state.min_visible
                applied = self._apply_counts(ctx, panel_states, counts)
                self._finalize_regular_layout(ctx, applied)
                # narrow mode только если ВСЕ панели скрыты (не считая QuickAdd)
                is_narrow = all(
                    value == 0 
                    for label, value in applied.items() 
                    if label != "quick"
                )
                if is_narrow:
                    self._apply_narrow_mode(ctx.top_bar, ctx.search)
                # ИСПРАВЛЕНИЕ: Испускаем сигнал об изменении режима
                if is_narrow != self._narrow_mode_active:
                    self._narrow_mode_active = is_narrow
                    self.narrowModeChanged.emit(is_narrow)
                # ИСПРАВЛЕНИЕ: Испускаем сигнал о пересчете layout
                self.layoutAdjusted.emit(applied)
                return

            self._adjust_running = True
            try:
                counts = self._visibility_solver.compute_visible_counts(ctx)
                counts = self._apply_hysteresis(ctx, counts)
                
                # ОПТИМИЗАЦИЯ: Если Favorites меньше 5 кнопок - скрываем полностью
                if "fav" in counts and 0 < counts["fav"] < 5:
                    counts["fav"] = 0
                
                applied = self._apply_counts(ctx, panel_states, counts)
                self._finalize_regular_layout(ctx, applied)
                
                # ИСПРАВЛЕНИЕ: Переходим в состояние LAYOUT_APPLIED после первого успешного adjust
                if self._init_state == InitializationState.DATA_READY:
                    self._init_state = InitializationState.LAYOUT_APPLIED
                    logger.debug("TopBarLM: state transition -> LAYOUT_APPLIED")
                
                # ИСПРАВЛЕНИЕ: Испускаем сигнал о пересчете layout
                self.layoutAdjusted.emit(applied)
                # ИСПРАВЛЕНИЕ: Сбрасываем narrow mode если были видимые панели
                if self._narrow_mode_active and any(v > 0 for v in applied.values()):
                    self._narrow_mode_active = False
                    self.narrowModeChanged.emit(False)
            finally:
                self._adjust_running = False
    
    def cleanup(self) -> None:
        """Очищает ресурсы перед удалением менеджера.
        
        УЛУЧШЕНИЕ: Использует ResourceManager для гарантированной очистки.
        Все ресурсы автоматически очищаются через ResourceManager.
        """
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("TopBarLM: starting cleanup")
        
        # УЛУЧШЕНИЕ: ResourceManager автоматически очистит таймер
        self._resource_manager.cleanup_all()
        
        # Отключаем все подключенные сигналы
        for obj, signal_name, slot in self._signal_connections:
            try:
                if not _sip_isdeleted(obj):
                    signal = getattr(obj, signal_name, None)
                    if signal is not None:
                        signal.disconnect(slot)
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(f"TopBarLM: disconnected signal {signal_name}")
            except (TypeError, RuntimeError, AttributeError) as e:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"TopBarLM: failed to disconnect {signal_name}: {e}")
        self._signal_connections.clear()
        
        # Отключаем event filters
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
        
        # Проверяем ошибки очистки
        errors = self._resource_manager.get_cleanup_errors()
        if errors:
            logger.warning(
                "TopBarLM: cleanup completed with %d errors: %s",
                len(errors),
                errors
            )
        elif logger.isEnabledFor(logging.DEBUG):
            logger.debug("TopBarLM: cleanup completed successfully")
    
    def __del__(self):
        """Деструктор с безопасной очисткой."""
        try:
            self.cleanup()
        except Exception:
            pass  # Игнорируем ошибки в деструкторе

    def _apply_counts(
        self,
        ctx: LayoutContext,
        panel_states: Iterable[PanelState],
        counts: Dict[str, int],
    ) -> Dict[str, int]:
        # ИСПРАВЛЕНИЕ: Конкретные исключения вместо Exception
        try:
            from app.utils.ui.updates import suspend_updates
        except (ImportError, AttributeError) as e:
            logger.debug("suspend_updates not available: %s", e)
            suspend_updates = None

        applied: Dict[str, int] = {}

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
        self, ctx: LayoutContext, applied_counts: Dict[str, int]
    ) -> None:
        top_bar = ctx.top_bar
        search = ctx.search
        # ИСПРАВЛЕНИЕ: Используем DI конфигурацию
        side = self._config.get_side_spacing()
        self._set_top_bar_margins(top_bar, side, 0, side, 0)
        self._enforce_stretches(top_bar, search)
        self._update_separators_visibility(
            top_bar,
            applied_counts,
            search is not None,
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

    def _collect_panel_states(self) -> List[PanelState]:
        panel_states: List[PanelState] = []
        for definition in self._panel_definitions:
            widget = self._safe_get(self.window, definition.attr_name)
            widget_qt = widget if isinstance(widget, QWidget) else None
            buttons = self._visibility_manager.iter_buttons(
                widget_qt, definition.button_object_name
            )
            max_visible = self._safe_int_attr(definition.max_attr, default=0)

            # ИСПРАВЛЕНИЕ: не ограничиваем max_visible количеством кнопок,
            # если кнопки еще не загружены. Ограничение применяется только
            # при реальном применении видимости в PanelVisibilityManager.
            # Это позволяет корректно работать при вызове adjust() до загрузки данных.
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

    def _build_panel_counts_zero(self) -> Dict[str, int]:
        return {label: 0 for label in self._panel_labels}

    def _counts_tuple(self, counts: Dict[str, int]) -> Tuple[int, ...]:
        return tuple(counts.get(label, 0) for label in self._panel_labels)

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
        """Фильтрует события для запуска пересчета layout.
        
        ИСПРАВЛЕНИЕ: Оптимизировано для уменьшения избыточных пересчетов.
        - Убран LayoutRequest (слишком частый)
        - Show/Hide только для watched_panels
        - Resize только для container и window
        """
        # ИСПРАВЛЕНИЕ: Фильтруем только критичные объекты
        container = self._container_widget
        if obj not in (container, self.window) and obj not in self._watched_panels:
            return super().eventFilter(obj, event)
        
        # ИСПРАВЛЕНИЕ: Resize только для container и window
        if event.type() == QEvent.Type.Resize:
            if obj in (container, self.window):
                if not self._throttle_timer.isActive():
                    self._throttle_timer.start(self._throttle_interval_ms)
        # ИСПРАВЛЕНИЕ: Show/Hide только для watched_panels
        elif event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
            if obj in self._watched_panels:
                if not self._throttle_timer.isActive():
                    self._throttle_timer.start(self._throttle_interval_ms)
        
        return super().eventFilter(obj, event)

    def _run_adjust(self) -> None:
        self.adjust()

    def _safe_get(self, obj: Optional[Any], name: str) -> Optional[Any]:
        """Безопасное получение атрибута объекта.
        
        ИСПРАВЛЕНИЕ: Заменен object на Any для лучшей типизации.
        
        Args:
            obj: Объект для получения атрибута (может быть любого типа)
            name: Имя атрибута
            
        Returns:
            Значение атрибута или None если объект None/deleted или атрибут не существует
        """
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
        self, ctx: LayoutContext, counts: Dict[str, int]
    ) -> Dict[str, int]:
        """Снижает дёрганье при сжатии/расширении, удерживая предыдущее состояние,
        если выигрыш/проигрыш по ширине меньше порога.

        Идея: считаем общий бюджет при новых и предыдущих counts и сравниваем с
        шириной контейнера. Если разница по запасу меньше порога, оставляем предыдущее.
        """
        if self._last_applied is None:
            return counts
        try:

            prev_counts = {label: self._last_applied[i] for i, label in enumerate(self._panel_labels)}
            total_new = self._width_calculator.total_width(
                ctx.top_bar, ctx.search, ctx.panel_states, counts, ctx.min_search_width
            )
            total_prev = self._width_calculator.total_width(
                ctx.top_bar, ctx.search, ctx.panel_states, prev_counts, ctx.min_search_width
            )

            slack_new = ctx.width - total_new
            slack_prev = ctx.width - total_prev

            try:
                spacing = int(ctx.top_bar.spacing() or 0)
            except Exception:
                spacing = 6
            threshold = max(self.HYSTERESIS_THRESHOLD_BASE, spacing * self.HYSTERESIS_SPACING_MULTIPLIER)

            if abs(slack_new) < threshold and abs(slack_prev) < threshold:
                return prev_counts
        except Exception:
            pass
        return counts

    def _clamp_search_width(
        self, ctx: LayoutContext, applied_counts: Dict[str, int]
    ) -> None:
        """Ограничивает ширину поиска на основе занятого места.
        
        ИСПРАВЛЕНИЕ: Оптимизирован до O(n) сложности - единственный проход по элементам.
        Запоминает индекс search для установки stretch без повторного прохода.
        Добавлены метрики производительности.
        """
        search = ctx.search
        if not isinstance(search, QLineEdit):
            return
        
        # ИСПРАВЛЕНИЕ: Измеряем производительность clamp_search_width
        with self._measure_operation("clamp_search_width", self.SLOW_CLAMP_THRESHOLD_MS):
            try:
                # ИСПРАВЛЕНИЕ: Предварительный расчет - создаем карту состояний панелей
                state_map: Dict[QWidget, PanelState] = {
                    state.widget: state 
                    for state in ctx.panel_states 
                    if state.widget is not None
                }
                
                occupied = 0
                top_bar = ctx.top_bar
                count = top_bar.count()
                occupy_items = 0
                search_index = -1  # ИСПРАВЛЕНИЕ: Запоминаем индекс search
                
                # ИСПРАВЛЕНИЕ: ЕДИНСТВЕННЫЙ проход по элементам layout
                for index in range(count):
                    item = top_bar.itemAt(index)
                    widget = item.widget()
                    
                    if widget is None:
                        # Обработка spacer
                        spacer = item.spacerItem()
                        if spacer is not None:
                            sp_w = max(0, spacer.sizeHint().width())
                            if sp_w > 0:
                                occupied += sp_w
                                occupy_items += 1
                        continue
                    
                    if widget is search:
                        search_index = index  # ИСПРАВЛЕНИЕ: Сохраняем индекс
                        continue
                    
                    # Проверка: это панель из state_map?
                    state = state_map.get(widget)
                    if state:
                        # Это наша панель - используем точный расчет
                        vis = max(0, applied_counts.get(state.definition.label, 0))
                        if vis > 0:  # Логически видима
                            try:
                                w_panel = int(
                                    self._width_calculator.panel_width(widget, state.buttons, vis)
                                )
                            except Exception:
                                w_panel = 0
                            w_use = max(self.MIN_PANEL_WIDTH, w_panel)
                            if w_use > 0:
                                occupied += w_use
                                occupy_items += 1
                    elif widget.isVisible():
                        # Другой виджет - используем sizeHint
                        try:
                            w_hint = int(widget.sizeHint().width())
                        except Exception:
                            w_hint = 0
                        if w_hint > 0:
                            occupied += w_hint
                            occupy_items += 1
                
                spacing = top_bar.spacing() or 0
                occupied += spacing * max(0, occupy_items - 1)
                margins = top_bar.contentsMargins()
                occupied += margins.left() + margins.right()
                remaining = max(0, ctx.container.width() - occupied)
                min_search = int(self._min_search_width)
                cur_min = int(search.minimumWidth()) if search.minimumWidth() > 0 else 0
                if cur_min > 0:
                    min_search = max(min_search, cur_min)

                # ИСПРАВЛЕНИЕ: Устанавливаем stretch БЕЗ повторного прохода
                if search_index >= 0:
                    try:
                        top_bar.setStretch(search_index, 1)
                    except Exception:
                        pass

                if search.minimumWidth() != min_search:
                    search.setMinimumWidth(min_search)
                    # ИСПРАВЛЕНИЕ: Испускаем сигнал об изменении ширины поиска
                    self.searchWidthChanged.emit(min_search)
                if search.maximumWidth() != self.MAX_WIDGET_WIDTH:
                    search.setMaximumWidth(self.MAX_WIDGET_WIDTH)
                if search.minimumWidth() != min_search:
                    search.setMinimumWidth(min_search)
            except Exception:
                logger.debug("TopBarLM: failed to clamp search width", exc_info=True)

    def _update_separators_visibility(
        self,
        top_bar: QLayout,
        applied_counts: Dict[str, int],
        has_search: bool,
    ) -> None:
        """Обновляет видимость разделителей между панелями.
        
        ИСПРАВЛЕНИЕ: Оптимизирован до O(n) - единственный проход по layout.
        Построение карты виджетов за O(n), затем O(1) lookup для соседей.
        """
        # Строим карту панелей для быстрой проверки логической видимости
        panel_widgets = {}
        for state_label, attr_name in (
            (PanelLabel.RECENT.value, "recent_links_widget"),
            (PanelLabel.FAVORITES.value, "fav_widget"),
            (PanelLabel.QUICK.value, "quick_add_widget"),
        ):
            widget = self._safe_get(self.window, attr_name)
            if widget:
                panel_widgets[id(widget)] = (state_label, widget)
        
        def logical_visible(widget: Optional[QWidget]) -> bool:
            """Проверяет логическую видимость панели (O(1))."""
            if not widget:
                return False
            panel_info = panel_widgets.get(id(widget))
            if panel_info:
                state_label, panel_widget = panel_info
                return applied_counts.get(state_label, 0) > 0 and panel_widget.isVisible()
            return False

        # ИСПРАВЛЕНИЕ: Единственный проход - строим список виджетов с индексами
        count = top_bar.count()
        widgets_map = {}  # index -> widget
        for index in range(count):
            item = top_bar.itemAt(index)
            widget = item.widget()
            if widget is not None:
                widgets_map[index] = widget
        
        # Обрабатываем разделители
        for index in range(count):
            item = top_bar.itemAt(index)
            widget = item.widget()
            if widget is None or widget.objectName() != "vSeparator":
                continue
            
            # O(1) поиск соседей через карту
            left_widget = None
            for left_idx in range(index - 1, -1, -1):
                if left_idx in widgets_map:
                    left_widget = widgets_map[left_idx]
                    break
            
            right_widget = None
            for right_idx in range(index + 1, count):
                if right_idx in widgets_map:
                    right_widget = widgets_map[right_idx]
                    break
            
            show_sep = logical_visible(left_widget) and (
                logical_visible(right_widget)
                or (has_search and isinstance(right_widget, QLineEdit))
            )
            widget.setVisible(show_sep)

            left_sp = top_bar.itemAt(index - 1).spacerItem() if index - 1 >= 0 else None
            right_sp = top_bar.itemAt(index + 1).spacerItem() if index + 1 < count else None

            if show_sep:
                if left_sp:
                    left_sp.changeSize(
                        self.SEPARATOR_SPACING_VISIBLE,
                        0,
                        QSizePolicy.Policy.Fixed,
                        QSizePolicy.Policy.Fixed,
                    )
                if right_sp:
                    right_sp.changeSize(
                        self.SEPARATOR_SPACING_VISIBLE,
                        0,
                        QSizePolicy.Policy.Fixed,
                        QSizePolicy.Policy.Fixed,
                    )
            else:
                is_search_right = isinstance(right_widget, QLineEdit)
                if left_sp:
                    left_sp.changeSize(
                        self.SEPARATOR_SPACING_HIDDEN if is_search_right else self.SEPARATOR_SPACING_VISIBLE,
                        0,
                        QSizePolicy.Policy.Fixed,
                        QSizePolicy.Policy.Fixed,
                    )
                if right_sp:
                    right_sp.changeSize(
                        self.SEPARATOR_SPACING_VISIBLE if is_search_right else self.SEPARATOR_SPACING_HIDDEN,
                        0,
                        QSizePolicy.Policy.Fixed,
                        QSizePolicy.Policy.Fixed,
                    )

    def _apply_narrow_mode(
        self, top_bar: QLayout, search: Optional[QLineEdit]
    ) -> None:

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
            try:
                widget.setVisible(False)
            except Exception:
                pass

    def _freeze_search_width(self) -> None:
        search = self._safe_get(self.window, "search")
        if isinstance(search, QLineEdit):
            try:
                search.setMaximumWidth(self._min_search_width)
                search.setMinimumWidth(self._min_search_width)
            except Exception:
                pass

    def _validate_config_int(
        self, 
        value: Any, 
        default: int, 
        min_val: int, 
        max_val: int,
        config_key: str = ""
    ) -> int:
        """Безопасное чтение и валидация целочисленного значения.
        
        ИСПРАВЛЕНИЕ: Добавлен универсальный метод валидации конфигурации.
        
        Args:
            value: Значение для валидации
            default: Значение по умолчанию
            min_val: Минимально допустимое значение
            max_val: Максимально допустимое значение
            config_key: Ключ конфигурации для логирования
            
        Returns:
            Валидированное целочисленное значение в диапазоне [min_val, max_val]
        """
        try:
            int_value = int(value)
            if not min_val <= int_value <= max_val:
                logger.warning(
                    "Config %s=%s out of range [%s, %s], using default=%s",
                    config_key or "value",
                    int_value,
                    min_val,
                    max_val,
                    default,
                )
                return default
            return int_value
        except (ValueError, TypeError, AttributeError) as e:
            logger.debug("Failed to parse config %s: %s", config_key or "value", e)
            return default
        except Exception as e:
            logger.warning("Unexpected error parsing config %s: %s", config_key or "value", e)
            return default
    
    # ИСПРАВЛЕНИЕ: Методы _read_min_search_width, _get_cfg_int, _get_cfg_bool удалены
    # Теперь используется dependency injection через TopBarConfigProtocol

    def _safe_int_attr(self, name: str, default: int = 0) -> int:
        """Безопасное чтение целочисленного атрибута."""
        try:
            value = getattr(self, name)
            return int(value)
        except (AttributeError, ValueError, TypeError):
            return default
        except Exception as e:
            logger.debug("Unexpected error reading attribute '%s': %s", name, e)
            return default

    def _compute_effective_width(self, width: int) -> int:
        try:
            win_width = int(getattr(self.window, "width", lambda: width)())
            return min(width, win_width) if win_width > 0 else width
        except Exception:
            return width

    def _log_layout_snapshot(self, ctx: LayoutContext, counts: Dict[str, int]) -> None:
        """Логирование snapshot layout для диагностики."""
        # УЛУЧШЕНИЕ: Logging guard для избежания избыточного форматирования
        if logger.isEnabledFor(logging.DEBUG):
            try:
                logger.debug(
                    "TopBarLM: layout snapshot - width=%d effective=%d counts=%s",
                    ctx.width,
                    ctx.effective_width,
                    counts,
                )
            except Exception:
                logger.debug(
                    "TopBarLM: failed to log snapshot",
                    exc_info=True,
                )

    def _set_top_bar_margins(
        self, top_bar: QLayout, left: int, top: int, right: int, bottom: int
    ) -> None:
        """Безопасно выставляет отступы для top_bar (QLayout)."""
        try:
            m = top_bar.contentsMargins()
            if (
                m.left() == left
                and m.top() == top
                and m.right() == right
                and m.bottom() == bottom
            ):
                return
        except Exception:
            logger.debug("TopBarLM: failed to read contentsMargins()", exc_info=True)
            top_bar.setContentsMargins(left, top, right, bottom)
        except Exception:
            logger.debug("TopBarLM: setContentsMargins failed", exc_info=True)

    def _enforce_stretches(self, top_bar: QLayout, search: Optional[QLineEdit]) -> None:
        """Сбрасывает stretch=0 для всех элементов top_bar и ставит stretch=1 только для поиска."""
        try:
            count = top_bar.count()
            search_index = -1
            for i in range(count):
                it = top_bar.itemAt(i)
                w = it.widget()
                if w is not None and isinstance(search, QLineEdit) and w is search:
                    search_index = i
                try:
                    top_bar.setStretch(i, 0)
                except Exception:
                    logger.debug(
                        "TopBarLM: setStretch(0) failed at index %s", i, exc_info=True
                    )
            if search_index >= 0:
                try:
                    top_bar.setStretch(search_index, 1)
                except Exception:
                    logger.debug(
                        "TopBarLM: setStretch(1) for search failed at index %s",
                        search_index,
                        exc_info=True,
                    )
        except Exception:
            logger.debug("TopBarLM: _enforce_stretches failed", exc_info=True)
