# app/views/main_components/bottom_panel_setup.py
from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from app.config_data import app_config

logger = logging.getLogger(__name__)


@runtime_checkable
class WindowUISetupProtocol(Protocol):
    """Protocol for WindowUISetup to enable better type checking without circular imports."""
    window: QWidget
    main_layout: Any  # Typically QVBoxLayout
    fonts: Any  # Typically dict with 'bottom_bar_button_px'


class BottomPanelBuilder:
    """Собирает нижнюю панель, используя существующее поведение WindowUISetup (без изменений)."""

    def __init__(self, ui: WindowUISetupProtocol) -> None:
        self.ui = ui
        self.window = ui.window
        self.main_layout = ui.main_layout

    def build(self) -> None:
        """Собирает и подключает нижнюю панель (полоса действий + разделитель).

        Обязанности:
        - Создать нижний layout с отступами/spacing из UIConfig
        - Построить кнопки действий по `bottom_actions` и подключить обработчики кликов
        - Создать контейнер `bottom_bar_container`, настроить политику размеров и добавить в основной layout
        - Добавить виджет-разделитель под панелью

        Примечание: сохраняет имеющееся поведение, включая политики фокуса и обработку ошибок.
        """
        bottom_layout = QHBoxLayout()
        # Полное прилегание: без внутренних отступов и без межкнопочного зазора
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)

        # Шрифт нижней панели задаётся централизованно через ui.fonts.bottom_bar_button_px (ThemeController)
        # Применяем шрифт здесь для консистентности (если не сделано в QSS)
        if hasattr(self.ui, 'fonts') and hasattr(self.ui.fonts, 'bottom_bar_button_px'):
            bottom_font = self.ui.fonts.bottom_bar_button_px
            # Примечание: в реальности применить через QApplication.setFont или stylesheet

        # Кнопка переключения сфер (будет создана после инициализации контроллеров)
        # Добавляем placeholder для будущей вставки (например, в начало layout)
        self.window.switch_sphere_button = None
        placeholder = QWidget()  # Временный spacer для будущей кнопки
        placeholder.setFixedWidth(0)  # Не занимает место изначально
        placeholder.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        bottom_layout.addWidget(placeholder)

        # Дополнительные кнопки из конфигурации (кэшируем для производительности)
        bottom_actions = app_config.ui.get_bottom_actions()
        bottom_btns: list[QPushButton] = []
        for text, fn_name in bottom_actions:
            btn = QPushButton(text)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # Улучшение доступности: добавляем accessible name для screen readers
            btn.setAccessibleName(text)
            btn.setAccessibleDescription(f"Кнопка действия: {text}")
            # Разрешаем горизонтальное сжатие ниже sizeHint
            try:
                btn.setMinimumWidth(0)
                btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            except (RuntimeError, TypeError) as e:
                logger.debug(
                    "BottomPanel: failed to apply size policy to bottom button '%s': %s",
                    text, e,
                    exc_info=True,
                )
            # Обработчик клика и добавление на панель
            handler = getattr(self.window, fn_name, None)
            if not callable(handler):
                logger.warning(
                    "BottomPanel: click handler '%s' not found for button '%s' — skipping",
                    fn_name, text,
                )
                continue
            try:
                btn.clicked.connect(handler)
            except (TypeError, RuntimeError) as e:
                logger.warning(
                    "BottomPanel: failed to connect handler '%s' for button '%s': %s — skipping",
                    fn_name, text, e,
                    exc_info=True,
                )
                continue
            bottom_layout.addWidget(btn)
            bottom_btns.append(btn)

        # Помечаем последнюю кнопку, чтобы убрать у неё правую границу через QSS
        if bottom_btns:
            try:
                bottom_btns[-1].setProperty("last", "1")
            except (RuntimeError, AttributeError) as e:
                logger.debug(
                    "BottomPanel: failed to set 'last' property on final button: %s",
                    e, exc_info=True,
                )

        # Контейнер для bottom bar
        container_parent = (
            getattr(self.main_layout, "parentWidget", lambda: None)()
            or self.window.centralWidget()
        )
        bottom_bar_container = QWidget(container_parent)
        bottom_bar_container.setObjectName("bottomBarContainer")
        bottom_bar_container.setLayout(bottom_layout)
        # Сохраняем виджет как атрибут окна для последующей настройки фокуса
        self.window.bottom_bar_container = bottom_bar_container
        # Явная политика: по горизонтали расширяется/сжимается, по вертикали фиксированная
        try:
            bottom_bar_container.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
        except (RuntimeError, TypeError) as e:
            logger.debug(
                "BottomPanel: failed to set size policy on bottom bar container: %s",
                e, exc_info=True,
            )

        # Добавляем контейнер в основной layout (в конец, перед разделителем если он есть)
        self.main_layout.addWidget(bottom_bar_container)

        # Убираем нижний разделитель: панель примыкает вплотную к содержимому
        # Ищем разделитель по objectName (предполагаем, что он добавлен ранее как "bottomSeparator")
        # Для robustness: ищем среди детей layout
        separator = self._find_separator_in_layout(self.main_layout)
        if separator:
            try:
                self.main_layout.removeWidget(separator)
                separator.setParent(None)  # Освобождаем ресурсы
                separator.deleteLater()  # Qt-идиома для отложенного удаления
                logger.debug("BottomPanel: removed bottom separator")
            except (RuntimeError, AttributeError) as e:
                logger.warning("BottomPanel: failed to remove bottom separator: %s", e)
        else:
            logger.debug("BottomPanel: no bottom separator found to remove")

    def _find_separator_in_layout(self, layout: Any) -> QWidget | None:
        """Вспомогательный метод: находит разделитель в layout по objectName."""
        if not hasattr(layout, 'itemAt') or not callable(layout.itemAt):
            return None
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is None:
                continue
            widget = item.widget()
            if isinstance(widget, QWidget) and widget.objectName() == "bottomSeparator":
                return widget
        return None

    def add_switch_sphere_button(self, button: QPushButton) -> None:
        """Добавляет кнопку переключения сфер в начало bottom layout (после placeholder)."""
        if not hasattr(self.window, 'bottom_bar_container') or self.window.bottom_bar_container is None:
            logger.warning("BottomPanel: cannot add switch button - container not built yet")
            return
        bottom_layout = self.window.bottom_bar_container.layout()
        if bottom_layout is None or not isinstance(bottom_layout, QHBoxLayout):
            logger.warning("BottomPanel: invalid layout for adding switch button")
            return
        # Находим placeholder (первый widget)
        if bottom_layout.count() > 0:
            placeholder_item = bottom_layout.itemAt(0)
            if placeholder_item and placeholder_item.widget():
                # Вставляем кнопку перед placeholder и удаляем placeholder
                bottom_layout.insertWidget(0, button)
                bottom_layout.removeWidget(placeholder_item.widget())
                placeholder_item.widget().setParent(None)
                placeholder_item.widget().deleteLater()
                self.window.switch_sphere_button = button
                logger.debug("BottomPanel: added switch sphere button")
            else:
                # Fallback: добавляем в начало
                bottom_layout.insertWidget(0, button)
                self.window.switch_sphere_button = button
                logger.debug("BottomPanel: added switch sphere button (fallback)")