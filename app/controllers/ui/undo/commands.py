"""
Общие вспомогательные undo/redo-команды для централизованного использования.
"""

from __future__ import annotations

from typing import Callable, Optional

from .base import BaseCommand, log_command


class NoopCommand(BaseCommand):
    """Команда-заглушка: ничего не делает, полезна для выравнивания макросов."""

    @log_command
    def _noop(self) -> None:
        return None

    # Избегаем дублирования: используем один и тот же no-op для обоих действий
    redo = _noop
    undo = _noop


class MacroCommand(BaseCommand):
    """Команда-обёртка, которая выполняет переданные колбэки в redo/undo.

    Удобна для простых изменений, когда нет смысла выделять отдельный класс.
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
