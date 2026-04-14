"""Public facade for running database tasks in background threads.

Examples::
    from app.utils.db.api import run_db

    # Basic run without progress reporting
    handle = run_db(lambda: db.links.upsert_link(data), on_finished=cb)

    # Cancel the task
    handle.cancel()

    # Progress reporting (0..100):
    # 1) Provide `on_progress` to receive updates in a Python callback.
    # 2) Subscribe to `handle.signals.progress` to react inside Qt UI code.
    # 3) Accept a positional reporter argument in the callable and invoke it.
    #    If the callable accepts one positional parameter, ``run_db`` will pass
    #    ``report_progress``. Otherwise the callable is invoked as-is for
    #    backwards compatibility.
    #
    # Example with explicit progress reporting inside the callable:
    def long_job(report_progress):
        for i in range(101):
            # ... work ...
            report_progress(i)
        return "ok"

    handle = run_db(
        long_job,
        on_progress=lambda v: logger.info("progress: %s", v),
        on_finished=lambda res: logger.info("done %s", res),
    )
"""

from __future__ import annotations

import inspect
import logging
import time
from typing import Callable, Protocol, TypeVar

from PyQt6.QtCore import (
    QCoreApplication,
    QObject,
    QThread,
    Qt,
    QThreadPool,
    pyqtSignal,
    pyqtSlot,
)

from app.utils.db.db_error_handler import handle_db_error
from app.utils.db.executors.pool import get_thread_pool
from app.utils.db.synchronization import db_lock
from app.utils.db.tasks.base import DatabaseTask, TaskSignals
from app.utils.metrics import get_metrics

T = TypeVar("T")
logger = logging.getLogger(__name__)


class TaskHandle(Protocol):
    signals: TaskSignals

    def cancel(self) -> None: ...  # noqa: E701


class _TaskHandleImpl:
    def __init__(self, task: DatabaseTask[T]) -> None:
        self._task = task
        self.signals = task.signals

    def cancel(self) -> None:
        self._task.cancel()


class _CallbackDispatcher(QObject):
    """Proxy object to marshal callbacks back to the GUI thread."""

    invoke = pyqtSignal(object, object, object)

    def __init__(self) -> None:
        parent = QCoreApplication.instance()
        super().__init__(parent)
        self.invoke.connect(
            self._execute, Qt.ConnectionType.QueuedConnection  # type: ignore[arg-type]
        )

    @pyqtSlot(object, object, object)
    def _execute(
        self, callback: Callable[..., object], args: tuple, kwargs: dict
    ) -> None:
        try:
            callback(*args, **kwargs)
        except Exception:
            logger.exception("Callback raised an exception in GUI thread")


_DISPATCHER: _CallbackDispatcher | None = None


def _get_dispatcher() -> _CallbackDispatcher | None:
    """Return shared dispatcher if QApplication exists."""
    global _DISPATCHER
    app = QCoreApplication.instance()
    if app is None:
        return None
    if _DISPATCHER is None:
        _DISPATCHER = _CallbackDispatcher()
    return _DISPATCHER


def _is_gui_thread() -> bool:
    app = QCoreApplication.instance()
    if app is None:
        return False
    try:
        return QThread.currentThread() == app.thread()
    except Exception:
        return False


def _invoke_in_gui(callback: Callable[..., object] | None, *args) -> None:
    """Execute callback in GUI thread when possible."""
    if callback is None:
        return
    dispatcher = _get_dispatcher()
    if dispatcher is None:
        try:
            callback(*args)
        except Exception:
            logger.exception("Callback raised an exception (no QApplication)")
        return
    dispatcher.invoke.emit(callback, args, {})


def _expects_reporter(callable_obj: Callable[..., T]) -> bool:
    """Return True if callable expects a positional reporter argument."""
    try:
        sig = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return False
    has_var_positional = any(
        p.kind is inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()
    )
    if has_var_positional:
        return True
    positional_count = sum(
        1
        for p in sig.parameters.values()
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    )
    return positional_count == 1


