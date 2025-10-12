"""Synchronization helpers for safe multi-threaded execution.

This module combines lock utilities and signal-loop protection:
- Base and enhanced locks with timeouts and monitoring
- Lock manager with deadlock prevention
- Protection against cyclic signal/slot invocations in PyQt6 applications
"""

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from threading import Lock, RLock
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ====================
# Locking utilities
# ====================


class LockType(Enum):
    """Lock acquisition order categories."""

    DATABASE = "database"
    TASKS = "tasks"
    UI_STATE = "ui_state"


class LockTimeout(Exception):
    """Raised when a lock acquisition times out."""

    pass


class DeadlockDetected(Exception):
    """Raised when a potential deadlock is detected."""

    pass


@dataclass
class LockStats:
    """Lock usage statistics."""

    name: str
    lock_type: str
    acquisition_count: int = 0
    total_wait_time: float = 0.0
    max_hold_time: float = 0.0
    avg_wait_time: float = 0.0
    holder_thread: Optional[int] = None
    is_held: bool = False

    def update_wait_time(self, wait_time: float) -> None:
        """Update wait-time statistics."""
        self.total_wait_time += wait_time
        self.acquisition_count += 1
        self.avg_wait_time = self.total_wait_time / self.acquisition_count

    def update_hold_time(self, hold_time: float) -> None:
        """Update held-time statistics."""
        self.max_hold_time = max(self.max_hold_time, hold_time)


class EnhancedLock:
    """Enhanced lock with timeout support and monitoring."""

    def __init__(self, name: str, lock_type: LockType, reentrant: bool = True):
        """Initialise enhanced lock.

        ✅ CHANGE: Added logging threshold.
        """
        self.name = name
        self.lock_type = lock_type
        self._lock = RLock() if reentrant else Lock()
        self._acquisition_time: Optional[float] = None
        self._holder_thread: Optional[int] = None
        self._stats = LockStats(name, lock_type.value)
        # ✅ Log only slow operations
        self._log_threshold_ms = 100.0  # Log when > 100 ms

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """Acquire the lock with an optional timeout.

        Args:
            timeout: Maximum wait time in seconds (``None`` = infinite)

        Returns:
            ``True`` if the lock is acquired, ``False`` on timeout

        Raises:
            LockTimeout: when timeout is exceeded
        """
        start_time = time.time()
        thread_id = threading.get_ident()

        # Attempt to acquire the lock
        acquired = self._lock.acquire(timeout=timeout or -1)

        if not acquired:
            wait_time = time.time() - start_time
            logger.warning(
                "[LOCK] Acquire timeout %s by thread %s (%.3fs)",
                self.name,
                thread_id,
                wait_time,
            )
            raise LockTimeout(f"Failed to acquire lock {self.name} within {timeout}s")

        # Update stats
        wait_time = time.time() - start_time
        wait_time_ms = wait_time * 1000.0
        self._stats.update_wait_time(wait_time)
        self._acquisition_time = time.time()
        self._holder_thread = thread_id
        self._stats.holder_thread = thread_id
        self._stats.is_held = True

        # ✅ Log only slow acquisitions
        if wait_time_ms > self._log_threshold_ms:
            logger.warning(
                "[LOCK] Slow acquisition %s by thread %s: %.2fms",
                self.name,
                thread_id,
                wait_time_ms,
            )
        elif logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "[LOCK] Acquired %s by thread %s (wait: %.2fms)",
                self.name,
                thread_id,
                wait_time_ms,
            )
        return True

    def release(self) -> None:
        """Release the lock and update statistics.

        ✅ CHANGE: Log only long hold durations.
        """
        if self._acquisition_time:
            hold_time = time.time() - self._acquisition_time
            self._stats.update_hold_time(hold_time)

            # ✅ Log long holds (> 1 s)
            if hold_time > 1.0:
                logger.warning("[LOCK] Long hold %s: %.3fs", self.name, hold_time)

        self._acquisition_time = None
        self._holder_thread = None
        self._stats.holder_thread = None
        self._stats.is_held = False
        self._lock.release()

    def get_stats(self) -> LockStats:
        """Return lock usage statistics."""
        return self._stats


