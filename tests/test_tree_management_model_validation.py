import pytest
from app.controllers.ui.structure.tree_management import TreeManagement


class TreeNoModel:
    pass


class TreeModelNone:
    def model(self):
        return None


class IncompleteModel:
    # missing insert_categories, update_item
    def insert_sections(self, *_):
        pass


class TreeWithIncompleteModel:
    def model(self):
        return IncompleteModel()


class Controller:
    def __init__(self, tree):
        self.tree = tree
        self.icon_handler = None


class TilesStub:
    def refresh(self, *_):
        pass


def test_init_raises_when_tree_has_no_model_attr():
    ctrl = Controller(TreeNoModel())
    with pytest.raises(ValueError, match=r"requires a valid tree model"):
        TreeManagement(ctrl, TilesStub())


def test_init_raises_when_model_is_none():
    ctrl = Controller(TreeModelNone())
    with pytest.raises(ValueError, match=r"requires a valid tree model"):
        TreeManagement(ctrl, TilesStub())


def test_init_raises_when_model_missing_methods():
    ctrl = Controller(TreeWithIncompleteModel())
    with pytest.raises(ValueError, match=r"requires a model providing methods: insert_sections, insert_categories, update_item"):
        TreeManagement(ctrl, TilesStub())
