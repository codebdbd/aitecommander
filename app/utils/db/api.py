"""Публичный фасад для запуска фоновых задач работы с БД.

Примеры:
    from app.utils.db.api import run_db

    # Базовый запуск без прогресса
    handle = run_db(lambda: db.links.upsert_link(data), on_finished=cb)

    # Отмена задачи
    handle.cancel()

    # Репортинг прогресса (0..100):
    # 1) Передайте обработчик on_progress, чтобы получать значения в колбэке.
    # 2) Подпишитесь на handle.signals.progress, чтобы получать Qt-сигналы в UI.
    # 3) Передайте в исполняемую функцию позиционный аргумент-репортёр и вызывайте его.
    #    Если функция принимает один аргумент, run_db передаст в неё callable report_progress.
    #    Иначе функция будет вызвана как есть (обратная совместимость).
    #
    # Пример с явным репортингом внутри функции:
    def long_job(report_progress):
        for i in range(101):
            # ... работа ...
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
from typing import Callable, Optional, Protocol, TypeVar, overload, cast

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


ProgressReporter = Callable[[int], None]


@overload
def run_db(
    func: Callable[[ProgressReporter], T],
    *,
    use_lock: bool = ...,
    description: Optional[str] = ...,
    pool: Optional[QThreadPool] = ...,
    on_finished: Optional[Callable[[T], None]] = ...,
    on_error: Optional[Callable[[Exception], None]] = ...,
    on_progress: Optional[Callable[[int], None]] = ...,
) -> TaskHandle: ...


@overload
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

    Отчёт о прогрессе:
    - Внутри задачи можно вызывать переданный позиционный аргумент `report_progress(value: int)`
      (если функция объявлена с одним позиционным параметром). Это эмитит Qt-сигнал
      `signals.progress` и вызывает `on_progress`, если он передан.
    - Либо можно подписаться на `handle.signals.progress` из UI.
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

    if expects_reporter:
        func_with_reporter = cast(Callable[[ProgressReporter], T], func)
        if use_lock:

            def _wrapped(report_progress: ProgressReporter) -> T:
                with db_lock:
                    return func_with_reporter(report_progress)
        else:

            def _wrapped(report_progress: ProgressReporter) -> T:
                return func_with_reporter(report_progress)
    else:
        func_noargs = cast(Callable[[], T], func)
        if use_lock:

            def _wrapped() -> T:
                with db_lock:
                    return func_noargs()
        else:

            def _wrapped() -> T:
                return func_noargs()

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
