from types import SimpleNamespace

import pytest

from app.controllers.ui.structure.tree_management import TreeManagement


class ModelStubSectionsError:
    def insert_sections(self, row, items):
        raise ValueError("bad section data")

    def insert_categories(self, parent_id, row, items):
        pass

    def update_item(self, *args, **kwargs):
        pass


class ModelStubCategoriesError:
    def insert_sections(self, row, items):
        pass

    def insert_categories(self, parent_id, row, items):
        raise RuntimeError("model failed")

    def update_item(self, *args, **kwargs):
        pass


class TreeStub:
    def __init__(self, model):
        self._model = model

    def model(self):
        return self._model


class SelectionHandlerStub:
    def _set_focus_on_new_item_by_id(self, *args, **kwargs):
        pass


class TilesControllerStub:
    def refresh(self, *_):
        pass


class ControllerStub:
    def __init__(self, tree):
        self.tree = tree
        self.selection_handler = SelectionHandlerStub()
        self.icon_handler = None
        self.main = SimpleNamespace(_first_structure_load=False)


def make_tree_mgmt(model):
    tree = TreeStub(model)
    ctrl = ControllerStub(tree)
    return TreeManagement(ctrl, TilesControllerStub())


def test_insert_section_error_not_suppressed():
    tm = make_tree_mgmt(ModelStubSectionsError())
    with pytest.raises(ValueError):
        tm._on_item_added("section", parent_id=0, data={"id": 10, "name": "S"})


def test_insert_category_error_not_suppressed():
    tm = make_tree_mgmt(ModelStubCategoriesError())
    with pytest.raises(RuntimeError):
        tm._on_item_added("category", parent_id=5, data={"id": 11, "name": "C"})
