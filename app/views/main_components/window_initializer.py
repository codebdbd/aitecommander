# app/views/main_components/window_initializer.py

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)
from contextlib import suppress
from typing import Any

from PyQt6.QtCore import QTimer, QEvent, QObject, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget
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
        # Фильтр сообщений Qt: подавить шумные предупреждения QPainter при сворачивании/разворачивании окна
        try:
            self._install_qt_message_filter()
        except Exception:
            logger.debug("QtMsgHandler: failed to install message filter", exc_info=True)
        # Диагностика фантомных окон: установить глобальный watcher один раз
        try:
            self._install_top_level_watcher()
        except Exception:
            logger.debug("DiagTopLevels: failed to install watcher", exc_info=True)
        # Диагностика: логирование первых событий Resize/Move главного окна
        try:
            self._install_window_resize_logger()
        except Exception:
            logger.debug("DiagTopLevels: failed to install resize logger", exc_info=True)
        # Диагностика: перехват вызовов QWidget.show()/setVisible(True) для top-level маленьких окон
        try:
            self._install_widget_show_hooks()
        except Exception:
            logger.debug("DiagTopLevels: failed to install QWidget.show hooks", exc_info=True)
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

        # Перед показом логируем текущее состояние top-level виджетов
        try:
            self._dump_top_levels("before window.show")
        except Exception:
            logger.debug("DiagTopLevels: failed to dump before show", exc_info=True)

        # Показываем окно сразу после лёгких шагов, чтобы пользователь видел интерфейс
        try:
            if hasattr(self.window, "show"):
                with metrics.time_span("light:window_show"):
                    self.window.show()
        except Exception:
            logger.exception("WindowInitializer: не удалось показать окно после лёгких шагов")

        # После показа — дампим top-level виджеты и планируем повторные проверки через 10 мс и 100 мс
        try:
            self._dump_top_levels("after window.show")
            QTimer.singleShot(10,  lambda: self._dump_top_levels("+10ms after show"))
            QTimer.singleShot(100, lambda: self._dump_top_levels("+100ms after show"))
        except Exception:
            logger.debug("DiagTopLevels: failed post-show dumps", exc_info=True)

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
                
                # Планируем следующий этап без лишней задержки
                QTimer.singleShot(0, _execute_next_init_step)
                
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
                
                # Планируем следующий этап без лишней задержки
                QTimer.singleShot(0, _execute_next_db_step)
                
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
            # Финальный снимок top-level виджетов
            try:
                self._dump_top_levels("finalize initialization")
            except Exception:
                logger.debug("DiagTopLevels: failed to dump at finalize", exc_info=True)
        except Exception:
            logger.exception("WindowInitializer: ошибка при финализации инициализации")

    # === Qt message handler ===
    def _install_qt_message_filter(self) -> None:
        """Устанавливает обработчик сообщений Qt для подавления шума QPainter::... в Release.

        Сообщения вида "QPainter::... Painter not active" часто приходят от внутренних стилей при
        анимации/сворачивании окна и не несут пользы для пользователя. Мы понижаем уровень до DEBUG
        или подавляем их полностью, чтобы лог не засорялся.
        """
        try:
            from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
        except Exception:
            return

        def _qt_msg_handler(msg_type, context, message):
            try:
                msg: str = str(message)
            except Exception:
                msg = ""
            # Фильтруем шумные сообщения про QPainter
            if msg.startswith("QPainter::") or "Painter not active" in msg:
                # Понижаем до DEBUG в наш лог, чтобы иметь след при необходимости
                try:
                    logger.debug("[QtMsgSuppressed] %s", msg)
                except Exception:
                    pass
                return
            # Прочие сообщения пропускаем как WARNING/ERROR в зависимости от типа
            try:
                if msg_type in (QtMsgType.QtWarningMsg, QtMsgType.QtInfoMsg):
                    logger.warning("[Qt] %s", msg)
                elif msg_type in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
                    logger.error("[Qt] %s", msg)
                else:
                    logger.info("[Qt] %s", msg)
            except Exception:
                pass

        # Установка глобального обработчика
        try:
            qInstallMessageHandler(_qt_msg_handler)
        except Exception:
            pass

    # === Диагностика: перехват QWidget.show()/setVisible ===
    def _diagnostics_enabled(self) -> bool:
        """Возвращает True, если разрешены тяжёлые диагностические хуки.

        Включается только при DEBUG-логировании или через переменную окружения
        OSTEEN_DIAG_TOPLEVEL=1. В релизе (INFO и выше) — выключено.
        """
        try:
            import os
            if os.environ.get("OSTEEN_DIAG_TOPLEVEL") == "1":
                return True
        except Exception:
            pass
        try:
            import logging as _logging
            return logger.isEnabledFor(_logging.DEBUG)
        except Exception:
            return False

    def _install_widget_show_hooks(self) -> None:
        """Устанавливает перехват QWidget.show/setVisible для выявления топ‑левел маленьких окон.

        Логируем стек Python при показе top-level QWidget с size <= 300x300 или без родителя.
        """
        # Отключаем в релизной сборке — дорого (сбор стеков) и засоряет логи
        if not self._diagnostics_enabled():
            return
        if getattr(QApplication, "_diag_show_hooks_installed", False):
            return

        import traceback

        def _log_widget(w: QWidget, method: str) -> None:
            try:
                parent_none = (w.parent() is None)
            except Exception:
                parent_none = True
            try:
                is_window = bool(w.isWindow())
            except Exception:
                is_window = False
            try:
                sz = w.size()
                w_ = sz.width()
                h_ = sz.height()
            except Exception:
                w_, h_ = -1, -1
            # Логируем любые top-level (без родителя или isWindow), независимо от размера, чтобы поймать стек
            if (parent_none or is_window):
                try:
                    name = w.objectName() or "<noname>"
                except Exception:
                    name = "<noname>"
                try:
                    title = w.windowTitle() or ""
                except Exception:
                    title = ""
                try:
                    flags = w.windowFlags()
                    flags_s = hex(int(flags))
                except Exception:
                    flags_s = "?"
                stack = "\n".join(traceback.format_stack(limit=25))
                logger.info(
                    "DiagTopLevels: QWidget.%s top-level show -> cls=%s name=%s title='%s' size=%sx%s flags=%s\n%s",
                    method, type(w).__name__, name, title, w_, h_, flags_s, stack,
                )

        # Перехват show
        if not hasattr(QWidget, "_orig_show_diag"):
            QWidget._orig_show_diag = QWidget.show  # type: ignore[attr-defined]

            def _diag_show(self: QWidget, *args, **kwargs):
                try:
                    _log_widget(self, "show")
                except Exception:
                    pass
                return QWidget._orig_show_diag(self, *args, **kwargs)  # type: ignore[attr-defined]

            QWidget.show = _diag_show  # type: ignore[assignment]

        # Перехват setVisible(True)
        if not hasattr(QWidget, "_orig_setVisible_diag"):
            QWidget._orig_setVisible_diag = QWidget.setVisible  # type: ignore[attr-defined]

            def _diag_setVisible(self: QWidget, vis: bool):
                try:
                    if bool(vis):
                        _log_widget(self, "setVisible(True)")
                except Exception:
                    pass
                return QWidget._orig_setVisible_diag(self, vis)  # type: ignore[attr-defined]

            QWidget.setVisible = _diag_setVisible  # type: ignore[assignment]

        QApplication._diag_show_hooks_installed = True  # type: ignore[attr-defined]

    def _install_window_resize_logger(self) -> None:
        """Вешает временный eventFilter на главное окно для логирования первых Resize/Move.

        Помогает обнаружить, не показывается ли окно сначала в маленьком размере, а потом расширяется.
        """
        win = getattr(self, "window", None)
        if not isinstance(win, QObject):
            return
        if getattr(win, "_diag_resize_logger_installed", False):
            return

        class _ResizeLogger(QObject):
            def __init__(self, parent=None):
                super().__init__(parent)
                self._resizes = 0
                self._moves = 0
                # Раздельные лимиты для событий; небольшой объём чтобы не шуметь
                try:
                    from app.config_data import app_config as _cfg
                    self._max_resizes = int(getattr(_cfg, "get", lambda *_: 5)("diag.resize_log.max_resizes", 5))
                    self._max_moves = int(getattr(_cfg, "get", lambda *_: 5)("diag.resize_log.max_moves", 5))
                except Exception:
                    self._max_resizes = 5
                    self._max_moves = 5
                # Ссылка на окно для аккуратного снятия фильтра
                self._owner = parent

            def _maybe_uninstall(self, obj):
                try:
                    if self._resizes >= self._max_resizes and self._moves >= self._max_moves:
                        try:
                            obj.removeEventFilter(self)
                        except Exception:
                            pass
                        try:
                            if hasattr(self._owner, "_diag_resize_logger") and getattr(self._owner, "_diag_resize_logger", None) is self:
                                setattr(self._owner, "_diag_resize_logger", None)  # type: ignore[attr-defined]
                                setattr(self._owner, "_diag_resize_logger_installed", False)  # type: ignore[attr-defined]
                        except Exception:
                            pass
                except Exception:
                    pass

            def eventFilter(self, obj, event):
                et = event.type()
                try:
                    if et == QEvent.Type.Resize and self._resizes < self._max_resizes:
                        self._resizes += 1
                        try:
                            sz = getattr(obj, "size", lambda: None)()
                            size_s = f"{sz.width()}x{sz.height()}" if sz is not None else "?"
                        except Exception:
                            size_s = "?"
                        logger.info("DiagTopLevels: Resize #%s -> %s", self._resizes, size_s)
                        self._maybe_uninstall(obj)
                    elif et == QEvent.Type.Move and self._moves < self._max_moves:
                        self._moves += 1
                        try:
                            pos = getattr(obj, "pos", lambda: None)()
                            pos_s = f"({pos.x()},{pos.y()})" if pos is not None else "?"
                        except Exception:
                            pos_s = "?"
                        logger.info("DiagTopLevels: Move #%s -> %s", self._moves, pos_s)
                        self._maybe_uninstall(obj)
                except Exception:
                    pass
                return QObject.eventFilter(self, obj, event)

        rl = _ResizeLogger(win)
        win.installEventFilter(rl)
        # Удерживаем ссылку, чтобы фильтр не был собран GC
        win._diag_resize_logger = rl  # type: ignore[attr-defined]
        win._diag_resize_logger_installed = True  # type: ignore[attr-defined]

    # === Диагностика top-level окон ===
    def _install_top_level_watcher(self) -> None:
        """Устанавливает глобальный eventFilter, который логирует появление top-level окон.

        Логирует события Show/Hide/WindowActivate для всех виджетов; интересуются только isWindow()/parent is None.
        """
        app = QApplication.instance()
        if app is None:
            return

        if getattr(app, "_diag_top_levels_installed", False):
            return

        class _TopLevelWatcher(QObject):
            def eventFilter(self, obj, event):
                try:
                    et = event.type()
                    if et in (QEvent.Type.Show, QEvent.Type.ShowToParent, QEvent.Type.WindowActivate):
                        try:
                            is_window = bool(getattr(obj, "isWindow", lambda: False)())
                        except Exception:
                            is_window = False
                        parent_none = getattr(obj, "parent", lambda: None)() is None
                        # Считаем подозрительным: реальное окно (isWindow) или отсутствие родителя
                        if is_window or parent_none:
                            name = getattr(obj, "objectName", lambda: "")() or "<noname>"
                            cls = type(obj).__name__
                            try:
                                sz = getattr(obj, "size", lambda: None)()
                                w_ = sz.width() if sz is not None else -1
                                h_ = sz.height() if sz is not None else -1
                                size_s = f"{w_}x{h_}" if sz is not None else "?"
                            except Exception:
                                w_, h_, size_s = -1, -1, "?"
                            try:
                                pos = getattr(obj, "pos", lambda: None)()
                                pos_s = f"({pos.x()},{pos.y()})" if pos is not None else "?"
                            except Exception:
                                pos_s = "?"
                            # Логируем как INFO один раз на событие
                            logger.info(
                                "DiagTopLevels: %s event for %s name=%s isWindow=%s parentNone=%s size=%s pos=%s",
                                et.name if hasattr(et, "name") else str(int(et)), cls, name, is_window, parent_none, size_s, pos_s,
                            )

                            # Детальная диагностика маленьких top-level QWidget: дерево детей
                            try:
                                from PyQt6.QtWidgets import QWidget, QLabel
                                if isinstance(obj, QWidget) and (w_ > 0 and h_ > 0 and w_ <= 300 and h_ <= 300):
                                    details: list[str] = []
                                    def _walk(w: QWidget, depth: int = 0):
                                        if depth > 3:
                                            return
                                        try:
                                            cname = type(w).__name__
                                        except Exception:
                                            cname = "<cls?>"
                                        try:
                                            oname = w.objectName() or "<noname>"
                                        except Exception:
                                            oname = "<noname>"
                                        extra = ""
                                        try:
                                            if isinstance(w, QLabel):
                                                txt = w.text()
                                                if txt:
                                                    extra = f" text='{txt[:40]}'"
                                        except Exception:
                                            pass
                                        details.append(f"{'  '*depth}{cname}[{oname}]{extra}")
                                        try:
                                            for ch in w.findChildren(QWidget):
                                                _walk(ch, depth+1)
                                        except Exception:
                                            pass
                                    _walk(obj)
                                    if details:
                                        logger.info("DiagTopLevels: small QWidget children tree:\n%s", "\n".join(details))
                            except Exception:
                                pass
                except Exception:
                    pass
                return QObject.eventFilter(self, obj, event)

        watcher = _TopLevelWatcher(app)
        app.installEventFilter(watcher)
        # Храним ссылку, чтобы не был собран GC
        app._diag_top_levels_watcher = watcher  # type: ignore[attr-defined]
        app._diag_top_levels_installed = True   # type: ignore[attr-defined]

        # Однократный снимок сразу после установки
        self._dump_top_levels("watcher installed")

    def _dump_top_levels(self, tag: str) -> None:
        """Логирует текущее множество top-level виджетов Qt и окон QGuiApplication."""
        app = QApplication.instance()
        if app is None:
            return
        try:
            tops = list(app.topLevelWidgets())
        except Exception:
            tops = []
        info_list: list[str] = []
        for w in tops:
            try:
                name = w.objectName() or "<noname>"
            except Exception:
                name = "<noname>"
            cls = type(w).__name__
            try:
                sz = w.size()
                size_s = f"{sz.width()}x{sz.height()}"
            except Exception:
                size_s = "?"
            try:
                pos = w.pos()
                pos_s = f"({pos.x()},{pos.y()})"
            except Exception:
                pos_s = "?"
            try:
                visible = w.isVisible()
            except Exception:
                visible = False
            # Дополнительная диагностика: title и флаги окна
            try:
                title = getattr(w, "windowTitle", lambda: "")() or ""
            except Exception:
                title = ""
            try:
                flags = getattr(w, "windowFlags", lambda: None)()
                flags_s = hex(int(flags)) if flags is not None else "?"
            except Exception:
                flags_s = "?"
            info_list.append(f"{cls}[{name}] vis={visible} size={size_s} pos={pos_s}")
        logger.info("DiagTopLevels[%s]: %d widgets: %s", tag, len(info_list), "; ".join(info_list))

        # Диагностика окон уровня QWindow (например, всплывающие тултипы/меню могут быть QWindow)
        try:
            from PyQt6.QtGui import QGuiApplication
            wins = list(QGuiApplication.allWindows())
        except Exception:
            wins = []
        win_list: list[str] = []
        for win in wins:
            try:
                cls = type(win).__name__
                title = win.title() if hasattr(win, "title") else ""
                sz = win.size() if hasattr(win, "size") else None
                size_s = f"{sz.width()}x{sz.height()}" if sz is not None else "?"
                pos = win.position() if hasattr(win, "position") else None
                pos_s = f"({pos.x()},{pos.y()})" if pos is not None else "?"
                vis = win.isVisible() if hasattr(win, "isVisible") else False
                flags = win.flags() if hasattr(win, "flags") else None
                flags_s = hex(int(flags)) if flags is not None else "?"
                win_list.append(f"{cls} title='{title}' vis={vis} size={size_s} pos={pos_s} flags={flags_s}")
            except Exception:
                continue
        if win_list:
            logger.info("DiagTopLevels[%s]: QWindows(%d): %s", tag, len(win_list), "; ".join(win_list))

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
