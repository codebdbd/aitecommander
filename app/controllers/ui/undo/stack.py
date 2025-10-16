"""
Wrapper over QUndoStack with convenient methods and a macro-command context manager.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator, Optional

from PyQt6.QtGui import QUndoStack

logger = logging.getLogger(__name__)


class UndoManager:
    """Manages the application's undo/redo stack.

    Provides convenient methods push(), clear(), begin_macro()/end_macro(),
    and a context manager macro(name).
    """

    def __init__(self, parent: Optional[object] = None) -> None:
        self.stack = QUndoStack(parent)

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

    # Delegate all other attributes to the inner QUndoStack
    def __getattr__(self, name):
        return getattr(self.stack, name)
