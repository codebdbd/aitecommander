"""Database ready lifecycle coordinator service."""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class DatabaseReadyService(QObject):
    """Tracks whether database initialization is ready or failed, emitting signals once."""

    ready = pyqtSignal()
    failed = pyqtSignal(Exception)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._is_ready: bool = False
        self._error: Optional[Exception] = None

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    @property
    def error(self) -> Optional[Exception]:
        return self._error

    def mark_ready(self) -> None:
        if self._is_ready or self._error is not None:
            return
        self._is_ready = True
        logger.info("DatabaseReadyService: database marked as ready")
        self.ready.emit()

    def mark_failed(self, error: Exception) -> None:
        if self._is_ready or self._error is not None:
            return
        self._error = error
        logger.error("DatabaseReadyService: database marked as failed: %s", error)
        self.failed.emit(error)
