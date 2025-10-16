"""
Centralized base for undo/redo commands.
"""

from __future__ import annotations

import logging

from PyQt6.QtGui import QUndoCommand

logger = logging.getLogger(__name__)


class BaseCommand(QUndoCommand):
    """Base command with unified logging and safe hooks.

    All subclasses must override redo() and undo().
    """

    def __init__(self, text: str = "", main_window: object | None = None) -> None:
        super().__init__(text)
        self.main = main_window
        if text:
            self.setText(text)

    # Note: QUndoCommand calls redo() automatically on push()
    def redo(self) -> None:  # noqa: D401 - документируется в наследниках
        raise NotImplementedError

    def undo(self) -> None:  # noqa: D401 - документируется в наследниках
        raise NotImplementedError

    # Utility to mark a command as obsolete/non-state-changing
    def set_obsolete(self, value: bool = True) -> None:
        try:
            self.setObsolete(value)
        except Exception:  # compatibility if subclasses override behavior
            pass


def log_command(fn):
    """Decorator for logging command execution."""

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
