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
        on_progress=lambda v: print(f"progress: {v}"),
        on_finished=lambda res: print("done", res),
    )
"""

from __future__ import annotations

import inspect
from typing import Callable, Protocol, TypeVar

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

    def _expects_reporter(callable_obj: Callable[..., T]) -> bool:
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

    expects_reporter = _expects_reporter(func)

    def _call_with_reporter(report_progress: Callable[[int], None]) -> T:
        if use_lock:
            with db_lock:
                return func(report_progress)  # type: ignore[misc]
        return func(report_progress)  # type: ignore[misc]

    def _call_without_reporter() -> T:
        if use_lock:
            with db_lock:
                return func()
        return func()

    if expects_reporter:
        task_callable: Callable[..., T] = _call_with_reporter
    else:
        task_callable = _call_without_reporter

    task = DatabaseTask[T](
        task_callable,
        description=description,
        reporter=(on_progress or (lambda *_: None)),
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
