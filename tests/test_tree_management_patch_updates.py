import pytest
from unittest.mock import MagicMock
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from app.controllers.ui.structure.tree_management import TreeManagement
from app.views.models.structure_tree_model import StructureTreeModel


class DummyTree:
    def __init__(self, model):
        self._model = model
        self._selection_model = MagicMock()

    def model(self):
        return self._model

    def selectionModel(self):
        return self._selection_model

    def currentIndex(self):
        # Вернуть первый элемент если есть
        idx = self._model.index(0, 0)
        return idx

    def setUpdatesEnabled(self, _):
        pass


class DummyController:
    def __init__(self, model):
        self.tree = DummyTree(model)
        # selection_handler с нужным методом
        self.selection_handler = MagicMock()
        # заглушки
        self.icon_handler = MagicMock()
        self.main = MagicMock()


class DummyTilesController:
    def clear(self):
        pass

    def refresh(self, section_id: int):
        pass


@pytest.fixture
def model():
    return StructureTreeModel()


@pytest.fixture
def controller(model):
    return DummyController(model)


@pytest.fixture
def tree_manager(controller):
    return TreeManagement(controller, category_tiles_controller=DummyTilesController())


def test_patch_insert_update_remove(tree_manager, controller, model):
    # Стартовое наполнение
    model.set_snapshot([
        {"id": 1, "name": "Alpha", "icon": QIcon(), "categories": [
            {"id": 101, "name": "A1", "icon": QIcon()}
        ]}
    ])

    # Патч: добавить секцию 2, обновить секцию 1, добавить категорию 102, удалить категорию 101
    patch = {
        "op": "patch",
        "insert": {
            "sections": [
                {"id": 2, "name": "Beta", "icon": QIcon(), "categories": []}
            ],
            "categories": {1: [
                {"id": 102, "name": "A2", "icon": QIcon()}
            ]},
        },
        "update": {
            "sections": [
                {"id": 1, "name": "Alpha+"}
            ]
        },
        "remove": {
            "categories": [101]
        },
    }

    # Вызов
    tree_manager._on_structure_loaded(patch)

    # Проверки
    assert model.rowCount() == 2
    s0 = model.index(0, 0)
    s1 = model.index(1, 0)
    names = [model.data(s0, Qt.ItemDataRole.DisplayRole), model.data(s1, Qt.ItemDataRole.DisplayRole)]
    assert set(names) == {"Alpha+", "Beta"}

    # В секции 1 осталась только категория 102
    # Найдём индекс секции 1
    from app.utils.ui.qt.roles import get_tree_tuple

    sec1_idx = s0 if get_tree_tuple(s0, 0) == ("section", 1) else s1
    assert model.rowCount(sec1_idx) == 1
    c0 = model.index(0, 0, sec1_idx)
    assert model.data(c0, Qt.ItemDataRole.DisplayRole) == "A2"

    # selection_handler._on_current_changed должен быть вызван единоразово
    controller.selection_handler._on_current_changed.assert_called()
