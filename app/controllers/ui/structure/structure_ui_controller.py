# app/controllers/structure/structure_ui_controller.py

from PyQt6.QtCore import (  # Импортируем Qt и QSize из QtCore
    QObject,
    QSize,
    Qt,
    pyqtSignal,
)
from PyQt6.QtWidgets import QAbstractItemView, QTreeView

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

    def __init__(self, tree_widget: QTreeView, business_logic, main_window):
        super().__init__()
        self.tree = tree_widget
        self.business = business_logic
        self.main = main_window
        self.undo_stack = main_window.undo_stack

        # Изменяем порядок: сначала icon_handler, затем вычисляем зависимости UI
        self.icon_handler = IconHandling(self)
        # Явная зависимость контроллера плиток категорий
        cat_tiles_ctrl = getattr(self.main, "category_tiles_controller", None)
        self.selection_handler = SelectionHandling(
            self, category_tiles_controller=cat_tiles_ctrl
        )
        self.item_ops = ItemOperations(self)
        # Передаём явную зависимость контроллера плиток категорий в TreeManagement
        self.tree_manager = TreeManagement(
            self, category_tiles_controller=cat_tiles_ctrl
        )  # TreeManagement после IconHandling

        self._setup_tree()
        self._connect_business_signals()
        self._connect_model_icon_reload_signals()

    def _connect_model_icon_reload_signals(self) -> None:
        """Подключения после modelReset.

        Иконки обычно заполняются при построении снапшота, однако для надёжности
        (и смены темы/нестандартных случаев) выполняем коалесцированную перезагрузку
        иконок после modelReset. Также переподключаем selectionModel.
        """
        try:
            model = self.tree.model()
        except Exception:
            model = None
        if not model:
            return

        # Коалесцированная перезагрузка иконок после стабилизации модели
        def _schedule_reload():
            from PyQt6.QtCore import QTimer

            def _do_reload():
                try:
                    self.icon_handler.reload_icons()
                except Exception:
                    pass

            QTimer.singleShot(0, _do_reload)

        # После modelReset у QTreeView меняется selectionModel. Переподключаем currentChanged.
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
                    # На всякий случай пытаемся отключить старую связь, если она есть
                    try:
                        sel_model.currentChanged.disconnect(
                            self.selection_handler._on_current_changed
                        )
                    except Exception:
                        # Не критично: previous connection мог отсутствовать
                        import logging
                        logging.getLogger(__name__).debug(
                            "Selection reconnect: disconnect previous failed",
                            exc_info=True,
                        )
                    try:
                        sel_model.currentChanged.connect(
                            self.selection_handler._on_current_changed
                        )
                    except Exception:
                        import logging
                        logging.getLogger(__name__).debug(
                            "Selection reconnect: connect failed", exc_info=True
                        )

                QTimer.singleShot(0, _reconnect)
            except Exception:
                # Не критично, просто логируем в DEBUG
                import logging
                logging.getLogger(__name__).debug(
                    "Failed to schedule selection reconnect after modelReset", exc_info=True
                )

        # Перезагрузка иконок после полной стабилизации модели
        try:
            model.modelReset.connect(_schedule_reload)
        except Exception:
            pass

        # Переподключение selectionModel после сброса модели
        try:
            model.modelReset.connect(_schedule_selection_reconnect)
        except Exception:
            pass

    def _setup_tree(self) -> None:
        self.tree.setHeaderHidden(True)
        # Размер иконок в дереве — из конфигурации (ui.tree_icon_size)
        try:
            w, h = app_config.ui.get_tree_icon_size()
            self.tree.setIconSize(QSize(int(w), int(h)))
        except Exception:
            # Fallback на безопасное значение
            self.tree.setIconSize(QSize(28, 28))
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        # Разрешаем множественное выделение, чтобы "Выделить все" сохранялось
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        # Переключение выделения для QTreeView через QItemSelectionModel
        sel_model = getattr(self.tree, "selectionModel", None)
        if callable(sel_model):
            sel_model = self.tree.selectionModel()
        if sel_model:
            sel_model.currentChanged.connect(self.selection_handler._on_current_changed)

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
        # QTreeView-only: определяем элемент по QModelIndex
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
            pass

        # 2) Текущий элемент в дереве структуры
        try:
            index = self.tree.currentIndex()
            if index and index.isValid():
                from app.utils.ui.qt.roles import get_tree_tuple

                t = get_tree_tuple(index, 0)
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

    def shutdown(self) -> None:
        """Завершает ресурсы контроллера (например, пул иконок).

        Вызывается централизованным контроллером завершения приложения.
        Повторные вызовы безопасны.
        """
        try:
            ih = getattr(self, "icon_handler", None)
            if ih is not None and hasattr(ih, "close"):
                ih.close()
        except Exception:
            # Проблемы закрытия не должны прерывать общий shutdown
            import logging
            logging.getLogger(__name__).debug(
                "StructureUIController.shutdown: icon_handler.close failed", exc_info=True
            )
