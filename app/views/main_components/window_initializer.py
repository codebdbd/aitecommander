# app/views/main_components/window_initializer.py

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

from app.controllers.system.window_controllers_setup import WindowControllersSetup
from app.interfaces import MainWindowLike, SettingsLike
from app.utils.ui.updates import suspend_updates

# Компоненты для рефакторинга
from .window_ui_setup import WindowUISetup


class WindowInitializer:
    """Инициализатор главного окна - извлекает всю логику создания UI из __init__."""

    def __init__(
        self,
        main_window: MainWindowLike,
        db: Any,
        settings: SettingsLike,
        theme_ctrl: Any,
    ) -> None:
        """
        Инициализация компонента.

        Args:
            main_window: Ссылка на главное окно (должно поддерживать setUpdatesEnabled)
            db: База данных (объект БД/фасад; конкретный тип варьируется)
            settings: Настройки приложения (должны предоставлять get_font_size)
            theme_ctrl: Контроллер тем (тип зависит от реализации)
        """
        self.window = main_window
        self.db = db
        self.settings = settings
        self.theme_ctrl = theme_ctrl

        # Композиция компонентов (пока сохраняем старую логику для обратной совместимости)
        self.ui_setup = WindowUISetup(self)
        self.controllers_setup = WindowControllersSetup(self)

    def initialize_window(self) -> None:
        """Выполняет полную инициализацию главного окна пошагово."""
        # Список шагов инициализации, выполняемых с отключёнными обновлениями
        init_steps = (
            self._init_window_properties,
            self._init_basic_attributes,
            self._init_menu,
            self._init_central_widget,
            self._capture_main_layout,
            self._init_top_panel,
            self._init_main_content,
            self._init_bottom_panel,
            self._init_status_bar,
            self._init_controllers,
            self._init_shortcuts,
            self._apply_user_font_size,
        )

        # На время инициализации отключаем обновления через контекстный менеджер
        with suspend_updates(self.window):
            for step in init_steps:
                step()

        # Инициализация сфер выполняется асинхронно (вне suspend_updates)
        self._initialize_spheres()

    # === Приватные шаги инициализации ===
    def _init_window_properties(self) -> None:
        self.ui_setup.setup_window_properties()

    def _init_basic_attributes(self) -> None:
        self.ui_setup.setup_basic_attributes()

    def _init_menu(self) -> None:
        self.ui_setup.setup_menu()

    def _init_central_widget(self) -> None:
        self.ui_setup.setup_central_widget()

    def _capture_main_layout(self) -> None:
        # Получаем main_layout из UI компонента для совместимости со старыми методами
        self.main_layout = self.ui_setup.main_layout

    def _init_top_panel(self) -> None:
        self.ui_setup.setup_top_panel()

    def _init_main_content(self) -> None:
        self.ui_setup.setup_main_content()

    def _init_bottom_panel(self) -> None:
        self.ui_setup.setup_bottom_panel()

    def _init_status_bar(self) -> None:
        self.ui_setup.setup_status_bar()

    def _init_controllers(self) -> None:
        # Контроллеры должны быть созданы до горячих клавиш
        self.controllers_setup.setup_controllers()

    def _init_shortcuts(self) -> None:
        # Горячие клавиши после создания контроллеров
        self.ui_setup.setup_shortcuts()

    def _apply_user_font_size(self) -> None:
        # Централизованно применяем пользовательский размер шрифта к дереву и таблице
        if hasattr(self.settings, "get_font_size") and hasattr(self.window, "apply_font_size_to_content"):
            fs = self.settings.get_font_size()
            try:
                with suppress(AttributeError, ValueError, TypeError):
                    if fs:
                        # Тип окна может не объявлять этот метод в протоколе — вызываем под hasattr
                        self.window.apply_font_size_to_content(int(fs))  # type: ignore[attr-defined]
            except Exception:
                # Логируем неожиданные ошибки, чтобы не терять диагностику
                logging.exception("WindowInitializer: unexpected error applying font size")

    def _initialize_spheres(self) -> None:
        self.controllers_setup.initialize_spheres()
