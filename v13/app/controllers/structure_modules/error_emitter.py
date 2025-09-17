# app/controllers/structure_modules/error_emitter.py

from __future__ import annotations

import logging
from typing import Callable, Optional


class ErrorEmitter:
    """Единая точка обработки и эмиссии ошибок для бизнес-логики структуры.

    Сохраняет поведение: логирует ошибку и эмитит сигнал (title, message).
    Не зависит от Qt напрямую — сигнал передаётся коллбеком.
    """

    def __init__(
        self,
        emit_error: Callable[[str, str], None],
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._emit_error = emit_error
        self._logger = logger or logging.getLogger(__name__)

    def handle(self, title: str, error: Exception) -> None:
        msg = str(error)
        self._logger.error("%s: %s", title, msg, exc_info=True)
        self.emit(title, msg)

    def emit(self, title: str, message: str) -> None:
        self._emit_error(title, message)
        # Дублируем запись в лог, сохраняя прежнее поведение
        self._logger.error("%s: %s", title, message)
