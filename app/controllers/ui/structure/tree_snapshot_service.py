from __future__ import annotations

import logging
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QTimer

logger = logging.getLogger(__name__)


class TreeSnapshotService(QObject):
    """Асинхронное применение снапшотов модели дерева структуры."""

    def __init__(self, *, manager, model) -> None:
        parent = manager if isinstance(manager, QObject) else None
        super().__init__(parent=parent)
        self._model = model
        self._pending: list[dict] | None = None
        self._on_success: Optional[Callable[[], None]] = None
        self._on_error: Optional[Callable[[], None]] = None

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._apply_pending_snapshot)

    def schedule_snapshot(
        self,
        snapshot: list[dict],
        *,
        on_success: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[], None]] = None,
    ) -> None:
        """Отложить применение снапшота до следующего цикла событий Qt."""
        # Создаём копию, чтобы изменения исходного списка не повлияли на применение
        self._pending = list(snapshot or [])
        self._on_success = on_success
        self._on_error = on_error
        if not self._timer.isActive():
            self._timer.start(0)

    def _apply_pending_snapshot(self) -> None:
        snapshot = self._pending or []
        on_success = self._on_success
        on_error = self._on_error
        # Сбрасываем ссылки перед выполнением, чтобы избежать повторных вызовов
        self._pending = None
        self._on_success = None
        self._on_error = None
        try:
            self._model.set_snapshot(snapshot)
        except Exception:
            logger.exception(
                "TreeSnapshotService: модель не смогла принять снапшот",
            )
            if on_error:
                try:
                    on_error()
                except Exception:
                    logger.debug(
                        "TreeSnapshotService: on_error callback failed",
                        exc_info=True,
                    )
        else:
            if on_success:
                try:
                    on_success()
                except Exception:
                    logger.debug(
                        "TreeSnapshotService: on_success callback failed",
                        exc_info=True,
                    )
