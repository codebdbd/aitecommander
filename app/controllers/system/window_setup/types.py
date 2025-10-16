"""
Types and protocols for main window controller setup.
"""

from typing import Any, Protocol, TypedDict, runtime_checkable

from app.controllers.business import StructureBusinessLogic
from app.controllers.business.links_business import LinksBusinessLogic
from app.controllers.system.app_shutdown_controller import AppShutdownController


# ✅ Strict protocols for typing
@runtime_checkable
class DatabaseProtocol(Protocol):
    """Protocol for database with detailed interface."""
    
    def __enter__(self): ...
    def __exit__(self, *args): ...
    
    # Data models
    spheres: Any
    sections: Any  
    categories: Any
    links: Any


@runtime_checkable
class QTreeViewProtocol(Protocol):
    """Protocol for structure tree."""
    
    def selectionModel(self): ...


@runtime_checkable
class QTableViewProtocol(Protocol):
    """Protocol for links table."""
    
    def selectionModel(self): ...
    def get_link_at(self, row: int): ...


@runtime_checkable
class QUndoStackProtocol(Protocol):
    """Protocol for undo operations stack."""
    
    def push(self, command): ...


@runtime_checkable
class WindowProtocol(Protocol):
    """Strictly typed protocol for application main window."""
    
    # Interface methods
    def get_current_category_id(self) -> int | None: ...
    def update_statusbar(self) -> None: ...
    def on_structure_item_changed(self, *args) -> None: ...
    def on_structure_item_added(self, *args) -> None: ...
    
    # Required attributes with specific types
    db: DatabaseProtocol
    tree: QTreeViewProtocol
    table: QTableViewProtocol
    undo_stack: QUndoStackProtocol
    tiles: Any  # CategoryTilesWidget
    fav_widget: Any  # FavoritesPanelWidget
    recent_links_widget: Any  # RecentPanelWidget


# ✅ TypedDict for structured data
class ControllersDict(TypedDict, total=False):
    """Typed dictionary of controllers."""
    structure_business: StructureBusinessLogic
    structure: Any  # StructureUIController
    links_business: LinksBusinessLogic
    links: Any  # LinksUIController
    link_operations: Any  # LinkOperationsController
    database_controller: Any  # DatabaseController
    system_dialogs: Any  # SystemDialogController
    app_shutdown: AppShutdownController
    ui_state: Any  # UIStateManager
    category_tiles_controller: Any  # CategoryTilesController
    links_table_controller: Any  # LinksTableController
    action_controller: Any  # ActionController
    spheres_controller: Any  # SpheresBarController
    top_panels_controller: Any  # TopPanelsController
    links_actions: Any  # LinksActions


class SetupError(Exception):
    """Window component setup errors."""
