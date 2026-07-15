import unittest
from unittest.mock import Mock, patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QItemSelectionModel, QModelIndex

from app.controllers.ui.links.controller import LinksUIController

class TestLinksUiFocus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_focus_on_links_applies_selection_and_current_index(self):
        # Mock table view
        table_widget = Mock()
        sel_model = Mock()
        table_widget.selectionModel.return_value = sel_model
        
        # Real table model
        from PyQt6.QtGui import QStandardItemModel
        model = QStandardItemModel(5, 5)
        table_widget.model.return_value = model
        
        # Instantiate controller with mocks
        business_logic = Mock()
        main_window = Mock()
        main_window.ui_state = None
        
        # Mock components to avoid deep dependencies
        with patch('app.controllers.ui.links.controller.LinksUIHandlers'), \
             patch('app.controllers.ui.links.controller.LinksUIClipboard'), \
             patch('app.controllers.ui.links.controller.LinksUILinkOperations'):
            
            controller = LinksUIController(
                table_widget=table_widget,
                business_logic=business_logic,
                main_window=main_window,
                link_operations=Mock(),
                links_table_controller=Mock()
            )
            
            # Setup row indexes
            controller._row_by_link_id = {101: 2, 102: 4}
            
            # Focus on link ids
            controller.focus_on_links([101, 102])
            
            # Assertions
            # 1. selectionModel().select() should be called with rows
            sel_model.select.assert_called_once()
            
            # 2. Current index should be set to first row (index 2) without update flag
            sel_model.setCurrentIndex.assert_called_once()
            call_args = sel_model.setCurrentIndex.call_args[0]
            self.assertEqual(call_args[0], model.index(2, 0))  # check index
            # Check NoUpdate flag was used
            self.assertEqual(call_args[1], QItemSelectionModel.SelectionFlag.NoUpdate)
            
            # 3. Should scroll to the first row (row 2)
            table_widget.scrollTo.assert_called_once()

    def test_focus_on_links_pending_logic(self):
        table_widget = Mock()
        table_widget.selectionModel.return_value = None  # No selection model yet
        business_logic = Mock()
        main_window = Mock()
        main_window.ui_state = None
        
        with patch('app.controllers.ui.links.controller.LinksUIHandlers'), \
             patch('app.controllers.ui.links.controller.LinksUIClipboard'), \
             patch('app.controllers.ui.links.controller.LinksUILinkOperations'):
            
            controller = LinksUIController(
                table_widget=table_widget,
                business_logic=business_logic,
                main_window=main_window,
                link_operations=Mock(),
                links_table_controller=Mock()
            )
            
            # Empty index initially
            controller._row_by_link_id = {}
            
            # Attempt focus
            controller.focus_on_links([201])
            
            # Check it saved to pending
            self.assertEqual(controller._pending_focus_link_ids, [201])
            
            # Mock get_link_at and rebuild_row_index
            controller.get_row_count = Mock(return_value=1)
            controller.get_link_at = Mock(return_value={"id": 201})
            
            # Trigger rebuild_row_index
            with patch('PyQt6.QtCore.QTimer.singleShot') as mock_timer:
                controller.rebuild_row_index()
                self.assertEqual(controller._row_by_link_id, {201: 0})
                self.assertIsNone(controller._pending_focus_link_ids)
                mock_timer.assert_called_once()
