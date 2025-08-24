"""Публичный фасад для запуска фоновых задач работы с БД.

Пример:
    from app.utils.db.api import run_db

    handle = run_db(lambda: db.links.upsert_link(data), on_finished=cb)
    handle.cancel()
"""

from __future__ import annotations

from typing import Callable, Optional, Protocol, TypeVar

from PyQt6.QtCore import QThreadPool

from app.utils.db.db_error_handler import handle_db_error
from app.utils.db.executors.pool import get_thread_pool
from app.utils.db.synchronization import db_lock
from app.utils.db.tasks.base import DatabaseTask, TaskSignals

T = TypeVar("T")


class TaskHandle(Protocol):
    signals: TaskSignals

    def cancel(self) -> None: ...  # noqa: E701


class _TaskHandleImpl:
    def __init__(self, task: DatabaseTask[T]) -> None:
        self._task = task
        self.signals = task.signals

    def cancel(self) -> None:
        self._task.cancel()


def run_db(
    func: Callable[[], T],
    *,
    use_lock: bool = True,
    description: Optional[str] = None,
    pool: Optional[QThreadPool] = None,
    on_finished: Optional[Callable[[T], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
    on_progress: Optional[Callable[[int], None]] = None,
) -> TaskHandle:
    """Запустить функцию БД в пуле потоков.

    - use_lock: выполнить под глобальным db_lock
    - description: описание для логирования/диагностики
    - on_finished/on_error/on_progress: необязательные колбэки на сигналы
    - pool: опционально указать свой QThreadPool
    """

    def _wrapped() -> T:
        if use_lock:
            with db_lock:
                return func()
        return func()

    task = DatabaseTask[T](
        _wrapped, description=description, reporter=(on_progress or (lambda *_: None))
    )

    if on_finished is not None:
        task.signals.finished.connect(on_finished)

    def _on_error(e: Exception) -> None:
        handle_db_error(e)
        if on_error is not None:
            on_error(e)

    task.signals.error.connect(_on_error)

    (pool or get_thread_pool()).start(task)
    return _TaskHandleImpl(task)