class LockManager:
    """Lock manager with deadlock prevention."""

    def __init__(self):
        # Acquisition order to prevent deadlocks
        self._lock_order = [LockType.DATABASE, LockType.TASKS, LockType.UI_STATE]
        self._locks: dict[str, EnhancedLock] = {}
        self._thread_locks: dict[int, set[EnhancedLock]] = {}
        self._manager_lock = RLock()

    def create_lock(
        self, name: str, lock_type: LockType, reentrant: bool = True
    ) -> EnhancedLock:
        """Create or return a named lock."""
        with self._manager_lock:
            if name in self._locks:
                return self._locks[name]

            lock = EnhancedLock(name, lock_type, reentrant)
            self._locks[name] = lock
            return lock

    def get_lock(self, name: str) -> Optional[EnhancedLock]:
        """Return existing lock by name if present."""
        return self._locks.get(name)

    @contextmanager
    def acquire_lock(self, name: str, timeout: float = 5.0):
        """Context manager to acquire a lock safely.

        Args:
            name: Lock name to acquire
            timeout: Timeout in seconds
        """
        lock = self._locks.get(name)
        if not lock:
            raise ValueError(f"Lock {name} not found")

        thread_id = threading.get_ident()

        # Validate acquisition order to prevent deadlocks
        with self._manager_lock:
            self._check_lock_order(thread_id, lock.lock_type)

            # Register lock for the current thread
            if thread_id not in self._thread_locks:
                self._thread_locks[thread_id] = set()
            self._thread_locks[thread_id].add(lock)

        try:
            # Acquire
            lock.acquire(timeout)
            yield
        finally:
            # Release
            lock.release()

            # Remove from thread lock list
            with self._manager_lock:
                if thread_id in self._thread_locks:
                    self._thread_locks[thread_id].discard(lock)
                    if not self._thread_locks[thread_id]:
                        del self._thread_locks[thread_id]

    def _check_lock_order(self, thread_id: int, new_lock_type: LockType) -> None:
        """Check acquisition order to prevent deadlocks."""
        if thread_id not in self._thread_locks:
            return

        # Current locks held by thread
        current_locks = self._thread_locks[thread_id]

        # Order validation
        current_lock_types = [lock.lock_type for lock in current_locks]

        # Ensure new lock type does not break order
        try:
            current_type_indices = [
                self._lock_order.index(t) for t in current_lock_types
            ]
            new_type_index = self._lock_order.index(new_lock_type)

            # If new lock must be acquired before existing ones, warn
            if any(new_type_index < idx for idx in current_type_indices):
                logger.warning(
                    "[LOCK] Potential deadlock: attempt to acquire %s after %s",
                    new_lock_type.value,
                    [t.value for t in current_lock_types],
                )
        except ValueError:
            # Skip check if type is not part of the predefined order
            pass

    def get_all_lock_stats(self) -> dict[str, LockStats]:
        """Return stats for all locks."""
        return {name: lock.get_stats() for name, lock in self._locks.items()}


# ====================
# Signal guard utilities
# ====================


class SignalGuard:
    """Protect against cyclic signal/slot invocations.

    Tracks active slot invocations and prevents re-entrancy while executing.
    """

    def __init__(self):
        self._active_calls: dict[int, set[str]] = {}
        self._lock = threading.RLock()
        self._call_counts: dict[str, int] = {}
        self._max_recursive_calls = 3  # Maximum recursive calls

    def is_active(self, slot_name: str) -> bool:
        """Return whether slot is active in current thread."""
        thread_id = threading.get_ident()
        with self._lock:
            active_slots = self._active_calls.get(thread_id, set())
            return slot_name in active_slots

    def enter_slot(self, slot_name: str) -> bool:
        """Enter slot if allowed.

        Returns ``True`` when permitted, ``False`` to prevent recursion.
        """
        thread_id = threading.get_ident()

        with self._lock:
            # Check invocation counter
            current_count = self._call_counts.get(slot_name, 0)
            if current_count >= self._max_recursive_calls:
                logger.warning(
                    "[SignalGuard] Recursive invocation limit exceeded for %s: %s",
                    slot_name,
                    current_count,
                )
                return False

            # Check active calls
            if thread_id not in self._active_calls:
                self._active_calls[thread_id] = set()

            active_slots = self._active_calls[thread_id]
            if slot_name in active_slots:
                logger.warning(
                    "[SignalGuard] Recursion prevented for slot: %s", slot_name
                )
                return False

            # Allow execution
            active_slots.add(slot_name)
            self._call_counts[slot_name] = current_count + 1

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "[SignalGuard] Enter slot: %s (thread: %s)", slot_name, thread_id
                )

            return True

    def exit_slot(self, slot_name: str) -> None:
        """Exit slot and release guard."""
        thread_id = threading.get_ident()

        with self._lock:
            if thread_id in self._active_calls:
                active_slots = self._active_calls[thread_id]
                active_slots.discard(slot_name)

                # Clean up empty sets
                if not active_slots:
                    del self._active_calls[thread_id]

            # Decrement counter
            if slot_name in self._call_counts:
                self._call_counts[slot_name] = max(0, self._call_counts[slot_name] - 1)
                if self._call_counts[slot_name] == 0:
                    del self._call_counts[slot_name]

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "[SignalGuard] Exit slot: %s (thread: %s)", slot_name, thread_id
                )

    def get_active_slots(self) -> dict[int, set[str]]:
        """Return copy of active slots for diagnostics."""
        with self._lock:
            return {tid: slots.copy() for tid, slots in self._active_calls.items()}

    def reset(self) -> None:
        """Reset all active calls (emergency use)."""
        with self._lock:
            self._active_calls.clear()
            self._call_counts.clear()
            logger.warning("[SignalGuard] Forced reset of all active slots")


