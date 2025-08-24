"""
Централизованная база для undo/redo команд.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtGui import QUndoCommand

logger = logging.getLogger(__name__)


class BaseCommand(QUndoCommand):
    """Базовая команда с единым логированием и безопасными хуками.

    Все наследники должны переопределять redo() и undo().
    """

    def __init__(self, text: str = "", main_window: Optional[object] = None) -> None:
        super().__init__(text)
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
        except (
            Exception
        ):  # совместимость, если унаследованные классы переопределяют поведение
            pass


def log_command(fn):
    """Декоратор для логирования выполнения команд."""

    def wrapper(self: BaseCommand, *args, **kwargs):
        logger.debug("%s.%s: start", self.__class__.__name__, fn.__name__)
        try:
            result = fn(self, *args, **kwargs)
            logger.debug("%s.%s: done", self.__class__.__name__, fn.__name__)
            return result
        except Exception as exc:
            logger.exception(
                "%s.%s: error: %s", self.__class__.__name__, fn.__name__, exc
            )
            raise

    return wrapper
