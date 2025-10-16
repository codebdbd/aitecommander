# app/views/main_components/init_status.py
from __future__ import annotations

import logging
from typing import Optional

from app.interfaces import MainWindowLike

logger = logging.getLogger(__name__)


class StatusUpdater:
    """Safely update status messages within the main window.

    Usage:
        status = StatusUpdater(window, logger)
        status.set_message("Loading...")
    """

    def __init__(
        self, window: MainWindowLike, _logger: Optional[logging.Logger] = None
    ) -> None:
        self._window = window
        self._logger = _logger or logger

    def set_message(self, message: str) -> None:
        try:
            if hasattr(self._window, "message_label") and self._window.message_label:
                self._window.message_label.setText(message)
        except (AttributeError, RuntimeError) as e:
            # Unexpected state during early initialization — log at DEBUG to avoid noise
            self._logger.debug(
                "StatusUpdater: failed to update status '%s': %s", message, e
            )
