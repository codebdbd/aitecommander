"""
Common helper undo/redo commands for centralized usage.
"""

from __future__ import annotations

from typing import Callable, Optional

from .base import BaseCommand, log_command


class NoopCommand(BaseCommand):
    """No-op command: does nothing, useful for macro alignment."""

    @log_command
    def _noop(self) -> None:
        return None

    # Avoid duplication: use the same no-op for both actions
    redo = _noop
    undo = _noop


class MacroCommand(BaseCommand):
    """Wrapper command that executes provided callbacks in redo/undo.

    Convenient for simple changes when creating a separate class is unnecessary.
    """

    def __init__(
        self,
        text: str,
        redo_fn: Callable[[], None],
        undo_fn: Callable[[], None],
        main_window: Optional[object] = None,
    ) -> None:
        super().__init__(text, main_window)
        self._redo_fn = redo_fn
        self._undo_fn = undo_fn

    @log_command
    def redo(self) -> None:
        self._redo_fn()

    @log_command
    def undo(self) -> None:
        self._undo_fn()
