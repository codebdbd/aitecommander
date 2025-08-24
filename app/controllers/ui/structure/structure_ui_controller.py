# app/controllers/structure/structure_ui_controller.py

from PyQt6.QtCore import (  # Импортируем Qt и QSize из QtCore
    QObject,
    QSize,
    Qt,
    pyqtSignal,
)
from PyQt6.QtWidgets import QAbstractItemView, QTreeWidget

from app.config_data import app_config

from .icon_handling import IconHandling
from .item_operations import ItemOperations
from .selection_handling import SelectionHandling
from .tree_management import TreeManagement

# Используем строковые литералы "section" и "category"


class StructureUIController(QObject):
    item_changed = pyqtSignal(str, int, dict)
    item_added = pyqtSignal(
        str, int, dict
    )  # Исправлено: object → int для согласованности с Business Layer

    def __init__(self, tree_widget: QTreeWidget, business_logic, main_window):
        super().__init__()
        self.tree = tree_widget
        self.business = business_logic
        self.main = main_window
        self.undo_stack = main_window.undo_stack

        # Изменяем порядок: сначала icon_handler, затем tree_manager
        self.icon_handler = IconHandling(self)
        self.selection_handler = SelectionHandling(self)
        self.item_ops = ItemOperations(self)
        self.tree_manager = TreeManagement(self)  # TreeManagement после IconHandling

        self._setup_tree()
        self._connect_business_signals()

    def _setup_tree(self) -> None:
        self.tree.setHeaderHidden(True)
        # Размер иконок в дереве — из конфигурации (ui.tree_icon_size)
        try:
            w, h = app_config.get_tree_icon_size()
            self.tree.setIconSize(QSize(int(w), int(h)))
        except Exception:
            # Fallback на безопасное значение
            self.tree.setIconSize(QSize(28, 28))
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.currentItemChanged.connect(self.selection_handler._on_current_changed)

    def _connect_business_signals(self) -> None:
        self.business.structure_loaded.connect(self.tree_manager._on_structure_loaded)
        self.business.item_added.connect(self.tree_manager._on_item_added)
        self.business.item_updated.connect(self.tree_manager._on_item_updated)
        self.business.item_deleted.connect(self.tree_manager._on_item_deleted)
        self.business.section_selected.connect(
            self.selection_handler._on_section_selected
        )
        self.business.category_selected.connect(
            self.selection_handler._on_category_selected
        )
        self.business.error_occurred.connect(self.selection_handler._on_error_occurred)

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = self.main.menu_controller.create_structure_context_menu(
            self.tree,
            item,
            delete_item_cb=self.item_ops.delete_item,
            add_new_section_cb=self.item_ops.add_new_section,
            sort_tree_cb=self.tree_manager._sort_tree,
        )
        menu.popup(self.tree.viewport().mapToGlobal(pos))

    # Публичные методы
    def load(self, item_to_select=None) -> None:
        self.item_ops.load(item_to_select)

    def switch_sphere(self, sphere_id: int) -> None:
        self.item_ops.switch_sphere(sphere_id)

    def switch_to_next_sphere(self) -> None:
        """Переключается на следующую сферу, используя бизнес-логику."""
        next_sphere_id = self.business.get_next_sphere_id()
        if next_sphere_id is not None:
            self.switch_sphere(next_sphere_id)

    def add_new_section(self) -> None:
        self.item_ops.add_new_section()

    def add_new_category(self) -> None:
        self.item_ops.add_new_category()

    def edit_item(self, item) -> None:
        self.item_ops.edit_item(item)

    def edit_selected_item(self) -> None:
        self.item_ops.edit_selected_item()

    def delete_item(self, item) -> None:
        self.item_ops.delete_item(item)

    def delete_selected_item(self) -> None:
        self.item_ops.delete_selected_item()

    def reload_icons(self) -> None:
        self.icon_handler.reload_icons()

    def handle_edit_category(self, category_id: int) -> None:
        self.item_ops.handle_edit_category(category_id)

    def handle_delete_category(self, category_id: int) -> None:
        self.item_ops.handle_delete_category(category_id)

    def on_structure_item_changed(
        self, item_type: str, item_id: int, data: dict
    ) -> None:
        self.tree_manager.on_structure_item_changed(item_type, item_id, data)

    def on_structure_item_added(
        self, item_type: str, parent_id: int, data: dict
    ) -> None:
        self.tree_manager.on_structure_item_added(item_type, parent_id, data)

    def get_current_category_id(self):
        """Вернуть текущий ID категории на основе активного UI-контекста.
        Предпочтение: плитки -> выбранный элемент дерева -> первая категория из BL.
        """
        # 1) Если активен режим плиток категорий — используем текущую плитку
        try:
            tiles_stack_index = app_config.get("ui.stack_indices.tiles", 0)
            stack = getattr(self.main, "stack", None)
            tiles = getattr(self.main, "tiles", None)
            if (
                stack is not None
                and tiles is not None
                and stack.currentIndex() == tiles_stack_index
            ):
                current_id = getattr(tiles, "_current_item_id", None)
                if isinstance(current_id, int):
                    return current_id
        except Exception:
            pass

        # 2) Текущий элемент в дереве структуры
        try:
            item = self.tree.currentItem()
            if item is not None:
                from app.utils.ui.qt.roles import get_tree_tuple

                t = get_tree_tuple(item, 0)
                if t:
                    item_type, item_id = t
                    if item_type == "category" and isinstance(item_id, int):
                        return item_id
        except Exception:
            pass

        # 3) Fallback: спросить у бизнес-логики первую доступную категорию
        try:
            return self.business.get_first_category_id()
        except Exception:
            return None
