"""
Thin facade for main window controller setup.

Main logic is moved to modules:
- app.controllers.system.window_setup.types - types and protocols
- app.controllers.system.window_setup.business - business logic and UI setup
- app.controllers.system.window_setup.wiring - signal connections
- app.controllers.system.window_setup.coordinator - setup coordinator

This module provides only public API and helper functions.
"""

import logging

from app.controllers.business import StructureBusinessLogic
from app.controllers.system.window_setup.coordinator import (
    WindowControllersSetup,
    setup_controllers,
)
from app.controllers.system.window_setup.keyboard import (
    setup_keyboard,
)
from app.controllers.system.window_setup.types import (
    SetupError,
)
from app.controllers.system.window_setup.ui import (
    setup_dependency_injection,
    setup_ui_elements,
)
from app.controllers.system.window_setup.wiring import (
    DatabaseEventHandler,
    setup_signal_connections,
)
from app.controllers.system.window_setup.wiring import (
    _connect_structure_signals as _new_connect_structure_signals,
)
from app.controllers.system.window_setup.wiring import (
    _connect_top_panels_signals_explicit as _new_connect_top_panels_signals_explicit,
)
from app.controllers.system.window_setup.wiring import (
    _on_structure_changed_schedule_refresh as _new_on_structure_changed_schedule_refresh,
)

logger = logging.getLogger(__name__)


def _resolve_structure_loader(structure_business: StructureBusinessLogic):
    """Return callable for structure loading: load_structure_async or load_structure.

    Strictly typed loader search: check method presence via hasattr
    and immediately raise SetupError if both methods are missing.
    """
    # Check for loading methods presence before attempting to use them
    has_async = hasattr(structure_business, "load_structure_async")
    has_sync = hasattr(structure_business, "load_structure")

    if not has_async and not has_sync:
        raise SetupError(
            "StructureBusinessLogic must provide load_structure_async() or load_structure()"
        )

    try:
        # Priority to async method if available
        if has_async:
            loader = structure_business.load_structure_async  # type: ignore[attr-defined]
            if not callable(loader):
                raise SetupError(
                    "StructureBusinessLogic.load_structure_async must be callable"
                )
            return loader

        if has_sync:
            loader = structure_business.load_structure  # type: ignore[attr-defined]
            if not callable(loader):
                raise SetupError(
                    "StructureBusinessLogic.load_structure must be callable"
                )
            return loader

    except SetupError:
        # SetupError already contains informative message - re-raise as is
        raise
    except Exception as e:
        logger.exception("Unexpected error while resolving structure loader")
        raise SetupError(
            "Failed to resolve structure loader due to unexpected error"
        ) from e

    # This code should never execute due to checks above
    raise SetupError("Internal error: structure loader resolution failed")


def _connect_structure_signals(*args, **kwargs):
    """Backward-compatible wrapper around the refactored implementation."""
    return _new_connect_structure_signals(*args, **kwargs)


def _connect_top_panels_signals_explicit(*args, **kwargs):
    """Backward-compatible wrapper around the refactored implementation."""
    return _new_connect_top_panels_signals_explicit(*args, **kwargs)


def _on_structure_changed_schedule_refresh(*args, **kwargs):
    """Backward-compatible wrapper around the refactored implementation."""
    return _new_on_structure_changed_schedule_refresh(*args, **kwargs)


__all__ = [
    "setup_controllers",
    "setup_ui_elements", 
    "setup_dependency_injection",
    "setup_signal_connections",
    "setup_keyboard",
    "WindowControllersSetup",
    "_resolve_structure_loader",
    "DatabaseEventHandler",
    "_connect_structure_signals",
    "_connect_top_panels_signals_explicit",
    "_on_structure_changed_schedule_refresh",
]
