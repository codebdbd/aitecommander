# app/views/main_components/init_status.py
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class StatusUpdater:
    """Безопасное обновление сообщений статуса в главном окне.

    Использование:
        status = StatusUpdater(window, logger)
        status.set_message("Загрузка...")
    """

    def __init__(self, window, _logger: Optional[logging.Logger] = None) -> None:
        self._window = window
        self._logger = _logger or logger

    def set_message(self, message: str) -> None:
        try:
            if hasattr(self._window, "message_label") and self._window.message_label:
                self._window.message_label.setText(message)
        except (AttributeError, RuntimeError) as e:
            # Нештатная ситуация для ранней фазы — логируем на DEBUG, чтобы не шуметь в релизе
            self._logger.debug("StatusUpdater: failed to update status '%s': %s", message, e)
