# app/controllers/bootstrap.py
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.controllers.business import StructureBusinessLogic
from app.controllers.business.links_business import LinksBusinessLogic
from app.controllers.system.app_shutdown_controller import AppShutdownController
from app.controllers.ui.dialogs import (
    DatabaseController,
    LinkOperationsController,
    SystemDialogController,
)
from app.controllers.ui.links import LinksUIController
from app.controllers.ui.structure.structure_ui_controller import StructureUIController


# ✅ Added protocol for input parameter validation
@runtime_checkable
class WindowWithRequiredAttributes(Protocol):
    """Protocol for window with required attributes.
    
    Defines minimal interface that main window must provide
    for correct controller operation.
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
    """
    Creates and returns controller/business logic facade for main window.
    Expects window to have: db, tree, table, undo_stack.
    
    Args:
        window: Window with required attributes (db, tree, table, undo_stack)
        
    Returns:
        ControllersFacade: Facade with all configured controllers
        
    Raises:
        AttributeError: If window is missing required attributes
    """
    # ✅ Required attribute validation
    _validate_window_attributes(window)
    # Business logic
    structure_business = StructureBusinessLogic(window.db)
    links_business = LinksBusinessLogic(window.db)

    # UI controllers and specialized controllers
    structure_ctrl = StructureUIController(window.tree, structure_business, window)
    # Create link_operations before LinksUIController and pass as explicit dependency
    link_ops = LinkOperationsController(window.db, window.undo_stack, window)
    links_ctrl = LinksUIController(
        window.table, links_business, window, link_operations=link_ops
    )
    db_ctrl = DatabaseController(window.db, window)
    sys_dialogs = SystemDialogController(window)

    # Shutdown controller
    app_shutdown = AppShutdownController(window)

    return ControllersFacade(
        structure_business=structure_business,
        structure=structure_ctrl,
        links_business=links_business,
        links=links_ctrl,
        link_operations=link_ops,
        database_controller=db_ctrl,
        system_dialogs=sys_dialogs,
        app_shutdown=app_shutdown,
    )


def _validate_window_attributes(window: Any) -> None:
    """Validate required window attributes."""
    required_attrs = ["db", "tree", "table", "undo_stack"]
    missing_attrs = []
    
    for attr in required_attrs:
        if not hasattr(window, attr):
            missing_attrs.append(attr)
    
    if missing_attrs:
        raise AttributeError(
            f"Window is missing required attributes: {', '.join(missing_attrs)}. "
            f"Required attributes: {', '.join(required_attrs)}"
        )


def create_main_window(settings, theme_ctrl, db):
    """
    Creates main window without passing Database to constructor and runs UI initialization.

    This meets the requirement: window accepts only ready high-level dependencies,
    while low-level details (Database) don't pass through window constructor.
    """
    from app.views.main_components.initialization.window_initializer import (
        WindowInitializer,
    )
    from app.views.windows.main_window import MainWindow

    # 1) Create window with safe signature (without Database)
    window = MainWindow(settings, theme_ctrl)

    # 2) Perform UI and controller initialization through WindowInitializer
    initializer = WindowInitializer(window, db, settings, theme_ctrl)
    initializer.initialize_window()

    return window
