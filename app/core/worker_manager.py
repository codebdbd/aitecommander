"""Centralized background worker management."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from app.core.database_manager import DatabaseManager
from app.core.log_manager import LogManager

logger = LogManager.get_logger(__name__)


class WorkerSignals(QObject):
    """Signals for worker -> UI communication."""

    finished = pyqtSignal()
    error = pyqtSignal(str)
    result = pyqtSignal(object)
    progress = pyqtSignal(int)


class Worker(QRunnable):
    """Generic QRunnable wrapper for running a callable in a thread pool."""

    def __init__(
        self,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    def run(self) -> None:  # pragma: no cover (Qt thread)
        try:
            result = self.func(*self.args, **self.kwargs)
            self.signals.result.emit(result)
            self.signals.finished.emit()
        except Exception:
            tb_str = traceback.format_exc()
            logger.error("Worker error:\n%s", tb_str)
            self.signals.error.emit(tb_str)


class WorkerManager:
    """Static API for centralized background execution."""

    _pool: QThreadPool | None = None

    @classmethod
    def configure(cls, max_threads: int) -> None:
        pool = QThreadPool.globalInstance()
        if pool is None:
            pool = QThreadPool()
        pool.setMaxThreadCount(max(1, int(max_threads)))
        cls._pool = pool

    @classmethod
    def _get_pool(cls) -> QThreadPool:
        if cls._pool is None:
            cls.configure(max_threads=4)
        return cls._pool  # type: ignore[return-value]

    @classmethod
    def run(cls, func: Callable[..., Any] | QRunnable, *args: Any, **kwargs: Any) -> QRunnable:
        pool = cls._get_pool()
        if isinstance(func, QRunnable):
            pool.start(func)
            return func
        worker = Worker(func, args, kwargs)
        pool.start(worker)
        return worker

    @classmethod
    def run_db(cls, func: Callable[..., Any], *args: Any, **kwargs: Any) -> QRunnable:
        def _wrapped() -> Any:
            connection = DatabaseManager.get_connection()
            return func(connection, *args, **kwargs)

        return cls.run(_wrapped)

    @classmethod
    def shutdown(cls, timeout_ms: int) -> None:
        pool = cls._pool
        if pool is None:
            return
        pool.waitForDone(max(0, int(timeout_ms)))
