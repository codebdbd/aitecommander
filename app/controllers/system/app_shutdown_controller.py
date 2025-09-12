# app/controllers/app_shutdown_controller.py

import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from enum import Enum
from typing import Any, Callable, Dict, List

from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import QApplication

from app.config_data import app_config

# Модульный логгер
logger = logging.getLogger(__name__)

# Политика завершения приложения:
# - UI-слой НЕ вызывает напрямую quit()/exit().
# - Завершение производится ТОЛЬКО через AppShutdownController (perform_shutdown)
#   либо косвенно через закрытие главного окна (MainWindow.close()), что триггерит контроллер.
# - Функция emergency_shutdown() — исключительно для фатальных аварийных ситуаций.


class ShutdownPriority(Enum):
    """Приоритеты выполнения операций shutdown."""

    CRITICAL = 1  # Сохранение данных, критичные операции
    HIGH = 2  # Остановка контроллеров
    NORMAL = 3  # Ожидание потоков
    LOW = 4  # Cleanup, бэкапы


class ShutdownTimeoutError(Exception):
    """Исключение для таймаутов shutdown операций."""

    pass


class ShutdownHandler:
    """Обертка для операций shutdown с метаданными."""

    def __init__(
        self,
        name: str,
        handler: Callable,
        priority: ShutdownPriority,
        timeout: int = None,
        critical: bool = False,
    ):
        self.name = name
        self.handler = handler
        self.priority = priority
        self.timeout = timeout or app_config.get("shutdown.default_timeout", 2000)
        self.critical = critical  # Если True, ошибка прервет shutdown


