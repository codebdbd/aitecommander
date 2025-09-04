# app/views/main_components/window_initializer.py

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)
from contextlib import suppress
from typing import Any

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox
from app.controllers.system.window_controllers_setup import WindowControllersSetup
from app.interfaces import MainWindowLike, SettingsLike
from app.utils.ui.updates import suspend_updates
from app.utils.metrics.startup_metrics import get_metrics
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
        metrics = get_metrics()
        metrics.reset()
        # Лёгкие шаги инициализации выполняем синхронно с отключёнными обновлениями,
        # чтобы окно появлялось быстрее и уже со стандартной структурой
        light_steps = (
            self._init_window_properties,
            self._init_basic_attributes,
            self._init_menu,
            self._init_central_widget,
            self._capture_main_layout,
            # ВАЖНО: создаём верхнюю панель ДО показа окна,
            # чтобы её высота была стабилизирована до первого рендера
            self._init_top_panel,
        )

        with suspend_updates(self.window):
            for step in light_steps:
                with metrics.time_span(f"light:{step.__name__}"):
                    step()

        # Подключаем обновление текста статус-бара к событию показа окна
        # Слот проверяет наличие элементов UI, поэтому вызов безопасен даже при отложенном создании статус-бара
        try:
            if hasattr(self.window, "shown"):
                # type: ignore[attr-defined] — сигнал присутствует в реальном MainWindow
                self.window.shown.connect(self._on_window_shown)  # noqa: E501
        except Exception:
            logger.exception("WindowInitializer: не удалось подключить слот к сигналу 'shown'")

        # Показываем окно сразу после лёгких шагов, чтобы пользователь видел интерфейс
        # пока выполняются тяжёлые операции в фоне
        try:
            if hasattr(self.window, "show"):
                with metrics.time_span("light:window_show"):
                    self.window.show()
        except Exception:
            logger.exception("WindowInitializer: не удалось показать окно после лёгких шагов")

        # Тяжёлые шаги разбиваем на асинхронные этапы для предотвращения блокировки UI-потока
        # Разделяем этапы на независимые от БД и зависящие от БД
        self._current_init_step = 0
        self._init_steps_before_db = [
            ("Загрузка основного содержимого...", self._init_main_content),
            ("Инициализация нижней панели...", self._init_bottom_panel),
            ("Создание статус-бара...", self._init_status_bar),
            ("Применение настроек шрифта...", self._apply_user_font_size),
        ]
        self._init_steps_after_db = [
            ("Настройка контроллеров...", self._init_controllers),
            ("Завершение инициализации...", self._initialize_spheres),
        ]
        self._db_ready = False
        self._waiting_for_db = False
        
        def _execute_next_init_step():
            """Выполняет следующий этап инициализации асинхронно."""
            try:
                # Проверяем, завершены ли этапы до БД
                if self._current_init_step >= len(self._init_steps_before_db):
                    if not self._db_ready:
                        # БД ещё не готова, ждём
                        if not self._waiting_for_db:
                            self._waiting_for_db = True
                            self._update_status_message("Ожидание готовности базы данных...")
                            self._setup_db_ready_listener()
                        return
                    else:
                        # БД готова, переходим к этапам после БД
                        self._execute_db_dependent_steps()
                        return
                
                step_name, step_func = self._init_steps_before_db[self._current_init_step]
                
                # Обновляем статус-бар если он уже создан
                self._update_status_message(step_name)
                
                # Выполняем текущий этап
                with metrics.time_span(f"heavy:{step_func.__name__}"):
                    step_func()
                
                # Специальная обработка после создания статус-бара
                if step_func == self._init_status_bar:
                    self._post_status_bar_init()
                
                self._current_init_step += 1
                
                # Даём UI-потоку возможность обработать события
                QApplication.processEvents()
                
                # Планируем следующий этап
                QTimer.singleShot(10, _execute_next_init_step)
                
            except Exception as e:
                logger.exception("WindowInitializer: ошибка в этапе инициализации — приложение будет закрыто")
                try:
                    metrics.flush_log(logger)
                except Exception:
                    pass
                self._handle_deferred_init_error(e)

        # Запускаем первый этап
        QTimer.singleShot(0, _execute_next_init_step)

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

    # === Вспомогательные методы для асинхронной инициализации ===
    def _update_status_message(self, message: str) -> None:
        """Обновляет сообщение в статус-баре, если он уже создан."""
        try:
            if hasattr(self.window, "message_label") and self.window.message_label:
                self.window.message_label.setText(message)
        except Exception:
            # Не логируем как ошибку, так как статус-бар может быть ещё не создан
            pass

    def _post_status_bar_init(self) -> None:
        """Выполняется после создания статус-бара."""
        try:
            if hasattr(self.window, "message_label") and self.window.message_label:
                self.window.message_label.setText("Загрузка интерфейса…")
        except Exception:
            logger.exception("WindowInitializer: ошибка обновления текста статус-бара после инициализации")

    def _post_controllers_init(self) -> None:
        """Выполняется после создания контроллеров - запускает асинхронную загрузку структуры."""
        try:
            sb = getattr(self.window, "structure_business", None)
            ao = getattr(sb, "async_operations", None) if sb else None
            if ao is not None:
                # Внимание: запуск загрузки сфер выполняется в SpheresBarController.init().
                # Здесь не дублируем, чтобы избежать двойного вызова и логов.

                # Загрузка структуры текущей сферы, если она уже выбрана
                try:
                    curr_id = getattr(sb, "current_sphere_id", None)
                    if isinstance(curr_id, int) and curr_id > 0:
                        metrics = get_metrics()
                        # Старт измерения асинхронной загрузки структуры; остановка по сигналу structure_loaded
                        metrics.start("async:structure_load")
                        try:
                            if hasattr(sb, "structure_loaded"):
                                def _on_structure_loaded_once(*_args):
                                    try:
                                        metrics.stop("async:structure_load")
                                    except Exception:
                                        pass
                                    try:
                                        sb.structure_loaded.disconnect(_on_structure_loaded_once)  # type: ignore[attr-defined]
                                    except Exception:
                                        pass
                                sb.structure_loaded.connect(_on_structure_loaded_once)  # type: ignore[attr-defined]
                        except Exception:
                            logger.debug("WindowInitializer: failed to wire metrics to structure_loaded", exc_info=False)
                        QTimer.singleShot(0, lambda cid=int(curr_id): ao.load_structure_async(cid))
                        metrics.mark("async:load_structure_async scheduled")
                except Exception:
                    logger.exception("WindowInitializer: не удалось запланировать load_structure_async")
        except Exception:
            # Общий страховочный перехват, чтобы отложенная инициализация не падала целиком
            logger.exception("WindowInitializer: ошибка планирования асинхронной загрузки структуры")

    def _setup_db_ready_listener(self) -> None:
        """Настраивает слушатель готовности БД."""
        try:
            # Проверяем, есть ли уже готовая БД (возможно, инициализация завершилась быстро)
            if hasattr(self.window, 'isEnabled') and self.window.isEnabled():
                # Окно разблокировано, значит БД готова
                self._on_db_ready()
                return
            
            # Устанавливаем таймер для периодической проверки готовности БД
            self._db_check_timer = QTimer()
            self._db_check_timer.timeout.connect(self._check_db_ready)
            self._db_check_timer.start(100)  # Проверяем каждые 100 мс
        except Exception:
            logger.exception("WindowInitializer: ошибка настройки слушателя готовности БД")

    def _check_db_ready(self) -> None:
        """Проверяет готовность БД."""
        try:
            # БД считается готовой, когда главное окно разблокировано
            if hasattr(self.window, 'isEnabled') and self.window.isEnabled():
                self._on_db_ready()
        except Exception:
            logger.exception("WindowInitializer: ошибка проверки готовности БД")

    def _on_db_ready(self) -> None:
        """Вызывается когда БД готова к использованию."""
        try:
            self._db_ready = True
            if hasattr(self, '_db_check_timer'):
                self._db_check_timer.stop()
                self._db_check_timer.deleteLater()
            
            logger.info("WindowInitializer: БД готова, продолжаем инициализацию контроллеров")
            self._execute_db_dependent_steps()
        except Exception:
            logger.exception("WindowInitializer: ошибка при обработке готовности БД")

    def _execute_db_dependent_steps(self) -> None:
        """Выполняет этапы инициализации, зависящие от БД."""
        self._current_db_step = 0
        
        def _execute_next_db_step():
            """Выполняет следующий этап инициализации, зависящий от БД."""
            try:
                if self._current_db_step >= len(self._init_steps_after_db):
                    # Все этапы завершены
                    self._finalize_initialization()
                    return
                
                step_name, step_func = self._init_steps_after_db[self._current_db_step]
                
                # Обновляем статус-бар
                self._update_status_message(step_name)
                
                # Выполняем текущий этап
                metrics = get_metrics()
                with metrics.time_span(f"heavy:{step_func.__name__}"):
                    step_func()
                
                # Специальная обработка после создания контроллеров
                if step_func == self._init_controllers:
                    self._post_controllers_init()
                
                self._current_db_step += 1
                
                # Даём UI-потоку возможность обработать события
                QApplication.processEvents()
                
                # Планируем следующий этап
                QTimer.singleShot(10, _execute_next_db_step)
                
            except Exception as e:
                logger.exception("WindowInitializer: ошибка в этапе инициализации зависящем от БД — приложение будет закрыто")
                try:
                    metrics = get_metrics()
                    metrics.flush_log(logger)
                except Exception:
                    pass
                self._handle_deferred_init_error(e)
        
        # Запускаем первый этап зависящий от БД
        QTimer.singleShot(0, _execute_next_db_step)

    def _finalize_initialization(self) -> None:
        """Завершает асинхронную инициализацию."""
        try:
            metrics = get_metrics()
            # Выводим сводку метрик старта в лог
            metrics.flush_log(logger)
            
            # Обновляем статус на "Готово"
            self._update_status_message("Готово")
            
            logger.info("WindowInitializer: асинхронная инициализация завершена успешно")
        except Exception:
            logger.exception("WindowInitializer: ошибка при финализации инициализации")

    # === Слоты ===
    def _on_window_shown(self) -> None:
        """Обновляем статус после показа окна.

        Учтено, что статус-бар создаётся отложенно: слот безопасно проверяет наличие
        необходимых элементов перед обновлением текста.
        """
        try:
            if hasattr(self.window, "message_label") and self.window.message_label:
                self.window.message_label.setText("Загрузка интерфейса…")
        except Exception:
            logger.exception("WindowInitializer: ошибка обновления текста статус-бара в _on_window_shown")

    # === Обработчики ошибок ===
    def _handle_deferred_init_error(self, exc: Exception) -> None:
        """Показывает диалог ошибки и завершает приложение при сбое отложенной инициализации."""
        try:
            parent = self.window if hasattr(self.window, "isVisible") else None
            QMessageBox.critical(parent, "Ошибка инициализации", f"Произошла ошибка при инициализации UI:\n{exc}")
        except Exception:
            logger.exception("WindowInitializer: не удалось показать диалог ошибки инициализации")
        finally:
            app = QApplication.instance()
            if app is not None:
                app.quit()
