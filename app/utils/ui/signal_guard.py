"""UI-facing adapter for signal guard decorator.

Keeps UI modules from importing database synchronization internals directly.
"""

from __future__ import annotations

from app.services.db_ui_adapter import signal_guard

__all__ = ["signal_guard"]
