# app/views/main_components/window_initializer.py
"""Инициализатор главного окна.

УЛУЧШЕНИЕ: Использует Protocol для типизации, ResourceManager для управления
ресурсами и константы вместо магических значений.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Callable, Dict, List, Tuple, TypeAlias

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.controllers.system.window_controllers_setup import WindowControllersSetup
from app.utils.metrics.startup_metrics import get_metrics
from app.utils.ui.updates import suspend_updates

from .constants import StatusMessage, Timeout
from .init_db_gate import DbReadyGate
from .init_diagnostics import DiagnosticsInstaller
from .init_scheduler import AsyncStepRunner
from .init_status import StatusUpdater
from .init_steps_config import AFTER_DB_STEP_CONFIG, BEFORE_DB_STEP_CONFIG
from .protocols import (
    DatabaseProtocol,
    MainWindowProtocol,
    SettingsProtocol,
    ThemeControllerProtocol,
)
from .resource_manager import ResourceManager
from .window_ui_setup import WindowUISetup

logger = logging.getLogger(__name__)

# Type aliases
Step: TypeAlias = tuple[str, Callable[[], None]]


class WindowInitializer:
    """Инициализатор главного окна.
    
    УЛУЧШЕНИЕ: Использует строгие Protocol для всех зависимостей
    и ResourceManager для гарантированной очистки ресурсов.
    """

    # --- Строгая типизация через Protocol ---
    window: MainWindowProtocol
    db: DatabaseProtocol
    settings: SettingsProtocol
    theme_ctrl: ThemeControllerProtocol

    ui_setup: WindowUISetup
    controllers_setup: WindowControllersSetup
    _metrics: object  # Из startup_metrics
    _status: StatusUpdater
    _resource_manager: ResourceManager

    _current_init_step: int
    _current_db_step: int
    _init_steps_before_db: list[Step]
    _init_steps_after_db: list[Step]
    _special_hooks_after: dict[Callable[[], None], Callable[[], None]]
    _db_ready: bool
    _waiting_for_db: bool

    def __init__(
        self,
        main_window: MainWindowProtocol,
        db: DatabaseProtocol,
        settings: SettingsProtocol,
        theme_ctrl: ThemeControllerProtocol,
    ) -> None:
        """Инициализация компонента.

        УЛУЧШЕНИЕ: Все параметры теперь используют Protocol для строгой типизации.

        Args:
            main_window: Главное окно приложения (MainWindowProtocol)
            db: База данных (DatabaseProtocol)
            settings: Настройки приложения (SettingsProtocol)
            theme_ctrl: Контроллер тем (ThemeControllerProtocol)
        """
        self.window = main_window
        self.db = db
        self.settings = settings
        self.theme_ctrl = theme_ctrl

        # УЛУЧШЕНИЕ: Инициализируем ResourceManager для управления ресурсами
        self._resource_manager = ResourceManager("WindowInitializer")

        # Композиция компонентов
        self.ui_setup = WindowUISetup(self)
        self.controllers_setup = WindowControllersSetup(self)
        self._metrics = get_metrics()
        self._status = StatusUpdater(self.window, logger)

        # --- Инициализация ранее динамических атрибутов ---
        # Индексы прогресса этапов
        self._current_init_step: int = 0
        self._current_db_step: int = 0
        # Наборы шагов и специальные хуки (заполняются при планировании)
        self._init_steps_before_db: list[Step] = []
        self._init_steps_after_db: list[Step] = []
        self._special_hooks_after: dict[Callable[[], None], Callable[[], None]] = {}
        # Состояния ожидания БД
        self._db_ready: bool = False
        self._waiting_for_db: bool = False

    def initialize_window(self) -> None:
        """Выполняет полную инициализацию главного окна пошагово."""
        self._metrics.reset()
        self._install_diagnostics()
        self._run_light_steps()
        self._schedule_heavy_steps()

    # === Оркестровка этапов инициализации (выделено из initialize_window) ===
    def _install_diagnostics(self) -> None:
        """Устанавливает диагностические фильтры и хуки (qt message filter, top-level watcher и т.п.)."""
        try:
            DiagnosticsInstaller(self.window, self._dump_top_levels).install_all()
        except (RuntimeError, AttributeError, ImportError) as e:
            # Диагностика не критична для работы приложения — логируем предупреждение и продолжаем
            logger.warning(
                "Diagnostics: failed to install one or more handlers: %s",
                e,
                exc_info=True,
            )

    def _run_light_steps(self) -> None:
        """Выполняет лёгкие синхронные шаги и подключает сигналы (без показа окна)."""
        light_steps = (
            self._init_window_properties,
            self._init_basic_attributes,
            self._init_menu,
            self._init_central_widget,
            self._capture_main_layout,
            self._init_top_panel,
            self._connect_db_signals,  # Подключаем сигналы БД к UI
        )

        with suspend_updates(self.window):
            for step in light_steps:
                with self._metrics.time_span(f"light:{step.__name__}"):
                    step()

        try:
            if hasattr(self.window, "shown"):
                self.window.shown.connect(self._on_window_shown)
        except (RuntimeError, AttributeError, TypeError):
            logger.exception(
                "WindowInitializer: не удалось подключить слот к сигналу 'shown'"
            )

        # Ранний показ окна: повышает отзывчивость UI, тяжёлые шаги выполнятся асинхронно
        try:
            if hasattr(self.window, "show"):
                # Показываем только если окно ещё не видно
                is_visible = False
                try:
                    is_visible = bool(getattr(self.window, "isVisible", lambda: False)())
                except Exception:
                    is_visible = False
                if not is_visible:
                    self.window.show()
        except Exception:
            logger.exception(
                "WindowInitializer: ранний показ окна после лёгких шагов не удался"
            )


    def _schedule_heavy_steps(self) -> None:
        """Разбивает тяжёлые шаги на асинхронные этапы и планирует их выполнение с ожиданием БД."""
        self._current_init_step = 0
        self._init_steps_before_db: List[Tuple[str, Callable[[], None]]] = []
        special_hooks_before: Dict[Callable[[], None], Callable[[], None]] = {}
        for label, method_name, hook_name in BEFORE_DB_STEP_CONFIG:
            step_func = getattr(self, method_name)
            self._init_steps_before_db.append((label, step_func))
            if hook_name:
                special_hooks_before[step_func] = getattr(self, hook_name)

        self._init_steps_after_db: List[Tuple[str, Callable[[], None]]] = []
        self._special_hooks_after: Dict[Callable[[], None], Callable[[], None]] = {}
        for label, method_name, hook_name in AFTER_DB_STEP_CONFIG:
            step_func = getattr(self, method_name)
            self._init_steps_after_db.append((label, step_func))
            if hook_name:
                self._special_hooks_after[step_func] = getattr(self, hook_name)
        self._db_ready = False
        self._waiting_for_db = False
        runner = AsyncStepRunner(self._metrics, self._status.set_message)
        on_error = self._on_init_error
        runner.run(
            steps=self._init_steps_before_db,
            index_getter=lambda: getattr(self, "_current_init_step", 0),
            index_setter=lambda v: setattr(self, "_current_init_step", v),
            on_completed=self._on_before_db_steps_completed,
            on_error=on_error,
            special_hooks=special_hooks_before,
        )

    def _init_window_properties(self) -> None:
        self.ui_setup.setup_window_properties()

    def _init_basic_attributes(self) -> None:
        self.ui_setup.setup_basic_attributes()

    def _init_menu(self) -> None:
        self.ui_setup.setup_menu()

    def _init_central_widget(self) -> None:
        self.ui_setup.setup_central_widget()

    def _capture_main_layout(self) -> None:
        self.main_layout = self.ui_setup.main_layout

    def _init_top_panel(self) -> None:
        self.ui_setup.setup_top_panel()

    def _connect_db_signals(self) -> None:
        """Подключает Qt сигналы Database к UI компонентам.
        
        УВЕДОМЛЯЕТ UI об изменениях в базе данных без polling.
        """
        try:
            # Проверяем, что у db есть сигналы (QObject)
            if not hasattr(self.db, 'data_changed'):
                logger.debug("Database doesn't have Qt signals, skipping signal connection")
                return
            
            # Подключаем сигнал изменения данных
            self.db.data_changed.connect(self._on_db_data_changed)
            
            # Подключаем сигнал загрузки структуры
            if hasattr(self.db, 'structure_loaded'):
                self.db.structure_loaded.connect(self._on_db_structure_loaded)
            
            # Подключаем сигнал создания бэкапа
            if hasattr(self.db, 'backup_created'):
                self.db.backup_created.connect(self._on_db_backup_created)
            
            # Подключаем сигнал ошибок
            if hasattr(self.db, 'error_occurred'):
                self.db.error_occurred.connect(self._on_db_error)
            
            logger.debug("Database signals connected successfully")
        except Exception as e:
            logger.warning(
                "Failed to connect database signals: %s",
                e,
                exc_info=True
            )
    
    def _on_db_data_changed(self, table_name: str, operation: str, affected_ids: list) -> None:
        """Обработчик изменения данных в БД."""
        try:
            logger.debug(f"DB data changed: {table_name}, {operation}, ids={affected_ids}")
            
            # Если изменились ссылки - обновляем таблицу
            if table_name == "link":
                # Таблица ссылок обновится через structure_business
                if hasattr(self.window, 'reload_current_category'):
                    self.window.reload_current_category()
            
            # Если изменилась структура - обновляем дерево
            elif table_name in ("sphere", "section", "category"):
                if hasattr(self.window, 'reload_structure'):
                    self.window.reload_structure()
        except Exception as e:
            logger.warning(
                "Error handling DB data change: %s",
                e,
                exc_info=True
            )
    
    def _on_db_structure_loaded(self) -> None:
        """Обработчик загрузки структуры."""
        try:
            logger.info("Database structure loaded - reloading UI")
            if hasattr(self.window, 'reload_structure'):
                self.window.reload_structure()
        except Exception as e:
            logger.warning(
                "Error handling structure loaded: %s",
                e,
                exc_info=True
            )
    
    def _on_db_backup_created(self, backup_path: str) -> None:
        """Обработчик создания резервной копии."""
        try:
            logger.info(f"Backup created: {backup_path}")
            # Показываем уведомление в статус-баре
            if hasattr(self.window, 'statusBar'):
                status_bar = self.window.statusBar()
                if status_bar:
                    status_bar.showMessage(f"Резервная копия создана: {backup_path}", 5000)
        except Exception as e:
            logger.warning(
                "Error handling backup created: %s",
                e,
                exc_info=True
            )
    
    def _on_db_error(self, title: str, message: str) -> None:
        """Обработчик ошибок БД."""
        try:
            logger.error(f"Database error: {title} - {message}")
            # Показываем диалог ошибки
            QMessageBox.critical(self.window, title, message)
        except Exception as e:
            logger.warning(
                "Error handling DB error signal: %s",
                e,
                exc_info=True
            )

    def _init_main_content(self) -> None:
        self.ui_setup.setup_main_content()

    def _init_bottom_panel(self) -> None:
        self.ui_setup.setup_bottom_panel()

    def _init_status_bar(self) -> None:
        self.ui_setup.setup_status_bar()

    def _init_controllers(self) -> None:
        self.controllers_setup.setup_controllers()

    def _apply_user_font_size(self) -> None:
        if hasattr(self.settings, "get_font_size") and hasattr(
            self.window, "apply_font_size_to_content"
        ):
            fs = self.settings.get_font_size()
            try:
                with suppress(AttributeError, ValueError, TypeError):
                    if fs:
                        self.window.apply_font_size_to_content(int(fs))
            except Exception:
                logger.exception(
                    "WindowInitializer: unexpected error applying font size"
                )

    def _initialize_spheres(self) -> None:
        self.controllers_setup.initialize_spheres()

    def _post_status_bar_init(self) -> None:
        try:
            # Не изменяем текст статус-бара на этапе инициализации
            pass
        except Exception:
            logger.exception(
                "WindowInitializer: ошибка обновления текста статус-бара после инициализации"
            )

    def _post_controllers_init(self) -> None:
        try:
            sb = getattr(self.window, "structure_business", None)
            ao = getattr(sb, "async_operations", None) if sb else None
            if ao is not None:
                curr_id = getattr(sb, "current_sphere_id", None)
                if isinstance(curr_id, int) and curr_id > 0:
                    self._metrics.start("async:structure_load")
                    try:
                        if hasattr(sb, "structure_loaded"):

                            def _on_structure_loaded_once(*_args):
                                try:
                                    self._metrics.stop("async:structure_load")
                                except Exception:
                                    logger.debug(
                                        "WindowInitializer: failed to stop 'async:structure_load' metric",
                                        exc_info=False,
                                    )
                                try:
                                    sb.structure_loaded.disconnect(
                                        _on_structure_loaded_once
                                    )
                                except Exception:
                                    logger.debug(
                                        "WindowInitializer: failed to disconnect temporary structure_loaded slot",
                                        exc_info=False,
                                    )

                            sb.structure_loaded.connect(_on_structure_loaded_once)
                    except Exception:
                        logger.debug(
                            "WindowInitializer: failed to wire metrics to structure_loaded",
                            exc_info=False,
                        )
                    try:
                        # Запускаем сразу, без лишнего тика event loop, чтобы быстрее показать дерево
                        ao.load_structure_async(int(curr_id))
                        self._metrics.mark("async:load_structure_async started")
                    except Exception:
                        logger.exception(
                            "WindowInitializer: failed to start load_structure_async immediately"
                        )
        except Exception:
            logger.exception(
                "WindowInitializer: не удалось запланировать load_structure_async"
            )

    def _execute_db_dependent_steps(self) -> None:
        self._current_db_step = 0
        runner = AsyncStepRunner(self._metrics, self._status.set_message)
        on_error = self._on_init_error
        runner.run(
            steps=self._init_steps_after_db,
            index_getter=lambda: getattr(self, "_current_db_step", 0),
            index_setter=lambda v: setattr(self, "_current_db_step", v),
            on_completed=self._finalize_initialization,
            on_error=on_error,
            special_hooks=self._special_hooks_after,
        )

    def _finalize_initialization(self) -> None:
        """Завершает асинхронную инициализацию и показывает полностью собранное окно."""
        # Сводка метрик старта в лог (ошибки здесь не критичны)
        try:
            self._metrics.flush_log(logger)
        except Exception:
            logger.debug("WindowInitializer: failed to flush startup metrics at finalize", exc_info=True)

        # Обновляем статус на "Готово" (к этому моменту статус-бар создан)
        self._status.set_message(StatusMessage.READY)

        logger.info(
            "WindowInitializer: асинхронная инициализация завершена успешно"
        )

        # Диагностика перед показом окна
        try:
            self._dump_top_levels("before final window.show")
        except Exception:
            logger.debug("DiagTopLevels: failed to dump before final show", exc_info=False)

        # Покажем окно только если оно ещё не было показано ранним шагом
        try:
            if hasattr(self.window, "show"):
                need_show = True
                try:
                    need_show = not bool(getattr(self.window, "isVisible", lambda: False)())
                except Exception:
                    need_show = True
                if need_show:
                    with self._metrics.time_span("final:window_show"):
                        self.window.show()
        except Exception as e:
            logger.exception(
                "WindowInitializer: не удалось показать окно в финале инициализации"
            )
            # Делегируем централизованному обработчику ошибок
            self._on_init_error(e)
            return

        # Пост-диагностика после показа окна
        try:
            self._dump_top_levels("after final window.show")
            QTimer.singleShot(10, lambda: self._dump_top_levels("+10ms after final show"))
            QTimer.singleShot(100, lambda: self._dump_top_levels("+100ms after final show"))
            # Диагностика шрифта шапки таблицы после полной сборки UI
            try:
                tc = getattr(self, "theme_ctrl", None)
                if tc and hasattr(tc, "_log_tables_header_font"):
                    # вызвать сразу и повторно через 50 мс на случай отложенного создания таблицы
                    QTimer.singleShot(0, lambda: tc._log_tables_header_font(self.window))
                    QTimer.singleShot(50, lambda: tc._log_tables_header_font(self.window))
            except Exception:
                logger.debug("WindowInitializer: header font diagnostics scheduling failed", exc_info=True)
        except Exception:
            logger.debug("DiagTopLevels: failed post-show dumps (final)", exc_info=False)

    def _on_init_error(self, exc: Exception) -> None:
        """Единая обработка ошибок этапов инициализации.

        Выполняет сброс и логирование метрик старта, затем делегирует стандартному
        обработчику ошибок отложенной инициализации.
        """
        try:
            self._metrics.flush_log(logger)
        except Exception:
            logger.exception("WindowInitializer: failed to flush startup metrics")
        self._handle_deferred_init_error(exc)

    def _on_before_db_steps_completed(self) -> None:
        """Коллбек завершения этапов до БД. Либо ждёт готовности БД, либо продолжает к этапам после БД."""
        # Используем ворота готовности БД
        gate = DbReadyGate(self.window, logger)
        gate.ensure_ready_or_wait(
            on_ready=self._execute_db_dependent_steps,
            on_waiting=self._on_waiting_for_db,
        )

    def _on_waiting_for_db(self) -> None:
        """Вызывается, когда БД ещё не готова: выставляет флаг ожидания и обновляет статус."""
        try:
            setattr(self, "_waiting_for_db", True)
            self._status.set_message(StatusMessage.WAITING_FOR_DB)
        except Exception:
            logger.exception(
                "WindowInitializer: failed to update waiting-for-DB status"
            )

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
        logger.info(
            "DiagTopLevels[%s]: %d widgets: %s",
            tag,
            len(info_list),
            "; ".join(info_list),
        )

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
                win_list.append(
                    f"{cls} title='{title}' vis={vis} size={size_s} pos={pos_s} flags={flags_s}"
                )
            except Exception:
                continue
        if win_list:
            logger.info(
                "DiagTopLevels[%s]: QWindows(%d): %s",
                tag,
                len(win_list),
                "; ".join(win_list),
            )

    # === Слоты ===
    def _on_window_shown(self) -> None:
        """Обновляем статус после показа окна.

        Учтено, что статус-бар создаётся отложенно: слот безопасно проверяет наличие
        необходимых элементов перед обновлением текста.
        """
        try:
            # Не навязываем сообщение в статус-баре при показе окна
            pass
        except Exception:
            logger.exception(
                "WindowInitializer: ошибка обновления текста статус-бара в _on_window_shown"
            )

    # === Обработчики ошибок ===
    def _handle_deferred_init_error(self, exc: Exception) -> None:
        """Показывает диалог ошибки и завершает приложение при сбое отложенной инициализации."""
        try:
            parent = self.window if hasattr(self.window, "isVisible") else None
            QMessageBox.critical(
                parent,
                "Ошибка инициализации",
                f"Произошла ошибка при инициализации UI:\n{exc}",
            )
        except Exception:
            logger.exception(
                "WindowInitializer: не удалось показать диалог ошибки инициализации"
            )
        finally:
            try:
                # Централизуем завершение: закрываем главное окно, чтобы сработал AppShutdownController
                if hasattr(self, "window") and hasattr(self.window, "close"):
                    self.window.close()
                    return
            except Exception:
                logger.debug("WindowInitializer: window.close() failed, falling back to app.quit()", exc_info=True)

            # Fallback: если окна нет, завершаем приложение напрямую
            app = QApplication.instance()
            if app is not None:
                app.quit()
