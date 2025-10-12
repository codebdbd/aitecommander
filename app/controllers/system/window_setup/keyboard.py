"""
Keyboard and hotkey setup.
"""

import logging
from typing import Any

from app.controllers.system.keyboard_manager import KeyboardManager

logger = logging.getLogger(__name__)


def setup_keyboard(window: Any, controllers: dict[str, Any]) -> None:
    """Set up centralized hotkey management."""
    window.keyboard_manager = KeyboardManager(window)
