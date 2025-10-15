"""
Coordinator for setting up controllers and components of the main window.
"""

import logging
from typing import Any

from .business import (
    _assign_controllers_to_window,
    _setup_business_logic,
    _setup_dialog_controllers,
    _setup_links_controllers,
    _setup_shutdown_controller,
    _setup_structure_controllers,
    _setup_ui_state_and_tiles,
    _validate_qt_context,
)
from .keyboard import setup_keyboard
from .types import SetupError
from .ui import setup_dependency_injection, setup_ui_elements
from .wiring import setup_signal_connections

logger = logging.getLogger(__name__)


def setup_controllers(window: Any, controllers: dict[str, Any], db: Any) -> None:
    """Create and set up main controllers."""
    _validate_qt_context()

    _setup_business_logic(controllers, db)
    _setup_ui_state_and_tiles(window, controllers)
    _setup_structure_controllers(window, controllers)
    _setup_links_controllers(window, controllers, db)
    _setup_dialog_controllers(window, controllers, db)
    _setup_shutdown_controller(window, controllers)
    _assign_controllers_to_window(window, controllers)


class WindowControllersSetup:
    """Coordinator for setting up controllers and components of the main window."""

    def __init__(self, window_initializer: Any):
        self.window_initializer = window_initializer
        self.window = window_initializer.window
        self.db = window_initializer.db

    def setup_controllers(self) -> None:
        """Set up controllers and components."""
        controllers: dict[str, Any] = {}

        try:
            setup_controllers(self.window, controllers, self.db)
            logger.info("Controllers setup completed")
        except Exception as e:
            logger.error("Failed to setup controllers: %s", e)
            raise SetupError(
                "Critical component ControllersSetup failed to initialize"
            ) from e

        # Initialize WindowFacade after creating controllers
        try:
            self._init_window_facade()
            logger.info("WindowFacade initialized")
        except Exception as e:
            logger.error("Failed to initialize WindowFacade: %s", e)
            raise SetupError("WindowFacade initialization failed") from e

        for name, step in (
            ("UIElementsSetup", setup_ui_elements),
            ("DependencyInjectionSetup", setup_dependency_injection),
            ("SignalConnectionSetup", setup_signal_connections),
            ("KeyboardSetup", setup_keyboard),
        ):
            try:
                if step is setup_signal_connections:
                    step(
                        self.window,
                        controllers,
                        top_panels_controller=self.window.top_panels_controller,
                    )
                else:
                    step(self.window, controllers)
                logger.info("%s completed", name)
            except (AttributeError, TypeError, ValueError, SetupError) as e:
                logger.error("%s failed: %s", name, e)
                raise SetupError(f"{name} failed during window setup") from e

    def _init_window_facade(self) -> None:
        """Initialize WindowFacade to simplify delegation."""
        from app.controllers.ui.window_facade import WindowFacade

        # Check for required controllers
        required_controllers = [
            "structure",
            "links_actions",
            "ui_state",
            "action_controller",
            "theme_ctrl",
        ]

        for ctrl_name in required_controllers:
            if not hasattr(self.window, ctrl_name):
                raise SetupError(
                    f"Cannot initialize WindowFacade: missing controller '{ctrl_name}'"
                )

        # Create facade
        self.window.facade = WindowFacade(
            structure=self.window.structure,
            links_actions=self.window.links_actions,
            ui_state=self.window.ui_state,
            action_controller=self.window.action_controller,
            theme_ctrl=self.window.theme_ctrl,
        )

        logger.debug("WindowFacade created with all controllers")

    def initialize_spheres(self):
        """Initialize spheres."""
        try:
            sc = getattr(self.window, "spheres_controller", None)
            if sc is None:
                from app.controllers.ui.structure.spheres_bar_controller import (
                    SpheresBarController,
                )

                sc = SpheresBarController(self.window)
                self.window.spheres_controller = sc
            sc.init()
        except (AttributeError, TypeError, ValueError) as e:
            logger.error("Failed to initialize spheres: %s", e)
            raise SetupError("Spheres initialization failed") from e