# ====================
# Глобальные экземпляры и функции
# ====================

# Global lock manager
_lock_manager = LockManager()

# Global signal guard
_global_guard = SignalGuard()

# Create default locks
enhanced_db_lock = _lock_manager.create_lock(
    "database", LockType.DATABASE, reentrant=True
)
enhanced_tasks_lock = _lock_manager.create_lock(
    "tasks", LockType.TASKS, reentrant=False
)

# Direct access to raw locks for compatibility/performance (no monitoring/timeout)
db_lock = enhanced_db_lock._lock
tasks_lock = enhanced_tasks_lock._lock


# ====================
# Context managers for locks
# ====================


@contextmanager
def safe_db_lock(timeout: float = 5.0):
    """Safely acquire database lock with timeout."""
    with _lock_manager.acquire_lock("database", timeout):
        yield


@contextmanager
def safe_tasks_lock(timeout: float = 2.0):
    """Safely acquire tasks lock with timeout."""
    with _lock_manager.acquire_lock("tasks", timeout):
        yield


# ====================
# Lock helper functions
# ====================


def get_lock_manager() -> LockManager:
    """Return global lock manager."""
    return _lock_manager


def log_lock_stats() -> None:
    """Emit lock usage statistics to the log."""


@contextmanager
def debug_lock(lock, operation_name: str):
    """Context manager with lock logging for debugging."""
    thread_id = threading.get_ident()
    logger.debug("[DEBUG_LOCK] Acquire %s by thread %s", operation_name, thread_id)
    start_time = time.time()

    with lock:
        acquire_time = time.time() - start_time
        logger.debug(
            "[DEBUG_LOCK] Acquired %s by thread %s (%.3fs)",
            operation_name,
            thread_id,
            acquire_time,
        )
        try:
            yield
        finally:
            hold_time = time.time() - start_time - acquire_time
            logger.debug(
                "[DEBUG_LOCK] Released %s by thread %s (hold: %.3fs)",
                operation_name,
                thread_id,
                hold_time,
            )


# ====================
# Decorators & helpers for signal guard
# ====================


def signal_guard(slot_name: str = None):
    """Decorator to protect slots from cyclic calls.

    Args:
        slot_name: Slot identifier; defaults to function name.

    Usage::
        @signal_guard("my_slot")
        def my_slot_method(self):
            # protected code
            ...
    """

    def decorator(func: Callable) -> Callable:
        nonlocal slot_name
        if slot_name is None:
            slot_name = f"{func.__qualname__}"

        @wraps(func)
        def wrapper(*args, **kwargs):
            if not _global_guard.enter_slot(slot_name):
                # Recursion prevented
                return None

            try:
                return func(*args, **kwargs)
            finally:
                _global_guard.exit_slot(slot_name)

        return wrapper

    return decorator


def get_signal_guard() -> SignalGuard:
    """Return global ``SignalGuard`` instance."""
    return _global_guard


class GuardedSlotMixin:
    """Mixin for classes that need guarded slots.

    Provides convenient helpers to work with ``SignalGuard``.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._signal_guard = get_signal_guard()

    def guarded_slot(self, slot_name: str, slot_func: Callable, *args, **kwargs):
        """Execute slot with recursion protection.

        Args:
            slot_name: Slot identifier
            slot_func: Slot callable to execute
            *args, **kwargs: Arguments passed to slot

        Returns:
            Slot result or ``None`` if recursion prevented
        """
        if not self._signal_guard.enter_slot(slot_name):
            return None

        try:
            return slot_func(*args, **kwargs)
        finally:
            self._signal_guard.exit_slot(slot_name)

    def is_slot_active(self, slot_name: str) -> bool:
        """Return whether given slot is active."""
        return self._signal_guard.is_active(slot_name)


# ====================
# Monitoring utilities
# ====================


def log_signal_guard_stats():
    """Log current ``SignalGuard`` usage statistics."""
    guard = get_signal_guard()
    active_slots = guard.get_active_slots()

    if active_slots:
        logger.info("[SignalGuard] Active slots by thread:")
        for thread_id, slots in active_slots.items():
            logger.info("  Thread %s: %s", thread_id, ", ".join(slots))
    else:
        logger.info("[SignalGuard] No active slots")


def emergency_reset_signal_guard():
    """Emergency reset for ``SignalGuard`` (critical scenarios only)."""
    logger.warning("[SignalGuard] EMERGENCY RESET - clearing all active slots")
    get_signal_guard().reset()
