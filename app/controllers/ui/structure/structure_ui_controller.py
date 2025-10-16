# app/controllers/structure/structure_ui_controller.py

import logging
from typing import Optional

from PyQt6.QtCore import (  # Import Qt and QSize from QtCore
    QObject,
    QSize,
    Qt,
    pyqtSignal,
)
from PyQt6.QtWidgets import QAbstractItemView, QTreeView

from app.config_data import app_config
from app.utils.ui.qt.roles import get_tree_tuple

from .icon_handling import IconHandling
from .item_operations import ItemOperations
from .selection_handling import SelectionHandling
from .tree_management import TreeManagement

# Use string literals "section" and "category"

logger = logging.getLogger(__name__)


class StructureUIController(QObject):
    item_changed = pyqtSignal(str, int, dict)
    item_added = pyqtSignal(
        str, int, dict
    )  # Fixed: object → int for consistency with Business Layer

    def __init__(self, tree_widget: QTreeView, business_logic, main_window):
        super().__init__()
        self.tree = tree_widget
        self.business = business_logic
        self.main = main_window
        self.undo_stack = main_window.undo_stack

        # Change order: initialize icon_handler first, then compute UI dependencies
        self.icon_handler = IconHandling(self)
        # Explicit dependency on category tiles controller
        cat_tiles_ctrl = getattr(self.main, "category_tiles_controller", None)
        self.selection_handler = SelectionHandling(
            self, category_tiles_controller=cat_tiles_ctrl
        )
        self.item_ops = ItemOperations(self)
        # Pass explicit category tiles controller dependency into TreeManagement
        self.tree_manager = TreeManagement(
            self, category_tiles_controller=cat_tiles_ctrl
        )  # TreeManagement после IconHandling

        self._setup_tree()
        self._connect_business_signals()
        self._connect_model_icon_reload_signals()

    def _connect_model_icon_reload_signals(self) -> None:
        """Connect to model signals to repopulate icons after tree stabilizes.

        Coalesce multiple events into a single call via QTimer.singleShot(0, ...).
        This ensures icons are updated only after the model finishes
        reset/insert/layout operations.
        """
        try:
            model = self.tree.model()
        except Exception:
            model = None
        if not model:
            return

        self._icons_reload_pending = False

        def _schedule_reload():
            if getattr(self, "_icons_reload_pending", False):
                return
            self._icons_reload_pending = True
            from PyQt6.QtCore import QTimer

            def _do_reload():
                try:
                    self.icon_handler.reload_icons()
                finally:
                    self._icons_reload_pending = False

            QTimer.singleShot(0, _do_reload)

        # After modelReset QTreeView's selectionModel changes. Reconnect currentChanged.
        def _schedule_selection_reconnect():
            try:
                from PyQt6.QtCore import QTimer

                def _reconnect():
                    try:
                        sel_model = self.tree.selectionModel()
                    except Exception:
                        sel_model = None
                    if not sel_model:
                        return
                    try:
                        self.selection_handler.bind_to_selection_model(sel_model)
                    except Exception:
                        import logging

                        logging.getLogger(__name__).debug(
                            "Selection reconnect: bind failed", exc_info=True
                        )

                QTimer.singleShot(0, _reconnect)
            except Exception:
                # Not critical, log in DEBUG only
                import logging

                logging.getLogger(__name__).debug(
                    "Failed to schedule selection reconnect after modelReset",
                    exc_info=True,
                )

        # Subscribe ONLY to modelReset to perform a single pass
        # after full snapshot assembly and avoid repaint on each rowsInserted/layoutChanged
        try:
            model.modelReset.connect(_schedule_reload)
        except Exception:
            pass
        # Reconnect selectionModel after model reset
        try:
            model.modelReset.connect(_schedule_selection_reconnect)
        except Exception:
            pass

    def _setup_tree(self) -> None:
        self.tree.setHeaderHidden(True)
        # Tree icon size — from configuration (ui.tree_icon_size)
        try:
            w, h = app_config.ui.get_tree_icon_size()
            self.tree.setIconSize(QSize(int(w), int(h)))
        except Exception:
            # Fallback to safe value
            self.tree.setIconSize(QSize(28, 28))
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        # Allow multiple selection so "Select All" persists
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        # Selection handling for QTreeView via QItemSelectionModel
        sel_model = getattr(self.tree, "selectionModel", None)
        if callable(sel_model):
            sel_model = self.tree.selectionModel()
        if sel_model:
            self.selection_handler.bind_to_selection_model(sel_model)

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
        # QTreeView-only: determine item by QModelIndex
        item = None
        try:
            idx = self.tree.indexAt(pos)
            item = idx if (idx and idx.isValid()) else None
        except Exception:
            item = None

        menu = self.main.menu_controller.create_structure_context_menu(
            self.tree,
            item,
            delete_item_cb=self.item_ops.delete_item,
            add_new_section_cb=self.item_ops.add_new_section,
            sort_tree_cb=self.tree_manager._sort_tree,
        )
        menu.popup(self.tree.viewport().mapToGlobal(pos))

    # Public methods
    def load(self, item_to_select=None) -> None:
        self.item_ops.load(item_to_select)

    def switch_sphere(self, sphere_id: int) -> None:
        self.item_ops.switch_sphere(sphere_id)

    def switch_to_next_sphere(self) -> None:
        """Switch to the next sphere using business logic."""
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

    def get_current_category_id(self) -> Optional[int]:
        """Return current category ID based on active UI context.
        Preference: tiles -> selected tree item -> first category from BL.
        """
        # 1) If category tiles view is active — use current tile
        try:
            tiles_stack_index = app_config.ui.get_stack_index_tiles()
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
            logger.debug(
                "StructureUIController.get_current_category_id: tiles lookup failed",
                exc_info=True,
            )

        # 2) Try to get category via TreeManagement (considering saved state)
        try:
            category_id = self.tree_manager.get_current_category_id()
            if isinstance(category_id, int):
                return category_id
        except Exception:
            logger.debug(
                "StructureUIController.get_current_category_id: tree manager lookup failed",
                exc_info=True,
            )

        # 3) Directly read selection from tree as a fallback
        try:
            index = self.tree.currentIndex()
            if index and index.isValid():
                item_type, item_id = get_tree_tuple(index, 0) or (None, None)
                if item_type == "category" and isinstance(item_id, int):
                    return item_id
        except Exception:
            logger.debug(
                "StructureUIController.get_current_category_id: tree current index lookup failed",
                exc_info=True,
            )

        # 4) Fallback: ask business logic for the first available category
        try:
            return self.business.get_first_category_id()
        except Exception:
            logger.debug(
                "StructureUIController.get_current_category_id: business fallback failed",
                exc_info=True,
            )
            return None
