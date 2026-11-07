"""
Keyboard and hotkey setup.
"""

import logging
from typing import Any

from app.controllers.system.app_shutdown_controller import ShutdownPriority
from app.controllers.system.keyboard_manager import KeyboardManager
from app.controllers.ui.command_palette_controller import CommandPaletteController

logger = logging.getLogger(__name__)


def setup_keyboard(window: Any, controllers: dict[str, Any]) -> None:
    """Set up centralized hotkey management and global Command Palette."""
    window.keyboard_manager = KeyboardManager(window)
    try:
        db = getattr(window, "db", None)
        cp_ctrl = CommandPaletteController(window, db=db)
        window.command_palette_controller = cp_ctrl
        controllers["command_palette_controller"] = cp_ctrl

        app_shutdown = getattr(window, "app_shutdown", None)
        if app_shutdown is not None and hasattr(app_shutdown, "add_shutdown_handler"):
            app_shutdown.add_shutdown_handler(
                "command_palette_cleanup",
                cp_ctrl.cleanup,
                ShutdownPriority.HIGH,
                timeout=500,
                critical=False,
            )
    except Exception:
        logger.warning("Failed to initialize CommandPaletteController", exc_info=True)
