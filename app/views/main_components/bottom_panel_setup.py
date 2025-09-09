# app/views/main_components/bottom_panel_setup.py
from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from app.config_data import app_config

logger = logging.getLogger(__name__)


class BottomPanelBuilder:
    """Собирает нижнюю панель, используя существующее поведение WindowUISetup (без изменений)."""

    def __init__(self, ui: Any) -> None:
        # ui is WindowUISetup; typed as Any to avoid circular imports
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

        # Кнопка переключения сфер (будет создана после инициализации контроллеров)
        self.window.switch_sphere_button = None

        # Дополнительные кнопки из конфигурации
        bottom_actions = app_config.ui.get_bottom_actions()
        bottom_btns = []
        for text, fn_name in bottom_actions:
            btn = QPushButton(text)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # Разрешаем горизонтальное сжатие ниже sizeHint
            try:
                btn.setMinimumWidth(0)
                btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            except (RuntimeError, TypeError):
                logger.debug(
                    "BottomPanel: failed to apply size policy to bottom button '%s'",
                    text,
                    exc_info=True,
                )
            # Обработчик клика и добавление на панель
            handler = getattr(self.window, fn_name, None)
            if not callable(handler):
                logger.warning(
                    "BottomPanel: click handler '%s' not found for button '%s' — skipping",
                    fn_name,
                    text,
                )
                continue
            try:
                btn.clicked.connect(handler)
            except (TypeError, RuntimeError):
                logger.warning(
                    "BottomPanel: failed to connect handler '%s' for button '%s' — skipping",
                    fn_name,
                    text,
                    exc_info=True,
                )
                continue
            bottom_layout.addWidget(btn)
            bottom_btns.append(btn)

        # Помечаем последнюю кнопку, чтобы убрать у неё правую границу через QSS
        if bottom_btns:
            try:
                bottom_btns[-1].setProperty("last", "1")
            except (RuntimeError, AttributeError):
                logger.debug(
                    "BottomPanel: failed to set 'last' property on final button",
                    exc_info=True,
                )

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
        except (RuntimeError, TypeError):
            logger.debug(
                "BottomPanel: failed to set size policy on bottom bar container",
                exc_info=True,
            )

        self.main_layout.addWidget(bottom_bar_container)

        # Убираем нижний разделитель: панель примыкает вплотную к содержимому
