from __future__ import annotations

import logging
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QTimer

logger = logging.getLogger(__name__)


class TreeSnapshotService(QObject):
    """Asynchronous application of structure tree model snapshots."""

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
        """Defer snapshot application until the next Qt event loop cycle."""
        # Create a copy so changes to the original list won't affect application
        self._pending = list(snapshot or [])
        self._on_success = on_success
        self._on_error = on_error
        if not self._timer.isActive():
            self._timer.start(0)

    def _apply_pending_snapshot(self) -> None:
        snapshot = self._pending or []
        on_success = self._on_success
        on_error = self._on_error
        # Reset references before execution to avoid repeated calls
        self._pending = None
        self._on_success = None
        self._on_error = None
        try:
            self._model.set_snapshot(snapshot)
        except Exception:
            logger.exception(
                "TreeSnapshotService: model failed to accept snapshot",
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