def _build_task_callable(
    func: Callable[..., T],
    *,
    use_lock: bool,
    expects_reporter: bool,
    description: str | None = None,
) -> Callable[..., T]:
    """Wrap user callable with optional db_lock and reporter argument."""
    op_name = (description or "run_db_task").strip() or "run_db_task"

    def _record_timing(metric_name: str, value_ms: float) -> None:
        metrics = get_metrics()
        metrics.record_timing(metric_name, value_ms)
        stats = metrics.get_stats(metric_name)
        if value_ms >= 25.0:
            logger.info("[Perf] run_db %s op=%s value=%.2f ms", metric_name, op_name, value_ms)
        else:
            logger.debug(
                "[Perf] run_db %s op=%s value=%.2f ms", metric_name, op_name, value_ms
            )
        count = int(stats.get("count", 0))
        if count > 0 and count % 20 == 0:
            logger.info(
                "[PerfAgg] %s: n=%s p50=%.2f ms p95=%.2f ms avg=%.2f ms",
                metric_name,
                count,
                float(stats.get("p50", 0.0)),
                float(stats.get("p95", 0.0)),
                float(stats.get("avg", 0.0)),
            )

    def _call_with_reporter(report_progress: Callable[[int], None]) -> T:
        if use_lock:
            lock_requested_ts = time.perf_counter()
            with db_lock:
                lock_wait_ms = (time.perf_counter() - lock_requested_ts) * 1000
                _record_timing("run_db.lock_wait_ms", lock_wait_ms)
                exec_started_ts = time.perf_counter()
                try:
                    return func(report_progress)
                finally:
                    exec_ms = (time.perf_counter() - exec_started_ts) * 1000
                    _record_timing("run_db.exec_ms", exec_ms)
        exec_started_ts = time.perf_counter()
        try:
            return func(report_progress)
        finally:
            exec_ms = (time.perf_counter() - exec_started_ts) * 1000
            _record_timing("run_db.exec_ms", exec_ms)

    def _call_without_reporter() -> T:
        if use_lock:
            lock_requested_ts = time.perf_counter()
            with db_lock:
                lock_wait_ms = (time.perf_counter() - lock_requested_ts) * 1000
                _record_timing("run_db.lock_wait_ms", lock_wait_ms)
                exec_started_ts = time.perf_counter()
                try:
                    return func()
                finally:
                    exec_ms = (time.perf_counter() - exec_started_ts) * 1000
                    _record_timing("run_db.exec_ms", exec_ms)
        exec_started_ts = time.perf_counter()
        try:
            return func()
        finally:
            exec_ms = (time.perf_counter() - exec_started_ts) * 1000
            _record_timing("run_db.exec_ms", exec_ms)

    return _call_with_reporter if expects_reporter else _call_without_reporter


def _wrap_with_queue_wait_metrics(
    task_callable: Callable[..., T],
    *,
    description: str | None,
    expects_reporter: bool,
    queued_ts: float,
) -> Callable[..., T]:
    """Wrap callable to measure wait time from enqueue to actual execution start."""

    op_name = (description or "run_db_task").strip() or "run_db_task"

    def _record_wait() -> None:
        queue_wait_ms = (time.perf_counter() - queued_ts) * 1000
        metrics = get_metrics()
        metrics.record_timing("run_db.queue_wait_ms", queue_wait_ms)
        stats = metrics.get_stats("run_db.queue_wait_ms")
        if queue_wait_ms >= 25.0:
            logger.info("[Perf] run_db queue_wait op=%s wait=%.2f ms", op_name, queue_wait_ms)
        else:
            logger.debug(
                "[Perf] run_db queue_wait op=%s wait=%.2f ms", op_name, queue_wait_ms
            )
        count = int(stats.get("count", 0))
        if count > 0 and count % 20 == 0:
            logger.info(
                "[PerfAgg] run_db.queue_wait_ms: n=%s p50=%.2f ms p95=%.2f ms avg=%.2f ms",
                count,
                float(stats.get("p50", 0.0)),
                float(stats.get("p95", 0.0)),
                float(stats.get("avg", 0.0)),
            )

    if expects_reporter:
        def _wrapped(report_progress: Callable[[int], None]) -> T:
            _record_wait()
            return task_callable(report_progress)  # type: ignore[misc]

        return _wrapped

    def _wrapped_no_reporter() -> T:
        _record_wait()
        return task_callable()  # type: ignore[call-arg]

    return _wrapped_no_reporter


