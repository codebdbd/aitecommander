# app/views/main_components/resize_logger.py
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QEvent, QObject

logger = logging.getLogger(__name__)


class ResizeLogger(QObject):
    """Логирует ограниченное число событий Resize/Move для указанного окна.

    Ведёт счётчики событий и автоматически отписывается (removeEventFilter),
    когда достигнуты лимиты по перемещениям и изменениям размера. Также
    сбрасывает на owner служебные флаги `_diag_resize_logger` и
    `_diag_resize_logger_installed`, если они установлены на него.
    """

    def __init__(self, owner: QObject, parent: Optional[QObject] = None) -> None:
        super().__init__(parent or owner)
        self._owner = owner
        self._resizes = 0
        self._moves = 0
        # Конфигурируемые лимиты через app_config, с безопасными дефолтами
        try:
            from app.config_data import app_config as _cfg  # lazy import to avoid cycles

            self._max_resizes = int(getattr(_cfg, "get", lambda *_: 5)("diag.resize_log.max_resizes", 5))
            self._max_moves = int(getattr(_cfg, "get", lambda *_: 5)("diag.resize_log.max_moves", 5))
        except Exception:
            self._max_resizes = 5
            self._max_moves = 5

    def _maybe_uninstall(self, obj: QObject) -> None:
        try:
            if self._resizes >= self._max_resizes and self._moves >= self._max_moves:
                try:
                    obj.removeEventFilter(self)
                except Exception:
                    logger.debug(
                        "ResizeLogger: removeEventFilter failed",
                        exc_info=True,
                    )
                try:
                    if (
                        hasattr(self._owner, "_diag_resize_logger")
                        and getattr(self._owner, "_diag_resize_logger", None) is self
                    ):
                        setattr(self._owner, "_diag_resize_logger", None)  # type: ignore[attr-defined]
                        setattr(self._owner, "_diag_resize_logger_installed", False)  # type: ignore[attr-defined]
                except Exception:
                    logger.debug(
                        "ResizeLogger: failed to reset owner flags",
                        exc_info=True,
                    )
        except Exception:
            logger.debug("ResizeLogger: _maybe_uninstall failed", exc_info=True)

    def eventFilter(self, obj: QObject, event) -> bool:  # type: ignore[override]
        et = event.type()
        try:
            if et == QEvent.Type.Resize and self._resizes < self._max_resizes:
                self._resizes += 1
                try:
                    sz = getattr(obj, "size", lambda: None)()
                    size_s = f"{sz.width()}x{sz.height()}" if sz is not None else "?"
                except Exception:
                    size_s = "?"
                logger.info("DiagTopLevels: Resize #%s -> %s", self._resizes, size_s)
                self._maybe_uninstall(obj)
            elif et == QEvent.Type.Move and self._moves < self._max_moves:
                self._moves += 1
                try:
                    pos = getattr(obj, "pos", lambda: None)()
                    pos_s = f"({pos.x()},{pos.y()})" if pos is not None else "?"
                except Exception:
                    pos_s = "?"
                logger.info("DiagTopLevels: Move #%s -> %s", self._moves, pos_s)
                self._maybe_uninstall(obj)
        except Exception:
            logger.debug("ResizeLogger: eventFilter failed", exc_info=True)
        return QObject.eventFilter(self, obj, event)
