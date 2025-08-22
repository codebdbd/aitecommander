"""
Обёртка над QUndoStack с удобными методами и контекст-менеджером макрокоманд.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator, Optional

from PyQt6.QtGui import QUndoStack


class UndoManager:
    """Управляет undo/redo стеком приложения.

    Предоставляет удобные методы push(), clear(), begin_macro()/end_macro(),
    а также контекст-менеджер macro(name).
    """

    def __init__(self, parent: Optional[object] = None) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.stack = QUndoStack(parent)

    def push(self, cmd) -> None:
        """Добавляет команду в стек c логированием."""
        self.logger.debug("push: %s", getattr(cmd, 'text', lambda: str(cmd))())
        self.stack.push(cmd)

    def clear(self) -> None:
        self.logger.debug("clear")
        self.stack.clear()

    def begin_macro(self, text: str) -> None:
        self.logger.debug("begin_macro: %s", text)
        self.stack.beginMacro(text)

    def end_macro(self) -> None:
        self.logger.debug("end_macro")
        self.stack.endMacro()

    def can_undo(self) -> bool:
        return self.stack.canUndo()

    def can_redo(self) -> bool:
        return self.stack.canRedo()

    def undo(self) -> None:
        self.logger.debug("undo")
        self.stack.undo()

    def redo(self) -> None:
        self.logger.debug("redo")
        self.stack.redo()

    @contextmanager
    def macro(self, text: str) -> Iterator[None]:
        """Контекст-менеджер для группировки нескольких операций в одну."""
        self.begin_macro(text)
        try:
            yield
        finally:
            self.end_macro()

    # Делегирование всех остальных атрибутов к внутреннему QUndoStack
    def __getattr__(self, name):
        return getattr(self.stack, name)
