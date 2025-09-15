import sys

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSize, Qt

from app.views.custom_widgets import StructureTreeView
from app.controllers.ui.structure.structure_ui_controller import StructureUIController
from app.views.models.structure_tree_model import StructureTreeModel
from app.config_data import app_config


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class _Signal:
    def connect(self, *_args, **_kwargs):
        # Stub for Qt signal 'connect'
        pass


class _BusinessStub:
    def __init__(self):
        self.structure_loaded = _Signal()
        self.item_added = _Signal()
        self.item_updated = _Signal()
        self.item_deleted = _Signal()
        self.section_selected = _Signal()
        self.category_selected = _Signal()
        self.error_occurred = _Signal()

    # Optional methods used elsewhere but not needed here
    def get_first_category_id(self):
        return None


class _MainStub:
    def __init__(self):
        self.undo_stack = object()
        # Minimal stub required by SelectionHandling / TreeManagement
        class _CategoryTilesControllerStub:
            def refresh(self, *args, **kwargs):
                pass

        self.category_tiles_controller = _CategoryTilesControllerStub()
        self.menu_controller = None


def test_tree_is_configured_by_controller(qapp):
    # Arrange
    tree = StructureTreeView()
    # TreeManagement requires a valid model on the tree
    tree.setModel(StructureTreeModel(tree))
    business = _BusinessStub()
    main = _MainStub()

    # Precondition: StructureTreeView itself does not force header hidden
    # Controller should be responsible for header visibility and icon size
    assert tree.isHeaderHidden() is False

    # Act
    StructureUIController(tree, business, main)

    # Assert header is hidden
    assert tree.isHeaderHidden() is True

    # Assert icon size comes from config (no extra clamping in view layer)
    cfg_w, cfg_h = app_config.ui.get_tree_icon_size()
    expected_size = QSize(int(cfg_w), int(cfg_h))
    assert tree.iconSize() == expected_size

    # Assert DnD configuration
    assert tree.dragEnabled() is True
    assert tree.acceptDrops() is True
    assert tree.defaultDropAction() == Qt.DropAction.MoveAction
    assert (
        tree.dragDropMode().value
        == tree.DragDropMode.InternalMove.value
    )
