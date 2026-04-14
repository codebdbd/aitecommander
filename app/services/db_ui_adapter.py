"""Service-layer bridge for DB helpers used by UI adapters.

Keeps UI modules from importing infrastructure-level ``app.utils.db`` directly.
"""

from __future__ import annotations

from app.utils.db.api import run_db
from app.utils.db.db_error_handler import handle_db_error
from app.utils.db.synchronization import signal_guard

__all__ = ["handle_db_error", "run_db", "signal_guard"]
