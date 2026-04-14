"""UI-facing adapter for DB synchronization helpers.

Keeps UI modules from importing infrastructure helpers directly.
"""

from __future__ import annotations

from app.services.db_ui_adapter import signal_guard

__all__ = ["signal_guard"]
