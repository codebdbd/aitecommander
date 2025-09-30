"""
Типы и протоколы для настройки контроллеров главного окна.
"""

from typing import Any, Protocol, runtime_checkable, TypedDict

from app.controllers.business import StructureBusinessLogic
from app.controllers.business.links_business import LinksBusinessLogic
from app.controllers.system.app_shutdown_controller import AppShutdownController


# ✅ Строгие протоколы для типизации
@runtime_checkable
class DatabaseProtocol(Protocol):
    """Протокол для базы данных с детальным интерфейсом."""
    
    def __enter__(self): ...
    def __exit__(self, *args): ...
    
    # Модели данных
    spheres: Any
    sections: Any  
    categories: Any
    links: Any


@runtime_checkable
class QTreeViewProtocol(Protocol):
    """Протокол для дерева структуры."""
    
    def selectionModel(self): ...


@runtime_checkable
class QTableViewProtocol(Protocol):
    """Протокол для таблицы ссылок."""
    
    def selectionModel(self): ...
    def get_link_at(self, row: int): ...


@runtime_checkable
class QUndoStackProtocol(Protocol):
    """Протокол для стека отмены операций."""
    
    def push(self, command): ...


@runtime_checkable
class WindowProtocol(Protocol):
    """Строго типизированный протокол для главного окна приложения."""
    
    # Методы интерфейса
    def get_current_category_id(self) -> int | None: ...
    def update_statusbar(self) -> None: ...
    def on_structure_item_changed(self, *args) -> None: ...
    def on_structure_item_added(self, *args) -> None: ...
    
    # Обязательные атрибуты с конкретными типами
    db: DatabaseProtocol
    tree: QTreeViewProtocol
    table: QTableViewProtocol
    undo_stack: QUndoStackProtocol
    tiles: Any  # CategoryTilesWidget
    fav_widget: Any  # FavoritesPanelWidget
    recent_links_widget: Any  # RecentPanelWidget


# ✅ TypedDict для структурированных данных
class ControllersDict(TypedDict, total=False):
    """Типизированный словарь контроллеров."""
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
    """Ошибки настройки компонентов окна."""
