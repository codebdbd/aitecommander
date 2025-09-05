# app/views/main_components/init_db_gate.py
from __future__ import annotations

import logging
from typing import Callable, Optional

from PyQt6.QtCore import QTimer

logger = logging.getLogger(__name__)


class DbReadyGate:
    """Инкапсулирует ожидание готовности БД по признаку разблокировки окна.

    Считает БД готовой, когда `window.isEnabled()` возвращает True.
    Проверка выполняется периодически таймером (100 мс), пока окно заблокировано.
    """

    def __init__(self, window, _logger: Optional[logging.Logger] = None) -> None:
        self._window = window
        self._logger = _logger or logger
        self._timer: Optional[QTimer] = None

    def ensure_ready_or_wait(self, on_ready: Callable[[], None], on_waiting: Optional[Callable[[], None]] = None) -> None:
        try:
            if hasattr(self._window, 'isEnabled') and self._window.isEnabled():
                on_ready()
                return
        except Exception:
            # Если проверка упала — логируем и пытаемся продолжить, вызвав on_ready как есть
            self._logger.exception("DbReadyGate: error checking window.isEnabled, proceeding as ready")
            on_ready()
            return

        # Если не готово — оповещаем и запускаем таймер
        if on_waiting:
            try:
                on_waiting()
            except Exception:
                self._logger.debug("DbReadyGate: on_waiting callback raised", exc_info=True)

        self._timer = QTimer()
        self._timer.timeout.connect(lambda: self._check_and_continue(on_ready))
        self._timer.start(100)

    def _check_and_continue(self, on_ready: Callable[[], None]) -> None:
        try:
            if hasattr(self._window, 'isEnabled') and self._window.isEnabled():
                try:
                    if self._timer is not None:
                        self._timer.stop()
                        self._timer.deleteLater()
                        self._timer = None
                except Exception:
                    pass
                on_ready()
        except Exception:
            self._logger.exception("DbReadyGate: error during readiness check")
