"""Tests for drag and drop category moves between sections in tree and from tiles."""

import sys
import unittest
from unittest.mock import Mock
from PyQt6.QtCore import QModelIndex, QPointF, Qt
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QApplication, QAbstractItemView

from app.utils.ui.dnd.tree import DragDropHandler
from app.views.models.structure_tree_model import StructureTreeModel


class TestTreeCategoryMoveDnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_determine_target_section_item(self) -> None:
        tree = Mock()
        tree.dropIndicatorPosition.return_value = QAbstractItemView.DropIndicatorPosition.OnItem
        model = Mock()
        model.rowCount.return_value = 3
        tree.model.return_value = model

        sec_idx = Mock(spec=QModelIndex)
        sec_idx.isValid.return_value = True
        sec_idx.model.return_value = model
        model.data.side_effect = lambda idx, role: ("section", 100) if role == Qt.ItemDataRole.UserRole else None
        tree.indexAt.return_value = sec_idx

        handler = DragDropHandler(tree)
        event = Mock(spec=QDropEvent)
        event.position.return_value = QPointF(10.0, 20.0)

        sec_id, base_row = handler.determine_target(event)
        self.assertEqual(sec_id, 100)
        self.assertEqual(base_row, 3)

    def test_determine_target_category_item_above(self) -> None:
        tree = Mock()
        tree.dropIndicatorPosition.return_value = QAbstractItemView.DropIndicatorPosition.AboveItem
        model = Mock()
        model.rowCount.return_value = 5
        tree.model.return_value = model

        sec_idx = Mock(spec=QModelIndex)
        sec_idx.isValid.return_value = True
        sec_idx.model.return_value = model

        cat_idx = Mock(spec=QModelIndex)
        cat_idx.isValid.return_value = True
        cat_idx.model.return_value = model
        cat_idx.row.return_value = 2
        cat_idx.parent.return_value = sec_idx

        def data_side_effect(idx, role):
            if role == Qt.ItemDataRole.UserRole:
                if idx is cat_idx:
                    return ("category", 15)
                if idx is sec_idx:
                    return ("section", 200)
            return None

        model.data.side_effect = data_side_effect
        tree.indexAt.return_value = cat_idx

        handler = DragDropHandler(tree)
        event = Mock(spec=QDropEvent)
        event.position.return_value = QPointF(10.0, 20.0)

        sec_id, base_row = handler.determine_target(event)
        self.assertEqual(sec_id, 200)
        self.assertEqual(base_row, 2)

    def test_is_valid_drop_allows_category_to_different_section(self) -> None:
        tree = Mock()
        tree.dropIndicatorPosition.return_value = QAbstractItemView.DropIndicatorPosition.OnItem
        model = Mock()
        tree.model.return_value = model

        src_parent = Mock(spec=QModelIndex)
        src_parent.isValid.return_value = True
        src_parent.model.return_value = model

        src_idx = Mock(spec=QModelIndex)
        src_idx.isValid.return_value = True
        src_idx.model.return_value = model
        src_idx.parent.return_value = src_parent

        tgt_parent = Mock(spec=QModelIndex)
        tgt_parent.isValid.return_value = True
        tgt_parent.model.return_value = model

        tgt_idx = Mock(spec=QModelIndex)
        tgt_idx.isValid.return_value = True
        tgt_idx.model.return_value = model
        tgt_idx.parent.return_value = tgt_parent

        def data_side_effect(idx, role):
            if role == Qt.ItemDataRole.UserRole:
                if idx is src_idx:
                    return ("category", 1)
                if idx is src_parent:
                    return ("section", 10)
                if idx is tgt_idx:
                    return ("category", 2)
                if idx is tgt_parent:
                    return ("section", 20)
            return None

        model.data.side_effect = data_side_effect
        tree.indexAt.return_value = tgt_idx

        handler = DragDropHandler(tree)
        event = Mock(spec=QDropEvent)
        event.position.return_value = QPointF(10.0, 20.0)

        # Drop is valid across sections
        self.assertTrue(handler._is_valid_drop_index(src_idx, event))

    def test_move_category_model_populates_target_section_if_collapsed(self) -> None:
        model = StructureTreeModel()
        model.set_snapshot([
            {
                "id": 1,
                "name": "Sec 1",
                "icon": None,
                "categories": [{"id": 10, "name": "Cat 10", "icon": None}],
            },
            {
                "id": 2,
                "name": "Sec 2",
                "icon": None,
                "categories": [{"id": 20, "name": "Cat 20", "icon": None}],
            },
        ])

        success = model.move_category(10, 2, 0)
        self.assertTrue(success)

        sec2_idx = model.index(1, 0, QModelIndex())
        self.assertEqual(model.rowCount(sec2_idx), 2)
        cat_moved_idx = model.index_for("category", 10)
        self.assertTrue(cat_moved_idx.isValid())
        self.assertEqual(cat_moved_idx.parent(), sec2_idx)
