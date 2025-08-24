"""
Утилиты синхронизации для безопасного многопоточного выполнения.

Этот модуль объединяет функциональность блокировок и защиты от циклических сигналов:
- Базовые и улучшенные блокировки с таймаутами и мониторингом
- Менеджер блокировок с защитой от deadlock
- Защита от циклических вызовов сигналов/слотов в PyQt6 приложениях
"""

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from threading import Lock, RLock
from typing import Callable, Dict, Optional, Set

logger = logging.getLogger(__name__)


# ====================
# Блокировки (Locks)
# ====================


class LockType(Enum):
    """Типы блокировок для упорядоченного захвата."""

    DATABASE = "database"
    TASKS = "tasks"
    UI_STATE = "ui_state"


class LockTimeout(Exception):
    """Исключение при превышении таймаута блокировки."""

    pass


class DeadlockDetected(Exception):
    """Исключение при обнаружении потенциального deadlock."""

    pass


@dataclass
class LockStats:
    """Статистика использования блокировки."""

    name: str
    lock_type: str
    acquisition_count: int = 0
    total_wait_time: float = 0.0
    max_hold_time: float = 0.0
    avg_wait_time: float = 0.0
    holder_thread: Optional[int] = None
    is_held: bool = False

    def update_wait_time(self, wait_time: float) -> None:
        """Обновляет статистику времени ожидания."""
        self.total_wait_time += wait_time
        self.acquisition_count += 1
        self.avg_wait_time = self.total_wait_time / self.acquisition_count

    def update_hold_time(self, hold_time: float) -> None:
        """Обновляет статистику времени удержания."""
        self.max_hold_time = max(self.max_hold_time, hold_time)