def _make_reporter(on_progress: Callable[[int], None] | None):
    """Create progress reporter callback for DatabaseTask."""
    if on_progress is None:
        return None

    def _report(value: int) -> None:
        if _is_gui_thread():
            on_progress(int(value))
            return
        _invoke_in_gui(on_progress, int(value))

    return _report


def _wire_finished(task: DatabaseTask[T], on_finished: Callable[[T], None] | None) -> None:
    """Connect finished signal to GUI-thread-safe callback."""
    if on_finished is None:
        return

    def _handle_finished(result: T) -> None:
        if _is_gui_thread():
            on_finished(result)
            return
        _invoke_in_gui(on_finished, result)

    task.signals.finished.connect(_handle_finished)


def _wire_error(task: DatabaseTask[T], on_error: Callable[[Exception], None] | None) -> None:
    """Connect error signal to default handler and optional user callback."""

    def _on_error(e: Exception) -> None:
        if _is_gui_thread():
            handle_db_error(e)
        else:
            _invoke_in_gui(handle_db_error, e)
        if on_error is not None:
            if _is_gui_thread():
                on_error(e)
            else:
                _invoke_in_gui(on_error, e)

    task.signals.error.connect(_on_error)


def _resolve_pool(pool: QThreadPool | None, *, use_lock: bool) -> QThreadPool:
    """Return provided pool or the appropriate default pool."""
    if pool is not None:
        return pool
    if use_lock:
        return get_thread_pool()
    shared_pool = QThreadPool.globalInstance()
    if shared_pool is None:
        raise RuntimeError("QThreadPool.globalInstance() returned None")
    return shared_pool


def run_db(
    func: Callable[..., T],
    *,
    use_lock: bool = True,
    description: str | None = None,
    pool: QThreadPool | None = None,
    on_finished: Callable[[T], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> TaskHandle:
    """Run a database callable inside the thread pool.

    - ``use_lock``: execute under the global ``db_lock``
    - ``description``: optional text for logging/diagnostics
    - ``on_finished`` / ``on_error`` / ``on_progress``: optional signal callbacks
    - ``pool``: custom ``QThreadPool`` if provided

    Progress reporting:
    - Inside the task you may call the positional argument ``report_progress(value: int)``
      (when the callable declares one positional parameter). This emits the Qt signal
      ``signals.progress`` and invokes ``on_progress`` if supplied.
    - Alternatively, subscribe to ``handle.signals.progress`` from the UI layer.
    """

    expects_reporter = _expects_reporter(func)
    task_callable: Callable[..., T] = _build_task_callable(
        func, use_lock=use_lock, expects_reporter=expects_reporter, description=description
    )
    queued_ts = time.perf_counter()
    task_callable = _wrap_with_queue_wait_metrics(
        task_callable,
        description=description,
        expects_reporter=expects_reporter,
        queued_ts=queued_ts,
    )

    reporter = _make_reporter(on_progress)

    task = DatabaseTask[T](
        task_callable,
        description=description,
        reporter=reporter,
    )

    _wire_finished(task, on_finished)

    _wire_error(task, on_error)

    _resolve_pool(pool, use_lock=use_lock).start(task)
    return _TaskHandleImpl(task)
