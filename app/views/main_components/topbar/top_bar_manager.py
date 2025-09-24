"""Основной менеджер топбара - координатор компонентов."""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from PyQt6.QtCore import QTimer, QObject
from PyQt6.QtWidgets import QHBoxLayout, QLayout, QLineEdit, QToolButton, QWidget

from app.views.main_components.topbar.top_bar_config import TopBarConfig
from app.views.main_components.topbar.top_bar_calculator import TopBarLayoutCalculator
from app.views.main_components.topbar.top_bar_animator import TopBarAnimationManager
from app.views.main_components.topbar.top_bar_event_handler import TopBarEventHandler

try:
    from sip import isdeleted as _sip_isdeleted
except ImportError:
    def _sip_isdeleted(obj: QObject) -> bool:
        return False

logger = logging.getLogger(__name__)


class TopBarLayoutManager(QObject):
    """Координатор компонентов топбара с четким разделением ответственности."""

    def __init__(
        self,
        window: QObject,
        config: TopBarConfig,
        calculator: TopBarLayoutCalculator,
        animator: TopBarAnimationManager,
        event_handler: TopBarEventHandler
    ) -> None:
        """Инициализация менеджера с dependency injection."""
        super().__init__(window)
        self.window = window
        self.config = config
        self.calculator = calculator
        self.animator = animator
        self.event_handler = event_handler

        # Состояние
        self._last_applied: Optional[Tuple[int, int, int, int]] = None
        self._warmup_adjusts_remaining = 2

        logger.info("TopBarLayoutManager: initializing with new architecture")

        # Throttling timer для отложенных корректировок
        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.timeout.connect(self._run_adjust)

        # Подключение событий
        self._setup_connections()

    def _setup_connections(self) -> None:
        """Настройка подключений к событиям."""
        # Подключение к сигналу shown окна
        if hasattr(self.window, "shown"):
            try:
                self.window.shown.connect(self.adjust)
            except RuntimeError:
                logger.debug("Failed to connect to window.shown signal")

        # Установка event filter'ов на основные виджеты
        widgets_to_watch = [
            "top_bar_host",
            "content_container",
            "quick_add_widget",
            "fav_widget",
            "recent_links_widget"
        ]

        for widget_name in widgets_to_watch:
            widget = self._get_widget(widget_name)
            if widget:
                self.event_handler.install_event_filters(widget)

        # Установка event filter на окно
        if isinstance(self.window, QWidget) and not _sip_isdeleted(self.window):
            self.event_handler.install_event_filters(self.window)

    def _get_widget(self, name: str) -> Optional[QWidget]:
        """Безопасное получение виджета по имени атрибута."""
        try:
            widget = getattr(self.window, name, None)
            if isinstance(widget, QWidget) and not _sip_isdeleted(widget):
                return widget
        except (AttributeError, RuntimeError):
            pass
        return None

    def _run_adjust(self) -> None:
        """Выполнить отложенную корректировку layout'а."""
        self.adjust()

    def adjust(self) -> None:
        """Основной метод пересчета layout'а."""
        logger.info("TopBarLayoutManager: adjust() called")
        container = self._get_container_widget()

        # Получить единую ширину для всех расчетов
        window_width = int(self.window.width()) if hasattr(self.window, "width") else 0
        container_width = container.width() if container else 0
        effective_width = min(container_width, window_width) if window_width > 0 else container_width

        logger.debug(
            f"TopBarLayoutManager.adjust() called: container={container}, "
            f"container_width={container_width}, window_width={window_width}, "
            f"effective_width={effective_width}"
        )

        if not container or effective_width <= 0:
            logger.debug("TopBarLayoutManager: container not ready or zero width")
            # Перед ранним выходом зажимаем поиск до минимальной ширины
            search = self._get_widget("search")
            if isinstance(search, QLineEdit):
                try:
                    search.setMaximumWidth(self.config.min_search_width)
                except RuntimeError:
                    pass
            return

        # Не меняем раскладку, пока контейнер верхней панели ещё скрыт — это предотвращает
        # преждевременное растягивание поиска до показа top_bar_host
        try:
            if hasattr(container, "isVisible") and not container.isVisible():
                # Также зажимаем поиск при скрытом контейнере
                search = self._get_widget("search")
                if isinstance(search, QLineEdit):
                    try:
                        search.setMaximumWidth(self.config.min_search_width)
                    except RuntimeError:
                        pass
                return
        except (AttributeError, RuntimeError):
            pass

        # Проверить узкий режим по единой ширине
        if effective_width <= self.config.narrow_threshold:
            logger.info("TopBarLayoutManager: applying narrow mode")
            self._apply_narrow_mode()
            return

        logger.debug("TopBarLayoutManager: normal mode, proceeding with layout calculation")

        # Выход из узкого режима
        search = self._get_widget("search")
        if isinstance(search, QLineEdit):
            self._restore_search_actions(search)

        # Получить панели и кнопки
        recent_panel, recent_buttons = self._get_panel_and_buttons("recent_links_widget", "recentButton")
        fav_panel, fav_buttons = self._get_panel_and_buttons("fav_widget", "favoriteButton")
        quick_panel, quick_buttons = self._get_panel_and_buttons("quick_add_widget", "quickButton")
        search_widget = self._get_widget("search")

        # Получить top_bar layout
        top_bar = self._get_top_bar()
        if not top_bar:
            return

        # Рассчитать оптимальные количества
        counts = self.calculator.compute_visible_counts(
            effective_width,
            top_bar,
            search_widget,
            recent_panel,
            fav_panel,
            quick_panel,
            recent_buttons,
            fav_buttons,
            quick_buttons
        )

        # Проверить, изменилось ли состояние
        if self._should_skip_adjust(effective_width, counts):
            return

        # Применить изменения
        self._apply_layout_changes(
            effective_width,
            top_bar,
            search_widget,
            recent_panel,
            fav_panel,
            quick_panel,
            recent_buttons,
            fav_buttons,
            quick_buttons,
            counts
        )

    def _get_container_widget(self) -> Optional[QWidget]:
        """Получить контейнер топбара."""
        return self._get_widget("top_bar_host") or self._get_widget("content_container")

    def _get_top_bar(self) -> Optional[QHBoxLayout]:
        """Получить layout топбара."""
        container = self._get_container_widget()
        if isinstance(container, QWidget):
            layout = container.layout()
            if isinstance(layout, QHBoxLayout):
                return layout
        return None

    def _get_panel_and_buttons(self, panel_name: str, button_name: str) -> Tuple[Optional[QWidget], List[QToolButton]]:
        """Получить панель и список кнопок."""
        panel = self._get_widget(panel_name)
        buttons = self._get_buttons(panel, button_name)
        return panel, buttons

    def _get_buttons(self, panel: Optional[QWidget], name: str) -> List[QToolButton]:
        """Получить кнопки из панели."""
        if not panel:
            return []

        buttons: List[QToolButton] = []

        # Получить layout панели
        layout = None
        bg_frame = getattr(panel, "bg_frame", None)
        if bg_frame and hasattr(bg_frame, "layout"):
            layout = bg_frame.layout()

        # Найти кнопки в layout
        if layout:
            for i in range(layout.count()):
                item = layout.itemAt(i)
                widget = item.widget()
                if isinstance(widget, QToolButton) and widget.objectName() == name:
                    buttons.append(widget)

        # Добавить кнопки, найденные через findChildren
        for button in panel.findChildren(QToolButton, name):
            if button not in buttons:
                buttons.append(button)

        return buttons

    def _is_narrow_mode(self, container: QWidget) -> bool:
        """Проверить, активен ли узкий режим."""
        try:
            # Используем единую логику effective_width как в adjust()
            window_width = int(self.window.width()) if hasattr(self.window, "width") else 0
            cont_visible = getattr(container, "isVisible", lambda: True)()
            cont_width = int(container.width())

            effective_width = min(cont_width, window_width) if window_width > 0 else cont_width

            logger.debug(
                f"TopBarLayoutManager: checking narrow mode: container_width={cont_width}, "
                f"container_visible={cont_visible}, window_width={window_width}, "
                f"effective_width={effective_width}, threshold={self.config.narrow_threshold}, "
                f"narrow_mode={effective_width <= self.config.narrow_threshold}"
            )
            return effective_width <= self.config.narrow_threshold
        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            logger.warning(f"TopBarLayoutManager: error checking narrow mode: {e}")
            # Фолбэк: используем ширину окна при ошибке
            try:
                ww = int(self.window.width())
            except Exception:
                ww = 0
            if ww > 0:
                return ww <= self.config.narrow_threshold
            return container.width() <= self.config.narrow_threshold

    def _should_skip_adjust(self, width: int, counts: Tuple[int, int, int]) -> bool:
        """Проверить, нужно ли пропустить пересчет."""
        state = (width, *counts)
        if self._last_applied == state:
            return True

        # Warmup: пропустить первые пересчеты для стабилизации
        if self._warmup_adjusts_remaining > 0:
            self._warmup_adjusts_remaining -= 1
            # Во время прогрева применяем нулевые квоты для стабилизации
            self._apply_zero_counts()
            self._throttle_timer.start(0)
            return True

        # Hysteresis: предотвратить частые переключения
        if self._last_applied and self._should_apply_hysteresis(width, counts):
            return True

        return False

    def _apply_zero_counts(self) -> None:
        """Применить нулевые квоты во время прогрева."""
        try:
            recent_panel = self._get_widget("recent_links_widget")
            fav_panel = self._get_widget("fav_widget")
            quick_panel = self._get_widget("quick_add_widget")

            # Скрыть все кнопки
            for panel, button_name in [(recent_panel, "recentButton"),
                                     (fav_panel, "favoriteButton"),
                                     (quick_panel, "quickButton")]:
                if panel:
                    buttons = self._get_buttons(panel, button_name)
                    for button in buttons:
                        try:
                            button.setVisible(False)
                        except RuntimeError:
                            pass
                    panel.setMaximumWidth(0)
        except Exception:
            logger.debug("TopBarLayoutManager: failed to apply zero counts during warmup")

    def _should_apply_hysteresis(self, width: int, counts: Tuple[int, int, int]) -> bool:
        """Проверить, нужно ли применить гистерезис."""
        if not self._last_applied:
            return False

        _, prev_recent, prev_fav, prev_quick = self._last_applied
        prev_total = self._calculate_total_width_for_state(
            self._get_top_bar(),
            self._get_widget("search"),
            *self._get_panel_and_buttons("recent_links_widget", "recentButton"),
            *self._get_panel_and_buttons("fav_widget", "favoriteButton"),
            *self._get_panel_and_buttons("quick_add_widget", "quickButton"),
            prev_recent, prev_fav, prev_quick
        )

        current_total = self._calculate_total_width_for_state(
            self._get_top_bar(),
            self._get_widget("search"),
            *self._get_panel_and_buttons("recent_links_widget", "recentButton"),
            *self._get_panel_and_buttons("fav_widget", "favoriteButton"),
            *self._get_panel_and_buttons("quick_add_widget", "quickButton"),
            *counts
        )

        band = max(8, self.config.button_size // 2)
        return abs(width - current_total) < band and abs(width - prev_total) < band

    def _calculate_total_width_for_state(
        self,
        top_bar: Optional[QHBoxLayout],
        search: Optional[QLineEdit],
        recent_panel: Optional[QWidget],
        recent_buttons: List[QToolButton],
        fav_panel: Optional[QWidget],
        fav_buttons: List[QToolButton],
        quick_panel: Optional[QWidget],
        quick_buttons: List[QToolButton],
        recent_count: int,
        fav_count: int,
        quick_count: int
    ) -> int:
        """Рассчитать общую ширину для заданного состояния."""
        if not top_bar:
            return 0

        return self.calculator.calculate_total_width(
            top_bar, search, recent_panel, fav_panel, quick_panel,
            recent_buttons, fav_buttons, quick_buttons,
            recent_count, fav_count, quick_count
        )

    def _apply_layout_changes(
        self,
        width: int,
        top_bar: QHBoxLayout,
        search: Optional[QLineEdit],
        recent_panel: Optional[QWidget],
        fav_panel: Optional[QWidget],
        quick_panel: Optional[QWidget],
        recent_buttons: List[QToolButton],
        fav_buttons: List[QToolButton],
        quick_buttons: List[QToolButton],
        counts: Tuple[int, int, int]
    ) -> None:
        """Применить изменения к layout'у."""
        logger.info(f"TopBarLayoutManager: applying layout changes: width={width}, counts={counts}")
        recent_count, fav_count, quick_count = counts

        # Применить изменения к каждой панели
        recent_visible = self._apply_panel_changes(
            recent_panel, recent_buttons, "recentButton", recent_count
        )
        fav_visible = self._apply_panel_changes(
            fav_panel, fav_buttons, "favoriteButton", fav_count
        )
        quick_visible = self._apply_panel_changes(
            quick_panel, quick_buttons, "quickButton", quick_count
        )

        # Обновить состояние
        self._last_applied = (width, recent_visible, fav_visible, quick_visible)

        # Обновить разделители
        self._update_separators(top_bar, recent_visible > 0, fav_visible > 0, quick_visible > 0, search is not None)

        # Обновить отступы топбара
        self._update_top_bar_margins(top_bar)

        # Применить ограничения к поиску
        self._apply_search_constraints(top_bar, search)

        # Логирование
        if self.config.log_info:
            logger.info(
                f"[TopBar] Applied: recent={recent_visible}, fav={fav_visible}, quick={quick_visible}"
            )
        logger.info("TopBarLayoutManager: layout changes applied successfully")

    def _apply_panel_changes(
        self,
        panel: Optional[QWidget],
        buttons: List[QToolButton],
        button_name: str,
        target_count: int
    ) -> int:
        """Применить изменения к одной панели."""
        if not panel:
            return 0

        # Установить видимость кнопок
        visible_count = 0
        for i, button in enumerate(buttons):
            try:
                button.setVisible(i < target_count)
                if i < target_count:
                    visible_count = i + 1
            except RuntimeError:
                pass

        # Установить ширину панели
        panel.setMinimumWidth(0)
        max_width = self.calculator.calculate_panel_width(panel, buttons, visible_count)
        panel.setMaximumWidth(max_width if visible_count > 0 else 0)

        # Убедиться, что панель видима
        try:
            panel.setVisible(True)
            panel.updateGeometry()
        except RuntimeError:
            pass

        return visible_count

    def _update_separators(
        self,
        top_bar: QHBoxLayout,
        recent_visible: bool,
        fav_visible: bool,
        quick_visible: bool,
        search_exists: bool
    ) -> None:
        """Обновить видимость разделителей."""
        # Эта логика может быть вынесена в отдельный компонент
        count = top_bar.count()
        for i in range(count):
            item = top_bar.itemAt(i)
            widget = item.widget()

            if self._is_separator(widget):
                # Определить, нужно ли показывать разделитель
                left_widget = self._find_left_widget(top_bar, i)
                right_widget = self._find_right_widget(top_bar, i)

                show_sep = self._should_show_separator(
                    left_widget, right_widget, recent_visible, fav_visible, quick_visible, search_exists
                )

                try:
                    widget.setVisible(show_sep)
                except RuntimeError:
                    pass

        top_bar.invalidate()

    def _is_separator(self, widget: Optional[QWidget]) -> bool:
        """Проверить, является ли виджет разделителем."""
        if not widget:
            return False
        return (
            widget.objectName() == "vSeparator" or
            widget.property("class") == "vertical_separator"
        )

    def _find_left_widget(self, top_bar: QHBoxLayout, separator_index: int) -> Optional[QWidget]:
        """Найти виджет слева от разделителя."""
        for i in range(separator_index - 1, -1, -1):
            item = top_bar.itemAt(i)
            widget = item.widget()
            if widget:
                return widget
        return None

    def _find_right_widget(self, top_bar: QHBoxLayout, separator_index: int) -> Optional[QWidget]:
        """Найти виджет справа от разделителя."""
        for i in range(separator_index + 1, top_bar.count()):
            item = top_bar.itemAt(i)
            widget = item.widget()
            if widget:
                return widget
        return None

    def _should_show_separator(
        self,
        left_widget: Optional[QWidget],
        right_widget: Optional[QWidget],
        recent_visible: bool,
        fav_visible: bool,
        quick_visible: bool,
        search_exists: bool
    ) -> bool:
        """Определить, нужно ли показывать разделитель."""
        def is_panel_visible(widget: Optional[QWidget]) -> bool:
            if not widget:
                return False
            if widget is self._get_widget("recent_links_widget"):
                return recent_visible and widget.isVisible()
            if widget is self._get_widget("fav_widget"):
                return fav_visible and widget.isVisible()
            if widget is self._get_widget("quick_add_widget"):
                return quick_visible and widget.isVisible()
            return False

        left_visible = is_panel_visible(left_widget)
        right_visible = is_panel_visible(right_widget) or (search_exists and isinstance(right_widget, QLineEdit))

        return left_visible and right_visible

    def _update_top_bar_margins(self, top_bar: QHBoxLayout) -> None:
        """Обновить отступы топбара."""
        try:
            side_margin = 8  # Можно вынести в конфиг
            top_bar.setContentsMargins(side_margin, 0, side_margin, 0)
        except RuntimeError:
            pass

    def _apply_search_constraints(self, top_bar: QHBoxLayout, search: Optional[QLineEdit]) -> None:
        """Применить ограничения к полю поиска."""
        if not isinstance(search, QLineEdit):
            return

        try:
            # Получить единую ширину для расчетов
            container = self._get_container_widget()
            window_width = int(self.window.width()) if hasattr(self.window, "width") else 0
            container_width = container.width() if container else 0
            effective_width = min(container_width, window_width) if window_width > 0 else container_width

            # Рассчитать оставшееся место
            occupied_width = 0
            count = top_bar.count()

            for i in range(count):
                item = top_bar.itemAt(i)
                widget = item.widget()

                if widget and widget is not search and widget.isVisible():
                    try:
                        occupied_width += widget.width()
                    except RuntimeError:
                        occupied_width += widget.sizeHint().width()

                # Учитывать спейсеры
                elif item.spacerItem():
                    spacer_width = item.spacerItem().sizeHint().width()
                    occupied_width += max(0, spacer_width)

            # Добавить spacing и margins
            spacing = top_bar.spacing() or 0
            visible_widgets = [item.widget() for item in [top_bar.itemAt(i) for i in range(count)]
                             if item.widget() is not None and item.widget() is not search and item.widget().isVisible()]
            occupied_width += spacing * max(0, len(visible_widgets) - 1)

            margins = top_bar.contentsMargins()
            occupied_width += margins.left() + margins.right()

            remaining = max(0, effective_width - occupied_width)

            # Установить ограничения
            min_width = max(self.config.min_search_width, search.minimumWidth() or 0)
            max_width = max(min_width, remaining)

            search.setMinimumWidth(min_width)
            search.setMaximumWidth(max_width)

        except RuntimeError:
            logger.debug("Failed to apply search constraints")

    def _apply_narrow_mode(self) -> None:
        """Применить узкий режим."""
        logger.info("TopBarLayoutManager: _apply_narrow_mode() called")
        top_bar = self._get_top_bar()
        search = self._get_widget("search")

        logger.debug(f"TopBarLayoutManager: narrow mode - top_bar={top_bar}, search={search}")

        if not top_bar:
            logger.warning("TopBarLayoutManager: narrow mode - no top_bar found")
            return

        # Скрыть только панели с кнопками, оставить разделители и поиск видимыми
        hidden_panels = []
        for i in range(top_bar.count()):
            item = top_bar.itemAt(i)
            widget = item.widget()
            if widget and widget is not search:
                # Скрывать только панели с кнопками, не трогать разделители
                if (hasattr(widget, 'objectName') and
                    widget.objectName() in ['quickAddPanel', 'favoritesWidget', 'recentLinksWidget']):
                    try:
                        widget.setVisible(False)
                        hidden_panels.append(widget.objectName() or str(type(widget).__name__))
                        logger.debug(f"TopBarLayoutManager: narrow mode - hid panel: {widget.objectName()}")
                    except RuntimeError:
                        pass

        logger.info(f"TopBarLayoutManager: narrow mode - hidden panels: {hidden_panels}")

        # Обнулить отступы
        try:
            top_bar.setContentsMargins(0, 0, 0, 0)
        except RuntimeError:
            pass

        # Растянуть поиск
        if isinstance(search, QLineEdit):
            try:
                search.setMinimumWidth(0)
                search.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX
                search.setSizePolicy(
                    search.sizePolicy().horizontalPolicy(),  # Keep vertical
                    search.sizePolicy().verticalPolicy()
                )
                logger.debug("TopBarLayoutManager: narrow mode - search widget configured")
            except RuntimeError:
                pass

        # Обновить layout
        top_bar.invalidate()
        container = self._get_container_widget()
        if container:
            try:
                container.updateGeometry()
                container.update()
                logger.debug("TopBarLayoutManager: narrow mode - container updated")
            except RuntimeError:
                pass

        logger.info("TopBarLayoutManager: narrow mode applied successfully")

    def _restore_search_actions(self, search: QLineEdit) -> None:
        """Восстановить действия поиска после выхода из узкого режима."""
        try:
            if hasattr(search, "setClearButtonEnabled"):
                search.setClearButtonEnabled(True)
        except RuntimeError:
            pass

        try:
            for action in search.actions():
                try:
                    action.setVisible(True)
                except RuntimeError:
                    pass
        except RuntimeError:
            pass

    def cleanup(self) -> None:
        """Очистка ресурсов."""
        self.event_handler.cleanup()
        self.animator.cleanup()
        self.calculator.clear_cache()
