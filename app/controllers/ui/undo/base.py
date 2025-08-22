"""
Централизованная база для undo/redo команд.
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtGui import QUndoCommand


class BaseCommand(QUndoCommand):
    """Базовая команда с единым логированием и безопасными хуками.

    Все наследники должны переопределять redo() и undo().
    """

    def __init__(self, text: str = "", main_window: Optional[object] = None) -> None:
        super().__init__(text)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.main = main_window
        if text:
            self.setText(text)

    # Примечание: QUndoCommand вызывает redo() автоматически при push()
    def redo(self) -> None:  # noqa: D401 - документируется в наследниках
        raise NotImplementedError

    def undo(self) -> None:  # noqa: D401 - документируется в наследниках
        raise NotImplementedError

    # Утилита для пометки команды как устаревшей/неизменяющей состояние
    def set_obsolete(self, value: bool = True) -> None:
        try:
            self.setObsolete(value)
        except Exception:  # совместимость, если унаследованные классы переопределяют поведение
            pass


def log_command(fn):
    """Декоратор для логирования выполнения команд."""
    def wrapper(self: BaseCommand, *args, **kwargs):
        self.logger.debug("%s: start", fn.__name__)
        try:
            result = fn(self, *args, **kwargs)
            self.logger.debug("%s: done", fn.__name__)
            return result
        except Exception as exc:
            self.logger.exception("%s: error: %s", fn.__name__, exc)
            raise
    return wrapper
