"""
Wrapper over QUndoStack with convenient methods and a macro-command context manager.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QUndoStack

from app.core.results import ErrorNotification, InvalidateRegion, Result

from .dispatcher import UndoDispatcher

logger = logging.getLogger(__name__)


class UndoManager:
    """Manages the application's undo/redo stack.

    Provides convenient methods push(), clear(), begin_macro()/end_macro(),
    and a context manager macro(name).
    """

    def __init__(self, parent: QObject | None = None) -> None:
        self.stack = QUndoStack(parent)
        self.dispatcher = UndoDispatcher(parent)

    def push(self, cmd) -> None:
        """Push a command into the stack with logging."""
        logger.debug("push: %s", getattr(cmd, "text", lambda: str(cmd))())
        self.stack.push(cmd)

    def clear(self) -> None:
        logger.debug("clear")
        self.stack.clear()

    def begin_macro(self, text: str) -> None:
        logger.debug("begin_macro: %s", text)
        self.stack.beginMacro(text)

    def end_macro(self) -> None:
        logger.debug("end_macro")
        self.stack.endMacro()

    def can_undo(self) -> bool:
        return self.stack.canUndo()

    def can_redo(self) -> bool:
        return self.stack.canRedo()

    def undo(self) -> None:
        logger.debug("undo")
        self.stack.undo()

    def redo(self) -> None:
        logger.debug("redo")
        self.stack.redo()

    @contextmanager
    def macro(self, text: str) -> Iterator[None]:
        """Context manager to group multiple operations into one."""
        self.begin_macro(text)
        try:
            yield
        finally:
            self.end_macro()

    def set_invalidate_handler(
        self, handler: Callable[[Iterable[InvalidateRegion]], None]
    ) -> None:
        """Attach invalidate handler to internal dispatcher."""

        self.dispatcher.set_invalidate_handler(handler)

    def set_notification_handler(
        self, handler: Callable[[Iterable[ErrorNotification]], None]
    ) -> None:
        """Attach notification handler to internal dispatcher."""

        self.dispatcher.set_notification_handler(handler)

    def dispatch_result(
        self,
        result: Result[object],
        *,
        on_success: Callable[[object | None], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        description: str = "unnamed-task",
    ) -> None:
        """Proxy dispatch call to the internal dispatcher."""

        self.dispatcher.dispatch(
            result,
            on_success=on_success,
            on_error=on_error,
            description=description,
        )

    # Delegate all other attributes to the inner QUndoStack
    def __getattr__(self, name: str):
        return getattr(self.stack, name)
