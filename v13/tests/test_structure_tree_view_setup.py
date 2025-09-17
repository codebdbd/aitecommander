import sys

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal, QSize

from app.views.custom_widgets import StructureTreeView
from app.views.models.structure_tree_model import StructureTreeModel
from app.controllers.ui.structure.structure_ui_controller import StructureUIController
from app.config_data import app_config


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    yield app


class _BusinessStub(QObject):
    # минимальный набор сигналов, к которым подключается контроллер
    structure_loaded = pyqtSignal(object)
    item_added = pyqtSignal(str, int, dict)
    item_updated = pyqtSignal(str, int, dict)
    item_deleted = pyqtSignal(str, int)
    items_batch_deleted = pyqtSignal(str, list)
    # дополнительные сигналы, используемые контроллером
    section_selected = pyqtSignal(int)
    category_selected = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    # методы, которые могут дергаться SelectionHandling/TreeManagement в тестах не используются
    def get_next_sphere_id(self):
        return None

    def get_first_category_id(self):
        return None


class _MainStub:
    def __init__(self):
        self.undo_stack = object()
        # обязательная зависимость контроллера: предоставляем минимальный заглушечный объект
        self.category_tiles_controller = object()
        # меню не требуется для теста настроек дерева
        self.menu_controller = None


def test_tree_is_configured_by_controller_not_by_ui_setup(qapp):
    tree = StructureTreeView()
    # UI-setup соединяет модель до создания контроллера
    model = StructureTreeModel(tree)
    tree.setModel(model)

    business = _BusinessStub()
    main = _MainStub()

    # Создание контроллера должно произвести всю конфигурацию дерева
    ctrl = StructureUIController(tree, business, main)

    # 1) Заголовок скрыт
    assert tree.isHeaderHidden() is True

    # 2) Размер иконок соответствует конфигу (или fallback из контроллера)
    try:
        w, h = app_config.ui.get_tree_icon_size()
        expected = QSize(int(w), int(h))
    except Exception:
        expected = QSize(28, 28)
    assert tree.iconSize() == expected

    # 3) Режим DnD и DefaultDropAction заданы
    assert tree.dragEnabled() is True
    assert tree.acceptDrops() is True
    # DropIndicatorShown включен в StructureTreeView
    assert tree.showDropIndicator() is True
