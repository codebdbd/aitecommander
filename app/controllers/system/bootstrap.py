"""Legacy controller bootstrap helpers (deprecated)."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.controllers.business import StructureBusinessLogic
from app.controllers.business.links_business import LinksBusinessLogic
from app.controllers.system.app_shutdown_controller import AppShutdownController
from app.controllers.system.window_setup.coordinator import setup_controllers
from app.controllers.ui.dialogs import (
    DatabaseController,
    LinkOperationsController,
    SystemDialogController,
)
from app.controllers.ui.links import LinksUIController
from app.controllers.ui.structure.structure_ui_controller import StructureUIController


@runtime_checkable
class WindowWithRequiredAttributes(Protocol):
    """Protocol for window with required attributes.

    Defines minimal interface that main window must provide for correct operation.
    """

    db: Any  # Database instance
    tree: Any  # QTreeView for structure
    table: Any  # QTableView for links
    undo_stack: Any  # QUndoStack for operations


@dataclass
class ControllersFacade:
    structure_business: StructureBusinessLogic
    structure: StructureUIController
    links_business: LinksBusinessLogic
    links: LinksUIController
    link_operations: LinkOperationsController
    database_controller: DatabaseController
    system_dialogs: SystemDialogController
    app_shutdown: AppShutdownController


def build_controllers(window: WindowWithRequiredAttributes) -> ControllersFacade:
    """Deprecated; use window_setup.WindowControllersSetup instead."""
    warnings.warn(
        "build_controllers() is deprecated; use window_setup coordinator instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    _validate_window_attributes(window)
    controllers: dict[str, Any] = {}
    setup_controllers(window, controllers, window.db)

    # Legacy path lacked WindowFacade wiring; replicate the modern setup so
    # shortcut handlers that rely on window.facade keep working.
    try:
        from app.controllers.ui.window_facade import WindowFacade

        window.facade = WindowFacade(  # type: ignore[attr-defined]
            structure=window.structure,  # type: ignore[attr-defined]
            links_actions=window.links_actions,  # type: ignore[attr-defined]
            ui_state=window.ui_state,  # type: ignore[attr-defined]
            action_controller=window.action_controller,  # type: ignore[attr-defined]
            theme_ctrl=window.theme_ctrl,  # type: ignore[attr-defined]
        )
    except Exception:
        warnings.warn(
            "build_controllers(): failed to initialize WindowFacade; "
            "keyboard shortcuts may not work correctly in this legacy mode.",
            RuntimeWarning,
            stacklevel=2,
        )

    return ControllersFacade(
        structure_business=controllers["structure_business"],
        structure=controllers["structure"],
        links_business=controllers["links_business"],
        links=controllers["links"],
        link_operations=controllers["link_operations"],
        database_controller=controllers["database_controller"],
        system_dialogs=controllers["system_dialogs"],
        app_shutdown=controllers["app_shutdown"],
    )


def _validate_window_attributes(window: Any) -> None:
    """Validate required window attributes."""
    required_attrs = ["db", "tree", "table", "undo_stack"]
    missing_attrs = [attr for attr in required_attrs if not hasattr(window, attr)]
    if missing_attrs:
        raise AttributeError(
            f"Window is missing required attributes: {', '.join(missing_attrs)}. "
            f"Required attributes: {', '.join(required_attrs)}"
        )


def create_main_window(settings, theme_ctrl, db):
    """Create main window and run window initializer (legacy helper)."""
    warnings.warn(
        "create_main_window() is deprecated; use app.startup.runtime instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    from app.views.main_components.initialization.window_initializer import (
        WindowInitializer,
    )
    from app.views.windows.main_window import MainWindow

    window = MainWindow(settings, theme_ctrl)
    initializer = WindowInitializer(window, db, settings, theme_ctrl)
    initializer.initialize_window()
    return window
