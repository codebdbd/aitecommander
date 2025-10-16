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


# ✅ Добавлен протокол для валидации входных параметров
@runtime_checkable
class WindowWithRequiredAttributes(Protocol):
    """Протокол для окна с обязательными атрибутами.
    
    Определяет минимальный интерфейс, который должно предоставлять главное окно
    для корректной работы контроллеров.
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
    Создаёт и возвращает фасад контроллеров/бизнес-логики для главного окна.
    Ожидает, что у окна есть: db, tree, table, undo_stack.
    
    Args:
        window: Окно с обязательными атрибутами (db, tree, table, undo_stack)
        
    Returns:
        ControllersFacade: Фасад со всеми настроенными контроллерами
        
    Raises:
        AttributeError: Если у окна отсутствуют обязательные атрибуты
    """
    # ✅ Валидация обязательных атрибутов
    _validate_window_attributes(window)
    # Бизнес-логика
    structure_business = StructureBusinessLogic(window.db)
    links_business = LinksBusinessLogic(window.db)

    # UI-контроллеры и специализированные контроллеры
    structure_ctrl = StructureUIController(window.tree, structure_business, window)
    # Создаём link_operations до LinksUIController и передаём как явную зависимость
    link_ops = LinkOperationsController(window.db, window.undo_stack, window)
    links_ctrl = LinksUIController(
        window.table, links_business, window, link_operations=link_ops
    )
    db_ctrl = DatabaseController(window.db, window)
    sys_dialogs = SystemDialogController(window)

    # Контроллер завершения
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
    """Валидация обязательных атрибутов окна."""
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
    Создаёт главное окно без передачи Database в конструктор и запускает инициализацию UI.

    Это соответствует требованию: окно принимает только готовые зависимости верхнего уровня,
    а низкоуровневые детали (Database) не проходят через конструктор окна.
    """
    from app.views.main_components import WindowInitializer
    from app.views.main_window import MainWindow

    # 1) Создаём окно с безопасной сигнатурой (без Database)
    window = MainWindow(settings, theme_ctrl)

    # 2) Выполняем инициализацию UI и контроллеров через WindowInitializer
    initializer = WindowInitializer(window, db, settings, theme_ctrl)
    initializer.initialize_window()

    return window
