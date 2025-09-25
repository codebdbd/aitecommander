"""
Настройка клавиатуры и горячих клавиш.
"""

import logging
from typing import Any, Dict

from app.controllers.system.keyboard_manager import KeyboardManager

logger = logging.getLogger(__name__)


def setup_keyboard(window: Any, controllers: Dict[str, Any]) -> None:
    """Настроить централизованное управление горячими клавишами."""
    window.keyboard_manager = KeyboardManager(window)
