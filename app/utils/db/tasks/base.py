"""Basic types and helpers for background database tasks."""

from __future__ import annotations

import inspect
from typing import Callable, Generic, Optional, TypeVar

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

T = TypeVar("T")


class TaskSignals(QObject):
    """Signals emitted by background tasks.

    - ``finished(object)``: emitted with result on success
    - ``error(object)``: emitted with raised exception
    - ``progress(int)``: optional progress indicator 0..100
    - ``canceled()``: task was canceled
    """

    finished = pyqtSignal(object)
    error = pyqtSignal(object)
    progress = pyqtSignal(int)
    canceled = pyqtSignal()


class DatabaseTask(QRunnable, Generic[T]):
    """QRunnable wrapper that executes an arbitrary callable in the thread pool.

    Contains no UI dependencies. All error/lock handling happens externally.
    """

    def __init__(
        self,
        func: Callable[..., T],
        *,
        description: Optional[str] = None,
        reporter: Optional[Callable[[int], None]] = None,
    ) -> None:
        super().__init__()
        self.func = func
        self.signals = TaskSignals()
        self._canceled = False
        self.description = description
        # External progress callback; may be ``None``
        self._external_reporter: Optional[Callable[[int], None]] = reporter

    def report_progress(self, value: int) -> None:
        """Report task progress (0..100).

        Always emits ``signals.progress`` first, then (if provided) calls the
        external callback passed via ``run_db(..., on_progress=...)``.
        """
        try:
            self.signals.progress.emit(int(value))
        except Exception:
            # Ensure external callback is still called even if signal emission fails
            pass
        try:
            if self._external_reporter is not None:
                self._external_reporter(int(value))
        except Exception:
            # Do not interrupt the task due to errors in user callbacks
            pass

    def cancel(self) -> None:
        self._canceled = True

    def is_canceled(self) -> bool:
        return self._canceled

    # QRunnable
    def run(self) -> None:  # pragma: no cover (Qt thread)
        if self._canceled:
            self.signals.canceled.emit()
            return
        try:
            # Determine signature: support callables with 0 or 1 positional argument
            try:
                sig = inspect.signature(self.func)
                params = list(sig.parameters.values())
                pos_params = [
                    p
                    for p in params
                    if p.kind
                    in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ]
                has_var_pos = any(
                    p.kind == inspect.Parameter.VAR_POSITIONAL for p in params
                )

                if has_var_pos or len(pos_params) == 1:
                    result = self.func(self.report_progress)  # type: ignore[misc]
                else:
                    result = self.func()  # type: ignore[call-arg]
            except ValueError:
                # Signature unavailable (built-in/C function): call without arguments by default
                result = self.func()  # type: ignore[call-arg]
            if self._canceled:
                self.signals.canceled.emit()
                return
            self.signals.finished.emit(result)
        except Exception as e:  # noqa: BLE001
            self.signals.error.emit(e)
