# app/views/main_components/window_initializer.py

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)
from contextlib import suppress
from typing import Any

from PyQt6.QtCore import QTimer
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
        # Лёгкие шаги инициализации выполняем синхронно с отключёнными обновлениями,
        # чтобы окно появлялось быстрее и уже со стандартной структурой
        light_steps = (
            self._init_window_properties,
            self._init_basic_attributes,
            self._init_menu,
            self._init_central_widget,
            self._capture_main_layout,
        )

        with suspend_updates(self.window):
            for step in light_steps:
                step()

        # Показываем окно на следующем тике цикла событий, чтобы пользователь сразу увидел каркас UI
        try:
            if hasattr(self.window, "show"):
                QTimer.singleShot(0, self.window.show)
        except Exception:
            logger.exception("WindowInitializer: не удалось показать окно")

        # Подключаем обновление текста статус-бара к событию показа окна
        # (исключает попытки доступа к message_label до его создания)
        try:
            if hasattr(self.window, "shown"):
                # type: ignore[attr-defined] — сигнал присутствует в реальном MainWindow
                self.window.shown.connect(self._on_window_shown)  # noqa: E501
        except Exception:
            logger.exception("WindowInitializer: не удалось подключить слот к сигналу 'shown'")

        # Тяжёлые шаги переносим на следующий цикл событий после показа окна,
        # чтобы минимизировать время до первого отображения
        def _deferred_init():
            try:
                # Выполняем тяжёлые шаги уже после показа окна
                self._init_top_panel()
                self._init_main_content()
                self._init_bottom_panel()
                self._init_status_bar()
                # После создания статус-бара безопасно обновляем сообщение статуса
                try:
                    if hasattr(self.window, "message_label") and self.window.message_label:
                        self.window.message_label.setText("Загрузка интерфейса…")
                except Exception:
                    logger.exception("WindowInitializer: ошибка обновления текста статус-бара после инициализации")
                self._init_controllers()
                # Немедленно после создания контроллеров запускаем асинхронную
                # загрузку данных структуры, чтобы не блокировать UI-поток
                try:
                    sb = getattr(self.window, "structure_business", None)
                    ao = getattr(sb, "async_operations", None) if sb else None
                    if ao is not None:
                        # Загрузка доступных сфер
                        try:
                            QTimer.singleShot(0, ao.load_spheres_async)
                        except Exception:
                            logger.exception("WindowInitializer: не удалось запланировать load_spheres_async")

                        # Загрузка структуры текущей сферы, если она уже выбрана
                        try:
                            curr_id = getattr(sb, "current_sphere_id", None)
                            if isinstance(curr_id, int) and curr_id > 0:
                                QTimer.singleShot(0, lambda cid=int(curr_id): ao.load_structure_async(cid))
                        except Exception:
                            logger.exception("WindowInitializer: не удалось запланировать load_structure_async")
                except Exception:
                    # Общий страховочный перехват, чтобы отложенная инициализация не падала целиком
                    logger.exception("WindowInitializer: ошибка планирования асинхронной загрузки структуры")
                self._apply_user_font_size()
            except Exception:
                logger.exception("WindowInitializer: ошибка в отложенной инициализации")
            finally:
                # Сначала завершаем инициализацию сфер и все связанные расчёты размеров,
                # избегая долгой блокировки обновлений
                try:
                    self._initialize_spheres()
                except Exception:
                    logger.exception("WindowInitializer: ошибка инициализации сфер")

        QTimer.singleShot(0, _deferred_init)

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
                logger.exception("WindowInitializer: unexpected error applying font size")

    def _initialize_spheres(self) -> None:
        self.controllers_setup.initialize_spheres()

    # === Слоты ===
    def _on_window_shown(self) -> None:
        """Обновляем статус только после показа окна (и, соответственно, после инициализации статус-бара)."""
        try:
            if hasattr(self.window, "message_label") and self.window.message_label:
                self.window.message_label.setText("Загрузка интерфейса…")
        except Exception:
            logger.exception("WindowInitializer: ошибка обновления текста статус-бара в _on_window_shown")
