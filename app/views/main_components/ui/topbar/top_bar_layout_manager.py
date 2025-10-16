"""TopBarLayoutManager - фасад для управления layout топ-бара."""
from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from contextlib import contextmanager

from PyQt6.QtCore import QEvent, QObject, pyqtSignal
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QWidget

from ...common.decorators import require_main_thread
from ...common.resource_manager import ResourceManager
from .models.config_protocol import TopBarConfigProtocol
from .models.panel_state import PanelState
from .models.topbar_constants import TOPBAR_CONSTANTS as C
from .models.types import TopBarWindow
from .services.hysteresis_service import HysteresisService
from .services.initialization_service import TopBarInitializationService
from .services.layout_orchestrator import InitializationState, LayoutOrchestrator
from .services.lifecycle_manager import TopBarLifecycleManager
from .services.narrow_mode_service import NarrowModeService
from .services.widget_accessor import WidgetAccessor
from .utils.qt_utils import get_sip_statistics
from .utils.qt_utils import is_deleted as _sip_isdeleted

logger = logging.getLogger(__name__)


class TopBarLayoutManager(QObject):
    """Фасад для управления layout топ-бара. Делегирует работу сервисам."""

    layoutAdjusted = pyqtSignal(dict)
    narrowModeChanged = pyqtSignal(bool)
    searchWidthChanged = pyqtSignal(int)

    # Константы (для обратной совместимости)
    MIN_PANEL_WIDTH = C.MIN_PANEL_WIDTH
    MAX_WIDGET_WIDTH = C.MAX_WIDGET_WIDTH
    MAX_VISIBLE_BUTTONS = C.MAX_VISIBLE_BUTTONS
    MIN_VISIBLE_BUTTONS = C.MIN_VISIBLE_BUTTONS
    MAX_SEARCH_WIDTH = C.MAX_SEARCH_WIDTH
    MIN_SEARCH_WIDTH_ABSOLUTE = C.MIN_SEARCH_WIDTH_ABSOLUTE
    HYSTERESIS_THRESHOLD_BASE = C.HYSTERESIS_THRESHOLD_BASE
    HYSTERESIS_SPACING_MULTIPLIER = C.HYSTERESIS_SPACING_MULTIPLIER
    SEPARATOR_SPACING_VISIBLE = C.SEPARATOR_SPACING_VISIBLE
    SEPARATOR_SPACING_HIDDEN = C.SEPARATOR_SPACING_HIDDEN
    SLOW_ADJUST_THRESHOLD_MS = C.SLOW_ADJUST_THRESHOLD_MS
    SLOW_CLAMP_THRESHOLD_MS = C.SLOW_CLAMP_THRESHOLD_MS

    def __init__(
        self, window: TopBarWindow, config: TopBarConfigProtocol | None = None
    ) -> None:
        super().__init__(window)
        self.window = window
        self._resource_manager = ResourceManager("TopBarLayoutManager")
        self._opacity_effect: QGraphicsOpacityEffect | None = None

        # Инициализация через сервис
        self._init_service = TopBarInitializationService(
            window, config, self._resource_manager
        )
        self._config = self._init_service.get_config()

        # Настройки
        settings = self._init_service.init_settings()
        self._throttle_interval_ms = settings["throttle_interval_ms"]
        self._log_info = settings["log_info"]
        self._min_search_width = settings["min_search_width"]
        self._narrow_threshold = settings["narrow_threshold"]

        # Границы панелей
        bounds = self._init_service.init_panel_bounds()
        self._max_recent = bounds["max_recent"]
        self._max_fav = bounds["max_fav"]
        self._max_quick = bounds["max_quick"]
        self._min_recent = bounds["min_recent"]
        self._min_fav = bounds["min_fav"]
        self._min_quick = bounds["min_quick"]

        # Определения панелей
        self._panel_definitions = self._init_service.create_panel_definitions()
        self._panel_labels = tuple(d.label for d in self._panel_definitions)

        # Сервисы
        services = self._init_service.init_services()
        self._width_calculator = services["width_calculator"]
        self._visibility_manager = services["visibility_manager"]
        self._visibility_solver = services["visibility_solver"]
        self._search_manager = services["search_manager"]
        self._separator_service = services["separator_service"]

        # Дополнительные сервисы
        self._widget_accessor = WidgetAccessor(window)
        self._hysteresis_service = HysteresisService(self._width_calculator)
        self._narrow_mode_service = NarrowModeService(
            window, self._widget_accessor, self._search_manager, self._min_search_width
        )

        # Orchestrator
        self._orchestrator = LayoutOrchestrator(
            window=window,
            widget_accessor=self._widget_accessor,
            visibility_manager=self._visibility_manager,
            visibility_solver=self._visibility_solver,
            search_manager=self._search_manager,
            separator_service=self._separator_service,
            hysteresis_service=self._hysteresis_service,
            narrow_mode_service=self._narrow_mode_service,
            panel_definitions=self._panel_definitions,
            panel_labels=self._panel_labels,
            min_search_width=self._min_search_width,
            narrow_threshold=self._narrow_threshold,
            log_info=self._log_info,
            slow_adjust_threshold_ms=self.SLOW_ADJUST_THRESHOLD_MS,
            side_spacing=self._config.get_side_spacing(),
            manager_ref=self,
        )

        # Lifecycle manager
        self._lifecycle_manager = TopBarLifecycleManager(self)

        # Таймер
        self._throttle_timer = self._init_service.init_timer(self, self._run_adjust)

        # Event handling
        self._init_event_handling()

    def _init_event_handling(self) -> None:
        """Инициализация обработки событий."""
        # Установка event filters через lifecycle manager
        widgets_to_watch = []
        for attr_name in [
            "top_bar_host",
            "content_container",
            "quick_add_widget",
            "fav_widget",
            "recent_links_widget",
        ]:
            widget = self._widget_accessor.safe_get(self.window, attr_name)
            if isinstance(widget, QWidget):
                widgets_to_watch.append(widget)

        if isinstance(self.window, QWidget) and not _sip_isdeleted(self.window):
            widgets_to_watch.append(self.window)

        self._lifecycle_manager.install_event_filters(widgets_to_watch)

        if hasattr(self.window, "shown"):
            self._lifecycle_manager.connect_signal(self.window, "shown", self.adjust)

    @contextmanager
    def _measure_operation(self, operation: str, threshold_ms: float):
        """Измерить длительность операции."""
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = (time.perf_counter() - start) * 1000
            if duration > threshold_ms:
                logger.warning(
                    "TopBarLM: slow %s: %.1fms (threshold: %sms)",
                    operation,
                    duration,
                    threshold_ms,
                )
            elif self._log_info:
                logger.info(f"TopBarLM: {operation}: {duration:.1f}ms")

    @require_main_thread
    def mark_data_ready(self) -> None:
        """Отметить что данные готовы."""
        state = self._orchestrator.get_init_state()
        if state == InitializationState.DATA_READY:
            logger.debug(
                "TopBarLM: data already marked as ready, ignoring duplicate call"
            )
            return

        if state == InitializationState.LAYOUT_APPLIED:
            logger.debug("TopBarLM: layout already applied, ignoring mark_data_ready")
            return

        self._orchestrator.set_init_state(InitializationState.DATA_READY)
        logger.debug("TopBarLM: state transition -> DATA_READY")

        # Reveal the panel
        if self._opacity_effect is not None:
            try:
                self._opacity_effect.setOpacity(1.0)
                logger.debug(
                    "TopBarLM: container opacity set to 1 (state=%s)",
                    self._orchestrator.get_init_state().name
                )
            except (RuntimeError, AttributeError) as e:
                logger.warning(
                    "TopBarLM: failed to set opacity (effect may be deleted): %s",
                    e
                )
            except Exception as e:
                logger.error(
                    "TopBarLM: unexpected error setting opacity: %s",
                    e,
                    exc_info=True
                )

        self.adjust()

    @require_main_thread
    def prepare_initial_layout(self) -> None:
        """Подготовить начальный layout.

        Создаёт QGraphicsOpacityEffect(0.0) для скрытия контейнера до готовности данных.
        Эффект автоматически очищается в cleanup().

        Thread-safety: Должен вызываться из GUI-потока.
        """
        container = self._widget_accessor.get_container_widget()
        if container:
            try:
                # Проверить существующий эффект
                existing_effect = container.graphicsEffect()
                if existing_effect is not None:
                    logger.warning(
                        "TopBarLM: container already has graphics effect: %s, "
                        "replacing",
                        type(existing_effect).__name__
                    )
                    container.setGraphicsEffect(None)
                    existing_effect.deleteLater()

                effect = QGraphicsOpacityEffect(container)
                effect.setOpacity(0.0)
                container.setGraphicsEffect(effect)
                self._opacity_effect = effect
                logger.debug("TopBarLM: container opacity set to 0")
            except (RuntimeError, AttributeError) as e:
                logger.warning(
                    "TopBarLM: failed to set opacity effect "
                    "(expected during shutdown): %s",
                    e
                )
            except Exception as e:
                logger.error(
                    "TopBarLM: unexpected error setting opacity effect: %s",
                    e,
                    exc_info=True
                )

        state = self._orchestrator.get_init_state()
        if state == InitializationState.NOT_STARTED:
            self._orchestrator.set_init_state(InitializationState.WAITING_FOR_DATA)
            logger.debug("TopBarLM: state transition -> WAITING_FOR_DATA")

    @require_main_thread
    def adjust(self) -> None:
        """Выполнить layout adjustment."""
        if self._throttle_timer.isActive():
            return

        if not self._orchestrator.acquire_adjust_lock():
            return

        try:
            result = self._orchestrator.perform_adjust(self._measure_operation)
            if result is None:
                return

            applied_dict, is_narrow, new_search_width = result

            # Emit signals
            self.layoutAdjusted.emit(applied_dict)
            self.narrowModeChanged.emit(is_narrow)

            if new_search_width is not None:
                self.searchWidthChanged.emit(new_search_width)

        finally:
            self._orchestrator.release_adjust_lock()

    def retranslate_topbar(self) -> None:
        """Перевести топ-бар на другой язык."""
        try:
            top_bar = self._widget_accessor.get_top_bar()
            if top_bar is None:
                return
            panel_states = self._orchestrator.collect_panel_states()
            if not panel_states:
                return

            last_applied = self._orchestrator.get_last_applied()
            if last_applied is not None:
                visible_counts = {
                    label: last_applied[i]
                    for i, label in enumerate(self._panel_labels)
                }
            else:
                visible_counts = self._visible_counts_from_state(panel_states)

            self._visibility_manager.retranslate_panels(panel_states, visible_counts)
        except Exception as e:
            logger.debug("TopBarLM: retranslate_topbar failed: %s", e)

    def _visible_counts_from_state(
        self, panel_states: Iterable[PanelState]
    ) -> dict[str, int]:
        """Получить counts из текущего состояния панелей."""
        counts: dict[str, int] = {label: 0 for label in self._panel_labels}
        try:
            for state in panel_states:
                visible = 0
                for b in state.buttons:
                    try:
                        if b.isVisible():
                            visible += 1
                    except Exception:
                        pass
                counts[state.definition.label] = visible
        except Exception:
            pass
        return counts

    def get_sip_statistics(self) -> dict:
        """Получить статистику SIP."""
        return get_sip_statistics()

    @require_main_thread
    def cleanup(self) -> None:
        """Очистить все ресурсы TopBarLayoutManager.

        Выполняет детерминированную очистку в следующем порядке:
        1. Удаление QGraphicsOpacityEffect с контейнера
        2. Очистка ResourceManager (таймеры, сервисы)
        3. Очистка TopBarLifecycleManager (event filters, сигналы)
        4. Очистка кэша WidgetAccessor

        Thread-safety: Должен вызываться из GUI-потока.
        Idempotent: Безопасен для множественных вызовов.

        Raises:
            Не выбрасывает исключения; все ошибки логируются.
        """
        self._log_cleanup_start()

        # Очистка opacity effect
        if self._opacity_effect is not None:
            try:
                container = self._widget_accessor.get_container_widget()
                if container and not _sip_isdeleted(container):
                    container.setGraphicsEffect(None)
                self._opacity_effect.deleteLater()
                self._opacity_effect = None
                logger.debug("TopBarLM: opacity effect cleaned up")
            except (RuntimeError, AttributeError) as e:
                logger.debug(
                    "TopBarLM: opacity effect cleanup failed "
                    "(expected during shutdown): %s",
                    e
                )

        self._resource_manager.cleanup_all()
        self._lifecycle_manager.cleanup()
        self._widget_accessor.clear_cache()
        self._log_cleanup_result()

    def _log_cleanup_start(self):
        """Логировать начало cleanup."""
        if logger.isEnabledFor(logging.DEBUG):
            stats = get_sip_statistics()
            if stats:
                logger.debug(
                    "TopBarLM: cleanup start - alive=%s, deleted=%s, "
                    "success_rate=%.1f%%",
                    stats["alive"],
                    stats["deleted"],
                    stats["success_rate"],
                )

    def _log_cleanup_result(self):
        """Логировать результат cleanup."""
        if logger.isEnabledFor(logging.DEBUG):
            stats = get_sip_statistics()
            if stats:
                logger.debug(
                    "TopBarLM: cleanup done - alive=%s, deleted=%s",
                    stats["alive"],
                    stats["deleted"],
                )

    # REMOVED: __del__ вызов cleanup рискован, т.к. деструктор QObject может сработать
    # поздно или после уничтожения дочерних Qt-объектов. Явный вызов cleanup() через
    # window.destroyed.connect(manager.cleanup) в window_ui_setup.py:513 обеспечивает
    # детерминированную очистку в правильном порядке жизненного цикла Qt.

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Фильтр событий."""
        container = self._widget_accessor.get_container_widget()
        if container is None:
            return super().eventFilter(obj, event)

        watched_panels = self._lifecycle_manager.get_watched_panels()

        if obj not in (container, self.window) and obj not in watched_panels:
            return super().eventFilter(obj, event)

        if event.type() == QEvent.Type.Resize:
            if obj in (container, self.window):
                if not self._throttle_timer.isActive():
                    self._throttle_timer.start(self._throttle_interval_ms)
        elif event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
            if obj in watched_panels:
                if not self._throttle_timer.isActive():
                    self._throttle_timer.start(self._throttle_interval_ms)

        return super().eventFilter(obj, event)

    def _run_adjust(self) -> None:
        """Запустить adjust (callback для таймера)."""
        self.adjust()
