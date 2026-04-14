# app/views/main_components/init_status.py
from __future__ import annotations

import logging

from app.interfaces import MainWindowLike
from app.views.widgets.status_bar import set_status_message

logger = logging.getLogger(__name__)


class StatusUpdater:
    """Safely update status messages within the main window.

    Usage:
        status = StatusUpdater(window, logger)
        status.set_message("Loading...")
    """

    def __init__(
        self, window: MainWindowLike, _logger: logging.Logger | None = None
    ) -> None:
        self._window = window
        self._logger = _logger or logger

    def set_message(self, message: str) -> None:
        if not set_status_message(self._window, message):
            self._logger.debug(
                "StatusUpdater: status bar unavailable for message '%s'", message
            )