class AppShutdownController:
    """Улучшенный контроллер корректного завершения приложения.

    Особенности:
    - Поддержка приоритетов операций
    - Улучшенная обработка ошибок с реальными таймаутами
    - Конфигурируемые таймауты
    - Полная обратная совместимость с существующим кодом
    - Безопасное завершение в многопоточной среде
    """

    def __init__(self, main_window):
        self.window = main_window
        self.shutdown_handlers: List[ShutdownHandler] = []
        self.shutdown_in_progress = False
        self._shutdown_lock = threading.RLock()
        self._shutdown_started_ts: float | None = None
        self._register_default_handlers()

        # Настройки из конфигурации
        self.max_shutdown_time = app_config.get("shutdown.max_total_time", 10000)
        self.parallel_execution = app_config.get("shutdown.parallel_execution", False)

    def perform_shutdown(self, event):
        """Основной метод - полностью совместим с оригинальным интерфейсом."""
        with self._shutdown_lock:
            if self.shutdown_in_progress:
                logger.warning(
                    "Shutdown already in progress, ignoring duplicate request"
                )
                return

            self.shutdown_in_progress = True
            self._shutdown_started_ts = time.monotonic()

        try:
            logger.info("Starting application shutdown sequence")
            self._execute_shutdown_sequence()
            logger.info("Application shutdown completed successfully")

        except Exception as exc:
            logger.error("Critical error during shutdown: %s", exc, exc_info=True)
        finally:
            # Безопасный вызов родительского closeEvent (обратная совместимость)
            self._safe_close_event(event)

    def _safe_close_event(self, event):
        """Безопасный вызов родительского closeEvent с fallback."""
        try:
            # Пытаемся найти родительский класс с closeEvent
            for base_class in self.window.__class__.__mro__[1:]:
                if hasattr(base_class, "closeEvent"):
                    base_class.closeEvent(self.window, event)
                    return

            # Если не нашли, просто принимаем событие
            event.accept()

        except Exception as exc:
            logger.error("Error in base closeEvent: %s", exc, exc_info=True)
            # В любом случае принимаем событие, чтобы приложение могло закрыться
            try:
                event.accept()
            except Exception:
                pass

    def _execute_shutdown_sequence(self):
        """Выполнить последовательность операций shutdown по приоритетам с учетом общего дедлайна."""
        handlers_by_priority = self._group_handlers_by_priority()

        for priority in ShutdownPriority:
            if priority not in handlers_by_priority:
                continue

            # Проверка общего дедлайна перед уровнем приоритета
            remaining = self._remaining_time_ms()
            if remaining is not None and remaining <= 0:
                logger.error(
                    "Global shutdown deadline exceeded before priority %s",
                    priority.name,
                )
                break

            handlers = handlers_by_priority[priority]
            logger.debug(
                "Executing shutdown priority %s with %s handlers (remaining ~%s ms)",
                priority.name,
                len(handlers),
                remaining,
            )

            try:
                if (
                    self.parallel_execution
                    and len(handlers) > 1
                    and priority != ShutdownPriority.CRITICAL
                ):
                    self._execute_handlers_parallel(handlers, remaining_ms=remaining)
                else:
                    self._execute_handlers_sequential(handlers, remaining_ms=remaining)
            except Exception as exc:
                logger.error(
                    "Error in priority %s: %s", priority.name, exc, exc_info=True
                )
                if priority == ShutdownPriority.CRITICAL:
                    raise

    def _group_handlers_by_priority(
        self,
    ) -> Dict[ShutdownPriority, List[ShutdownHandler]]:
        """Группировка handlers по приоритетам."""
        groups = {}
        for handler in self.shutdown_handlers:
            if handler.priority not in groups:
                groups[handler.priority] = []
            groups[handler.priority].append(handler)
        return groups

    def _execute_handlers_sequential(
        self, handlers: List[ShutdownHandler], remaining_ms: int | None = None
    ):
        """Последовательное выполнение handlers с учетом общего дедлайна."""
        for handler in handlers:
            rem = self._remaining_time_ms() if remaining_ms is None else remaining_ms
            if rem is not None and rem <= 0:
                logger.error(
                    "Global shutdown deadline exceeded during sequential handlers"
                )
                break
            eff_timeout = (
                min(handler.timeout, rem) if rem is not None else handler.timeout
            )
            self._execute_single_handler(handler, override_timeout_ms=eff_timeout)

    def _execute_handlers_parallel(
        self, handlers: List[ShutdownHandler], remaining_ms: int | None = None
    ):
        """Параллельное выполнение handlers (для некритичных операций) с учетом общего дедлайна."""
        max_workers = min(len(handlers), 4)
        # Эффективный таймаут — минимум из максимального таймаута handlers и оставшегося времени
        max_handler_timeout = max(h.timeout for h in handlers) if handlers else 0
        eff_ms = (
            min(max_handler_timeout + 1000, remaining_ms)
            if remaining_ms is not None
            else (max_handler_timeout + 1000)
        )
        timeout_seconds = (eff_ms / 1000.0) if eff_ms is not None else None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_handler = {
                executor.submit(
                    self._execute_single_handler,
                    handler,
                    min(handler.timeout, remaining_ms)
                    if remaining_ms is not None
                    else handler.timeout,
                ): handler
                for handler in handlers
            }

            try:
                # Если timeout_seconds None, ждем без таймаута
                iterator = (
                    as_completed(future_to_handler, timeout=timeout_seconds)
                    if timeout_seconds is not None
                    else as_completed(future_to_handler)
                )
                for future in iterator:
                    handler = future_to_handler[future]
                    try:
                        future.result()
                    except Exception as exc:
                        error_msg = f"Parallel handler {handler.name} failed: {exc}"
                        if handler.critical:
                            logger.critical(error_msg, exc_info=True)
                            raise
                        else:
                            logger.error(error_msg, exc_info=True)

            except FutureTimeoutError:
                logger.error("Timeout waiting for parallel handlers completion")
                for future in future_to_handler:
                    if not future.done():
                        future.cancel()

    @contextmanager
    def _timeout_context(self, timeout_ms: int, handler_name: str):
        """Контекстный менеджер для установки таймаута операции."""
        timeout_seconds = timeout_ms / 1000.0
        timer = None
        timeout_occurred = False

        def timeout_handler():
            nonlocal timeout_occurred
            timeout_occurred = True

        # Используем threading.Timer вместо signal (совместимость с Windows и PyQt)
        timer = threading.Timer(timeout_seconds, timeout_handler)
        timer.start()

        try:
            yield
            if timeout_occurred:
                raise ShutdownTimeoutError(
                    f"Handler '{handler_name}' timed out after {timeout_seconds}s"
                )
        finally:
            if timer:
                timer.cancel()

    def _execute_single_handler(
        self, handler: ShutdownHandler, override_timeout_ms: int | None = None
    ):
        """Выполнение одного handler с реальным таймаутом и расширенным логированием.

        Исполняем обработчик в отдельном потоке и ждём завершения через Future.result(timeout).
        В случае таймаута — логируем, пытаемся отменить и продолжаем (или прерываем для critical).
        """
        from concurrent.futures import ThreadPoolExecutor
        from concurrent.futures import TimeoutError as _FTimeout

        eff_timeout_ms = (
            override_timeout_ms if override_timeout_ms is not None else handler.timeout
        )
        eff_timeout_sec = max(0.001, float(eff_timeout_ms) / 1000.0) if eff_timeout_ms else None

        logger.debug(
            "Executing shutdown handler: %s (timeout=%sms, critical=%s)",
            handler.name,
            eff_timeout_ms,
            handler.critical,
        )

        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(handler.handler)
                try:
                    fut.result(timeout=eff_timeout_sec)
                    logger.debug("Handler %s completed successfully", handler.name)
                    return
                except _FTimeout:
                    # Пытаемся отменить, если ещё не начался
                    try:
                        fut.cancel()
                    except Exception:
                        pass
                    msg = (
                        f"Handler '{handler.name}' timed out after {eff_timeout_sec:.3f}s"
                    )
                    if handler.critical:
                        logger.critical(msg)
                        raise ShutdownTimeoutError(msg)
                    else:
                        logger.error(msg)
                        return
                except Exception as exc:
                    if handler.critical:
                        logger.critical(
                            "Handler '%s' failed: %s", handler.name, exc, exc_info=True
                        )
                        raise
                    else:
                        logger.error(
                            "Handler '%s' failed: %s", handler.name, exc, exc_info=True
                        )
                        return
        except ShutdownTimeoutError:
            # Уже залогировано выше, пробрасываем дальше для критичных кейсов
            raise
        except Exception as exc:
            # Непредвиденные ошибки инфраструктуры исполнения
            if handler.critical:
                logger.critical(
                    "Execution infrastructure failed for handler '%s': %s",
                    handler.name,
                    exc,
                    exc_info=True,
                )
                raise
            else:
                logger.error(
                    "Execution infrastructure failed for handler '%s': %s",
                    handler.name,
                    exc,
                    exc_info=True,
                )
                return

    def _register_default_handlers(self):
        """Регистрация стандартных handlers (совместимость с оригинальным кодом)."""
        # Порядок как раньше: controllers -> wait threads -> backup
        # 1) Остановка контроллеров (строгий, критичный)
        self.add_shutdown_handler(
            "controllers_shutdown",
            self._shutdown_controllers,
            ShutdownPriority.HIGH,
            timeout=3000,
            critical=True,
        )
        # 2) Ожидание пулов потоков (строгий, критичный)
        # Согласуем таймаут обработчика с конфигом ui.thread_pool_shutdown_timeout, добавив буфер
        tp_timeout = app_config.ui.get_thread_pool_shutdown_timeout()
        handler_timeout = max(
            tp_timeout + 1000, 3000
        )  # небольшой буфер во избежание ложных таймаутов
        self.add_shutdown_handler(
            "thread_pools_wait",
            self._wait_for_thread_pools,
            ShutdownPriority.NORMAL,
            timeout=handler_timeout,
            critical=True,
        )
        # 3) Бэкап базы (некритичный, последний)
        self.add_shutdown_handler(
            "database_backup",
            self._backup_database,
            ShutdownPriority.LOW,
            timeout=5000,
            critical=False,
        )

    def _remaining_time_ms(self) -> int | None:
        """Сколько миллисекунд осталось до общего дедлайна. None — если дедлайн не настроен."""
        if not self.max_shutdown_time:
            return None
        if self._shutdown_started_ts is None:
            return self.max_shutdown_time
        elapsed_ms = int((time.monotonic() - self._shutdown_started_ts) * 1000)
        remaining = self.max_shutdown_time - elapsed_ms
        return max(0, remaining)

    def add_shutdown_handler(
        self,
        name: str,
        handler: Callable,
        priority: ShutdownPriority = ShutdownPriority.NORMAL,
        timeout: int = None,
        critical: bool = False,
    ):
        """Добавить пользовательский shutdown handler."""
        # Проверяем, нет ли уже handler'а с таким именем
        self.remove_shutdown_handler(name)

        shutdown_handler = ShutdownHandler(name, handler, priority, timeout, critical)
        self.shutdown_handlers.append(shutdown_handler)
        logger.debug(
            "Registered shutdown handler: %s (priority: %s)", name, priority.name
        )

    def remove_shutdown_handler(self, name: str) -> bool:
        """Удалить shutdown handler по имени. Возвращает True, если handler был найден и удален."""
        initial_count = len(self.shutdown_handlers)
        self.shutdown_handlers = [h for h in self.shutdown_handlers if h.name != name]
        removed = len(self.shutdown_handlers) < initial_count
        if removed:
            logger.debug("Removed shutdown handler: %s", name)
        return removed

    def get_shutdown_handlers(self) -> List[Dict[str, Any]]:
        """Получить информацию о всех зарегистрированных handlers (для отладки)."""
        return [
            {
                "name": h.name,
                "priority": h.priority.name,
                "timeout": h.timeout,
                "critical": h.critical,
            }
            for h in self.shutdown_handlers
        ]

    # =================== ОРИГИНАЛЬНЫЕ МЕТОДЫ (рефакторинг) ===================

    def _shutdown_controllers(self):
        """Остановить фоновые контроллеры - улучшенная версия оригинала."""
        controllers_to_shutdown = [
            ("links", "Links controller"),
            ("links_business", "Links business controller"),
            ("tiles", "Tiles controller"),
        ]

        for attr_name, display_name in controllers_to_shutdown:
            try:
                if not hasattr(self.window, attr_name):
                    logger.debug("%s not found on window object", display_name)
                    continue

                controller = getattr(self.window, attr_name)
                if controller is None:
                    logger.debug("%s is None", display_name)
                    continue

                if not hasattr(controller, "shutdown"):
                    logger.debug("%s has no shutdown method", display_name)
                    continue

                logger.debug("Shutting down %s", display_name)
                shutdown_method = getattr(controller, "shutdown")
                if callable(shutdown_method):
                    shutdown_method()
                else:
                    logger.warning("%s.shutdown is not callable", display_name)

            except Exception as exc:
                logger.error(
                    "Error shutting down %s: %s", display_name, exc, exc_info=True
                )

    def _wait_for_thread_pools(self):
        """Ожидание завершения потоков - улучшенная версия оригинала."""
        timeout = app_config.ui.get_thread_pool_shutdown_timeout()

        # Глобальный thread pool
        try:
            pool = QThreadPool.globalInstance()
            if pool and pool.activeThreadCount() > 0:
                logger.debug(
                    "Waiting for %s global threads to finish",
                    pool.activeThreadCount(),
                )
                if not pool.waitForDone(timeout):
                    logger.warning(
                        "Global thread pool did not finish within timeout, forcing cleanup"
                    )
                    # Пытаемся форсированно завершить
                    try:
                        pool.clear()
                    except Exception as clear_exc:
                        logger.error("Error clearing global thread pool: %s", clear_exc)
        except Exception as exc:
            logger.error("Error waiting for global thread pool: %s", exc, exc_info=True)

        # Локальный thread pool окна
        try:
            if hasattr(self.window, "thread_pool"):
                local_pool = getattr(self.window, "thread_pool")
                if local_pool and local_pool.activeThreadCount() > 0:
                    logger.debug(
                        "Waiting for %s local threads to finish",
                        local_pool.activeThreadCount(),
                    )
                    if not local_pool.waitForDone(timeout):
                        logger.warning(
                            "Local thread pool did not finish within timeout, forcing cleanup"
                        )
                        try:
                            local_pool.clear()
                        except Exception as clear_exc:
                            logger.error(
                                "Error clearing local thread pool: %s",
                                clear_exc,
                            )
        except Exception as exc:
            logger.error("Error waiting for local thread pool: %s", exc, exc_info=True)

    def _backup_database(self):
        """Создание бэкапа БД - улучшенная версия оригинала."""
        try:
            if not hasattr(self.window, "db"):
                logger.debug("No 'db' attribute found on window, skipping backup")
                return

            db = getattr(self.window, "db")
            if db is None:
                logger.debug("Database instance is None, skipping backup")
                return

            if not hasattr(db, "backup"):
                logger.debug("Database has no backup method")
                return

            backup_method = getattr(db, "backup")
            if not callable(backup_method):
                logger.debug("Database backup attribute is not callable")
                return

            logger.info("Creating database backup...")
            backup_method()
            logger.info("Database backup completed successfully")

        except Exception as exc:
            # Для бэкапа ошибка не критична, но логируем
            logger.error("Database backup failed: %s", exc, exc_info=True)


# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================


def create_shutdown_controller(main_window) -> AppShutdownController:
    """Фабричная функция для создания контроллера с настройками по умолчанию."""
    controller = AppShutdownController(main_window)

    # Дополнительные handlers можно добавить здесь
    # controller.add_shutdown_handler("custom_cleanup", custom_cleanup_function, ShutdownPriority.LOW)

    return controller


def emergency_shutdown():
    """Экстренное завершение приложения в случае критических ошибок."""
    logger.critical("Emergency shutdown initiated")
    try:
        app = QApplication.instance()
        if app:
            app.quit()
        else:
            sys.exit(1)
    except Exception as exc:
        logger.critical("Error during emergency shutdown: %s", exc)
        sys.exit(1)