class EnhancedLock:
    """Улучшенная блокировка с таймаутами и мониторингом."""

    def __init__(self, name: str, lock_type: LockType, reentrant: bool = True):
        self.name = name
        self.lock_type = lock_type
        self._lock = RLock() if reentrant else Lock()
        self._acquisition_time: Optional[float] = None
        self._holder_thread: Optional[int] = None
        self._stats = LockStats(name, lock_type.value)

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Захватывает блокировку с опциональным таймаутом.

        Args:
            timeout: Максимальное время ожидания в секундах (None = бесконечно)

        Returns:
            True если блокировка захвачена, False при таймауте

        Raises:
            LockTimeout: При превышении таймаута
        """
        start_time = time.time()
        thread_id = threading.get_ident()

        logger.debug(f"[LOCK] Попытка захвата {self.name} потоком {thread_id}")

        # Пытаемся захватить блокировку
        acquired = self._lock.acquire(timeout=timeout or -1)

        if not acquired:
            wait_time = time.time() - start_time
            logger.warning(
                f"[LOCK] Таймаут захвата {self.name} потоком {thread_id} ({wait_time:.3f}s)"
            )
            raise LockTimeout(
                f"Не удалось захватить блокировку {self.name} за {timeout}s"
            )

        # Обновляем статистику
        wait_time = time.time() - start_time
        self._stats.update_wait_time(wait_time)
        self._acquisition_time = time.time()
        self._holder_thread = thread_id
        self._stats.holder_thread = thread_id
        self._stats.is_held = True

        logger.debug(
            f"[LOCK] Захвачена {self.name} потоком {thread_id} (ожидание: {wait_time:.3f}s)"
        )
        return True

    def release(self) -> None:
        """Освобождает блокировку и обновляет статистику."""
        if self._acquisition_time:
            hold_time = time.time() - self._acquisition_time
            self._stats.update_hold_time(hold_time)

            if hold_time > 1.0:  # Предупреждение о длительном удержании
                logger.warning(
                    f"[LOCK] Длительное удержание {self.name}: {hold_time:.3f}s"
                )

        thread_id = threading.get_ident()
        logger.debug(f"[LOCK] Освобождена {self.name} потоком {thread_id}")

        self._acquisition_time = None
        self._holder_thread = None
        self._stats.holder_thread = None
        self._stats.is_held = False
        self._lock.release()

    def get_stats(self) -> LockStats:
        """Возвращает статистику использования блокировки."""
        return self._stats


class LockManager:
    """Менеджер блокировок с защитой от deadlock."""

    def __init__(self):
        # Порядок захвата блокировок для предотвращения deadlock
        self._lock_order = [LockType.DATABASE, LockType.TASKS, LockType.UI_STATE]
        self._locks: Dict[str, EnhancedLock] = {}
        self._thread_locks: Dict[int, Set[EnhancedLock]] = {}
        self._manager_lock = RLock()

    def create_lock(
        self, name: str, lock_type: LockType, reentrant: bool = True
    ) -> EnhancedLock:
        """Создает новую блокировку."""
        with self._manager_lock:
            if name in self._locks:
                return self._locks[name]

            lock = EnhancedLock(name, lock_type, reentrant)
            self._locks[name] = lock
            return lock

    def get_lock(self, name: str) -> Optional[EnhancedLock]:
        """Получает существующую блокировку по имени."""
        return self._locks.get(name)

    @contextmanager
    def acquire_lock(self, name: str, timeout: float = 5.0):
        """
        Контекстный менеджер для безопасного захвата блокировки.

        Args:
            name: Имя блокировки
            timeout: Таймаут в секундах
        """
        lock = self._locks.get(name)
        if not lock:
            raise ValueError(f"Блокировка {name} не найдена")

        thread_id = threading.get_ident()

        # Проверяем порядок захвата для предотвращения deadlock
        with self._manager_lock:
            self._check_lock_order(thread_id, lock.lock_type)

            # Добавляем в список блокировок потока
            if thread_id not in self._thread_locks:
                self._thread_locks[thread_id] = set()
            self._thread_locks[thread_id].add(lock)

        try:
            # Захватываем блокировку
            lock.acquire(timeout)
            yield
        finally:
            # Освобождаем блокировку
            lock.release()

            # Удаляем из списка блокировок потока
            with self._manager_lock:
                if thread_id in self._thread_locks:
                    self._thread_locks[thread_id].discard(lock)
                    if not self._thread_locks[thread_id]:
                        del self._thread_locks[thread_id]

    def _check_lock_order(self, thread_id: int, new_lock_type: LockType) -> None:
        """Проверяет порядок захвата блокировок для предотвращения deadlock."""
        if thread_id not in self._thread_locks:
            return

        # Получаем текущие блокировки потока
        current_locks = self._thread_locks[thread_id]

        # Проверяем порядок захвата
        current_lock_types = [lock.lock_type for lock in current_locks]

        # Проверяем, не нарушает ли новый тип порядок
        try:
            current_type_indices = [
                self._lock_order.index(t) for t in current_lock_types
            ]
            new_type_index = self._lock_order.index(new_lock_type)

            # Если новый тип должен быть захвачен раньше какого-либо текущего,
            # это может привести к deadlock
            if any(new_type_index < idx for idx in current_type_indices):
                logger.warning(
                    f"[LOCK] Потенциальный deadlock: попытка захвата {new_lock_type.value} "
                    f"после {[t.value for t in current_lock_types]}"
                )
        except ValueError:
            # Если тип не в списке упорядоченных, пропускаем проверку
            pass

    def get_all_lock_stats(self) -> Dict[str, LockStats]:
        """Возвращает статистику по всем блокировкам."""
        return {name: lock.get_stats() for name, lock in self._locks.items()}


# ====================
# Защита сигналов (Signal Guard)
# ====================


class SignalGuard:
    """
    Класс для защиты от циклических вызовов сигналов/слотов.

    Отслеживает активные вызовы слотов и предотвращает повторные вызовы
    одного и того же слота во время его выполнения.
    """

    def __init__(self):
        self._active_calls: Dict[int, Set[str]] = {}
        self._lock = threading.RLock()
        self._call_counts: Dict[str, int] = {}
        self._max_recursive_calls = 3  # Максимум рекурсивных вызовов

    def is_active(self, slot_name: str) -> bool:
        """Проверяет, активен ли слот в текущем потоке."""
        thread_id = threading.get_ident()
        with self._lock:
            active_slots = self._active_calls.get(thread_id, set())
            return slot_name in active_slots

    def enter_slot(self, slot_name: str) -> bool:
        """
        Входит в слот. Возвращает True, если вход разрешен.
        False, если слот уже активен (предотвращение рекурсии).
        """
        thread_id = threading.get_ident()

        with self._lock:
            # Проверяем счетчик вызовов
            current_count = self._call_counts.get(slot_name, 0)
            if current_count >= self._max_recursive_calls:
                logger.warning(
                    f"[SignalGuard] Превышен лимит рекурсивных вызовов для {slot_name}: {current_count}"
                )
                return False

            # Проверяем активные вызовы
            if thread_id not in self._active_calls:
                self._active_calls[thread_id] = set()

            active_slots = self._active_calls[thread_id]
            if slot_name in active_slots:
                logger.warning(
                    f"[SignalGuard] Предотвращена рекурсия для слота: {slot_name}"
                )
                return False

            # Разрешаем вход
            active_slots.add(slot_name)
            self._call_counts[slot_name] = current_count + 1

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    f"[SignalGuard] Вход в слот: {slot_name} (поток: {thread_id})"
                )

            return True

    def exit_slot(self, slot_name: str) -> None:
        """Выходит из слота, освобождая защиту."""
        thread_id = threading.get_ident()

        with self._lock:
            if thread_id in self._active_calls:
                active_slots = self._active_calls[thread_id]
                active_slots.discard(slot_name)

                # Очищаем пустые наборы
                if not active_slots:
                    del self._active_calls[thread_id]

            # Уменьшаем счетчик
            if slot_name in self._call_counts:
                self._call_counts[slot_name] = max(0, self._call_counts[slot_name] - 1)
                if self._call_counts[slot_name] == 0:
                    del self._call_counts[slot_name]

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    f"[SignalGuard] Выход из слота: {slot_name} (поток: {thread_id})"
                )

    def get_active_slots(self) -> Dict[int, Set[str]]:
        """Возвращает копию активных слотов для диагностики."""
        with self._lock:
            return {tid: slots.copy() for tid, slots in self._active_calls.items()}

    def reset(self) -> None:
        """Сбрасывает все активные вызовы (для экстренных случаев)."""
        with self._lock:
            self._active_calls.clear()
            self._call_counts.clear()
            logger.warning("[SignalGuard] Принудительный сброс всех активных слотов")


# ====================
# Глобальные экземпляры и функции
# ====================

# Глобальный менеджер блокировок
_lock_manager = LockManager()

# Глобальный экземпляр для защиты сигналов
_global_guard = SignalGuard()

# Создаем стандартные блокировки
enhanced_db_lock = _lock_manager.create_lock(
    "database", LockType.DATABASE, reentrant=True
)
enhanced_tasks_lock = _lock_manager.create_lock(
    "tasks", LockType.TASKS, reentrant=False
)

# Прямой доступ к внутренним блокировкам для обратной совместимости
# Использовать только если необходима максимальная производительность
# и не требуется мониторинг/таймауты
db_lock = enhanced_db_lock._lock
tasks_lock = enhanced_tasks_lock._lock


# ====================
# Контекстные менеджеры для блокировок
# ====================


@contextmanager
def safe_db_lock(timeout: float = 5.0):
    """Безопасный захват блокировки базы данных с таймаутом."""
    with _lock_manager.acquire_lock("database", timeout):
        yield


@contextmanager
def safe_tasks_lock(timeout: float = 2.0):
    """Безопасный захват блокировки задач с таймаутом."""
    with _lock_manager.acquire_lock("tasks", timeout):
        yield


# ====================
# Функции для работы с блокировками
# ====================


def get_lock_manager() -> LockManager:
    """Возвращает глобальный менеджер блокировок."""
    return _lock_manager


def log_lock_stats() -> None:
    """Выводит статистику использования блокировок в лог."""
    stats = _lock_manager.get_all_lock_stats()
    if not stats:
        logger.info("[LOCKS] Нет статистики блокировок")
        return

    logger.info("[LOCKS] Статистика использования блокировок:")
    for name, stat in stats.items():
        logger.info(
            f"  {name}: захватов={stat.acquisition_count}, "
            f"ожидание={stat.total_wait_time:.3f}s, "
            f"макс.удержание={stat.max_hold_time:.3f}s"
        )


@contextmanager
def debug_lock(lock, operation_name: str):
    """Контекстный менеджер с логированием блокировок для отладки."""
    thread_id = threading.get_ident()
    logger.debug(f"[DEBUG_LOCK] Захват {operation_name} потоком {thread_id}")
    start_time = time.time()

    with lock:
        acquire_time = time.time() - start_time
        logger.debug(
            f"[DEBUG_LOCK] Захвачена {operation_name} потоком {thread_id} ({acquire_time:.3f}s)"
        )
        try:
            yield
        finally:
            hold_time = time.time() - start_time - acquire_time
            logger.debug(
                f"[DEBUG_LOCK] Освобождена {operation_name} потоком {thread_id} (удержание: {hold_time:.3f}s)"
            )


# ====================
# Декораторы и функции для защиты сигналов
# ====================


def signal_guard(slot_name: str = None):
    """
    Декоратор для защиты слотов от циклических вызовов.

    Args:
        slot_name: Имя слота для идентификации. Если не указано, используется имя функции.

    Usage:
        @signal_guard("my_slot")
        def my_slot_method(self):
            # Защищенный код
            pass
    """

    def decorator(func: Callable) -> Callable:
        nonlocal slot_name
        if slot_name is None:
            slot_name = f"{func.__qualname__}"

        @wraps(func)
        def wrapper(*args, **kwargs):
            if not _global_guard.enter_slot(slot_name):
                # Рекурсия предотвращена
                return None

            try:
                return func(*args, **kwargs)
            finally:
                _global_guard.exit_slot(slot_name)

        return wrapper

    return decorator


def get_signal_guard() -> SignalGuard:
    """Возвращает глобальный экземпляр SignalGuard."""
    return _global_guard


class GuardedSlotMixin:
    """
    Миксин для классов, которые хотят использовать защищенные слоты.

    Предоставляет удобные методы для работы с SignalGuard.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._signal_guard = get_signal_guard()

    def guarded_slot(self, slot_name: str, slot_func: Callable, *args, **kwargs):
        """
        Выполняет слот с защитой от рекурсии.

        Args:
            slot_name: Имя слота для идентификации
            slot_func: Функция слота для выполнения
            *args, **kwargs: Аргументы для передачи в слот

        Returns:
            Результат выполнения слота или None, если рекурсия предотвращена
        """
        if not self._signal_guard.enter_slot(slot_name):
            return None

        try:
            return slot_func(*args, **kwargs)
        finally:
            self._signal_guard.exit_slot(slot_name)

    def is_slot_active(self, slot_name: str) -> bool:
        """Проверяет, активен ли указанный слот."""
        return self._signal_guard.is_active(slot_name)


# ====================
# Утилиты для мониторинга
# ====================


def log_signal_guard_stats():
    """Логирует статистику использования SignalGuard."""
    guard = get_signal_guard()
    active_slots = guard.get_active_slots()

    if active_slots:
        logger.info("[SignalGuard] Активные слоты по потокам:")
        for thread_id, slots in active_slots.items():
            logger.info(f"  Поток {thread_id}: {', '.join(slots)}")
    else:
        logger.info("[SignalGuard] Нет активных слотов")


def emergency_reset_signal_guard():
    """Экстренный сброс SignalGuard (использовать только в критических случаях)."""
    logger.warning("[SignalGuard] ЭКСТРЕННЫЙ СБРОС - все активные слоты будут сброшены")
    get_signal_guard().reset()
