# app/controllers/system/__init__.py
# Subpackage for application-level system controllers (lifecycle, setup)

from .app_shutdown_controller import (
    AppShutdownController,
    ShutdownPriority,
    ShutdownTimeoutError,
)
from .bootstrap import ControllersFacade, build_controllers  # re-export for convenience
from .window_controllers_setup import WindowControllersSetup

__all__ = [
    'ControllersFacade',
    'build_controllers',
    'WindowControllersSetup',
    'AppShutdownController',
    'ShutdownPriority',
    'ShutdownTimeoutError',
]
