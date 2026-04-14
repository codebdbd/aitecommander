"""Undo dispatcher for routing results to the UI thread."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from PyQt6.QtCore import QObject, QTimer

from app.core.results import ErrorNotification, InvalidateRegion, Result

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DispatchTask:
    """Task scheduled for UI handling."""

    callback: Callable[[], None]
    description: str


class UndoDispatcher(QObject):
    """Dispatches service results to UI handlers in a serialized manner."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._queue: deque[DispatchTask] = deque()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._process_next)
        self._invalidate_handler: Callable[[Iterable[InvalidateRegion]], None] | None = None
        self._notification_handler: (
            Callable[[Iterable[ErrorNotification]], None] | None
        ) = None

    def set_invalidate_handler(
        self, handler: Callable[[Iterable[InvalidateRegion]], None]
    ) -> None:
        """Register a callback for invalidate-region processing."""

        self._invalidate_handler = handler

    def set_notification_handler(
        self, handler: Callable[[Iterable[ErrorNotification]], None]
    ) -> None:
        """Register a callback for user-facing notifications."""

        self._notification_handler = handler

    def dispatch(
        self,
        result: Result[object],
        *,
        on_success: Callable[[object | None], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        description: str = "unnamed-task",
    ) -> None:
        """Enqueue callbacks according to result status."""

        try:
            if result.is_success():
                self._enqueue_success(result, on_success, description)
            elif result.is_failure():
                self._enqueue_error(result, on_error, description)
            else:
                self._enqueue_partial(result, on_success, on_error, description)
            self._schedule()
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("UndoDispatcher.dispatch: enqueue failed")

    def _enqueue_success(
        self,
        result: Result[object],
        on_success: Callable[[object | None], None] | None,
        description: str,
    ) -> None:
        self._enqueue_metadata(result, description)
        if on_success:
            self._queue.append(
                DispatchTask(
                    callback=lambda: on_success(result.value),
                    description=f"{description}:success",
                )
            )

    def _enqueue_error(
        self,
        result: Result[object],
        on_error: Callable[[Exception], None] | None,
        description: str,
    ) -> None:
        self._enqueue_metadata(result, description)
        error = result.error or RuntimeError("Failure without error")
        if on_error:
            self._queue.append(
                DispatchTask(
                    callback=lambda: on_error(error),
                    description=f"{description}:failure",
                )
            )

    def _enqueue_partial(
        self,
        result: Result[object],
        on_success: Callable[[object | None], None] | None,
        on_error: Callable[[Exception], None] | None,
        description: str,
    ) -> None:
        self._enqueue_metadata(result, description)
        if on_success:
            self._queue.append(
                DispatchTask(
                    callback=lambda: on_success(result.value),
                    description=f"{description}:partial:success",
                )
            )
        if result.error and on_error:
            self._queue.append(
                DispatchTask(
                    callback=lambda: on_error(result.error),
                    description=f"{description}:partial:error",
                )
            )

    def _enqueue_metadata(self, result: Result[object], description: str) -> None:
        invalidate = tuple(result.invalidate_regions)
        if invalidate and self._invalidate_handler:
            self._queue.append(
                DispatchTask(
                    callback=lambda: self._invalidate_handler(invalidate),
                    description=f"{description}:invalidate",
                )
            )
        notifications = tuple(result.notifications)
        if notifications and self._notification_handler:
            self._queue.append(
                DispatchTask(
                    callback=lambda: self._notification_handler(notifications),
                    description=f"{description}:notify",
                )
            )
        for warning in result.warnings:
            logger.warning("UndoDispatcher warning (%s): %s", description, warning)

    def _schedule(self) -> None:
        if not self._timer.isActive():
            self._timer.start(0)

    def _process_next(self) -> None:
        if not self._queue:
            return
        task: DispatchTask | None = None
        try:
            task = self._queue.popleft()
            task.callback()
        except Exception:  # pragma: no cover - defensive logging
            logger.exception(
                "UndoDispatcher task failed: %s",
                task.description if task else "unknown",
            )
        finally:
            if self._queue:
                self._timer.start(0)


__all__ = ["UndoDispatcher", "DispatchTask"]
