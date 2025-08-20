# app/controllers/system/__init__.py
# Subpackage for application-level system controllers (lifecycle, setup)

from .bootstrap import ControllersFacade, build_controllers  # re-export for convenience
from .window_controllers_setup import WindowControllersSetup
from .app_shutdown_controller import AppShutdownController, ShutdownPriority, ShutdownTimeoutError
