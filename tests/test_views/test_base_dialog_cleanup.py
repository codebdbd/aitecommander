"""
Тесты для проверки cleanup ресурсов в BaseDialog.

✅ НОВЫЕ ТЕСТЫ: Проверяют предотвращение memory leaks в диалогах.
"""

import pytest
from unittest.mock import Mock, patch
from PyQt6.QtWidgets import QLineEdit, QTextEdit, QMenu
from PyQt6.QtCore import Qt

from app.views.windows.dialogs.base_dialog import BaseDialog


class TestBaseDialogCleanup:
    """Тесты cleanup ресурсов BaseDialog."""
    
    @pytest.fixture
    def base_dialog(self, qtbot):
        """Create BaseDialog instance for testing."""
        dialog = BaseDialog()
        qtbot.addWidget(dialog)
        return dialog
    
    def test_context_menus_tracking_initialization(self, base_dialog):
        """✅ ТЕСТ: Проверяет инициализацию трекинга context menus."""
        # Assert: Context menus list initialized
        assert hasattr(base_dialog, '_context_menus')
        assert isinstance(base_dialog._context_menus, list)
        assert len(base_dialog._context_menus) == 0
    
    def test_show_context_menu_adds_to_tracking(self, base_dialog, qtbot):
        """✅ ТЕСТ: Проверяет добавление context menu в трекинг."""
        # Arrange: Create widget
        widget = QLineEdit()
        qtbot.addWidget(widget)
        
        # Mock create_context_menu to return a mock menu
        mock_menu = Mock(spec=QMenu)
        
        with patch('app.views.windows.dialogs.base_dialog.create_context_menu', return_value=mock_menu):
            # Act: Show context menu
            base_dialog._show_context_menu(widget, widget.pos())
        
        # Assert: Menu added to tracking
        assert len(base_dialog._context_menus) == 1
        assert base_dialog._context_menus[0] is mock_menu
        mock_menu.popup.assert_called_once()
    
    def test_cleanup_context_menus_closes_and_deletes(self, base_dialog):
        """✅ ТЕСТ: Проверяет cleanup context menus."""
        # Arrange: Add mock menus to tracking
        mock_menu1 = Mock(spec=QMenu)
        mock_menu1.isHidden.return_value = False
        mock_menu2 = Mock(spec=QMenu)
        mock_menu2.isHidden.return_value = True
        
        base_dialog._context_menus = [mock_menu1, mock_menu2]
        
        # Act: Cleanup
        base_dialog._cleanup_context_menus()
        
        # Assert: Visible menu closed, all menus deleted
        mock_menu1.close.assert_called_once()
        mock_menu1.deleteLater.assert_called_once()
        mock_menu2.deleteLater.assert_called_once()
        mock_menu2.close.assert_not_called()  # Hidden menu not closed
        
        # Assert: Tracking list cleared
        assert len(base_dialog._context_menus) == 0
    
    def test_cleanup_handles_runtime_errors(self, base_dialog):
        """✅ ТЕСТ: Проверяет обработку RuntimeError при cleanup."""
        # Arrange: Add mock menu that raises RuntimeError
        mock_menu = Mock(spec=QMenu)
        mock_menu.isHidden.side_effect = RuntimeError("Object deleted")
        mock_menu.deleteLater.side_effect = RuntimeError("Object deleted")
        
        base_dialog._context_menus = [mock_menu]
        
        # Act & Assert: No exception raised
        base_dialog._cleanup_context_menus()  # Should not raise
        
        # Assert: List still cleared despite errors
        assert len(base_dialog._context_menus) == 0
    
    def test_close_event_calls_cleanup(self, base_dialog, qtbot):
        """✅ ТЕСТ: Проверяет что closeEvent вызывает cleanup."""
        # Arrange: Mock cleanup method
        base_dialog._cleanup_context_menus = Mock()
        
        # Mock event
        event = Mock()
        
        # Act: Call closeEvent
        base_dialog.closeEvent(event)
        
        # Assert: Cleanup called
        base_dialog._cleanup_context_menus.assert_called_once()
    
    def test_setup_russian_context_menus_uses_tracking(self, base_dialog, qtbot):
        """✅ ТЕСТ: Проверяет что setup использует трекинг."""
        # Arrange: Add text widgets
        line_edit = QLineEdit()
        text_edit = QTextEdit()
        
        # Add widgets to dialog (simulate findChildren result)
        base_dialog.layout().addWidget(line_edit) if base_dialog.layout() else None
        base_dialog.layout().addWidget(text_edit) if base_dialog.layout() else None
        
        # Mock findChildren to return our widgets
        with patch.object(base_dialog, 'findChildren', return_value=[line_edit, text_edit]):
            # Act: Setup context menus
            base_dialog._setup_russian_context_menus()
        
        # Assert: Widgets have custom context menu policy
        assert line_edit.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
        assert text_edit.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
    
    @patch('app.views.windows.dialogs.base_dialog.logger')
    def test_show_context_menu_logs_errors(self, mock_logger, base_dialog, qtbot):
        """✅ ТЕСТ: Проверяет логирование ошибок при показе context menu."""
        # Arrange: Mock create_context_menu to raise exception
        widget = QLineEdit()
        qtbot.addWidget(widget)
        
        with patch('app.views.windows.dialogs.base_dialog.create_context_menu', 
                  side_effect=Exception("Menu creation failed")):
            # Act: Try to show context menu
            base_dialog._show_context_menu(widget, widget.pos())
        
        # Assert: Error logged
        mock_logger.warning.assert_called_once()
        args = mock_logger.warning.call_args[0]
        assert "Failed to show context menu" in args[0]
        assert "Menu creation failed" in str(args[1])
    
    def test_multiple_context_menus_tracking(self, base_dialog, qtbot):
        """✅ ТЕСТ: Проверяет трекинг нескольких context menus."""
        # Arrange: Create multiple widgets
        widget1 = QLineEdit()
        widget2 = QTextEdit()
        qtbot.addWidget(widget1)
        qtbot.addWidget(widget2)
        
        mock_menu1 = Mock(spec=QMenu)
        mock_menu2 = Mock(spec=QMenu)
        
        # Act: Show multiple context menus
        with patch('app.views.windows.dialogs.base_dialog.create_context_menu', 
                  side_effect=[mock_menu1, mock_menu2]):
            base_dialog._show_context_menu(widget1, widget1.pos())
            base_dialog._show_context_menu(widget2, widget2.pos())
        
        # Assert: Both menus tracked
        assert len(base_dialog._context_menus) == 2
        assert mock_menu1 in base_dialog._context_menus
        assert mock_menu2 in base_dialog._context_menus
        
        # Act: Cleanup all
        base_dialog._cleanup_context_menus()
        
        # Assert: All menus cleaned up
        mock_menu1.deleteLater.assert_called_once()
        mock_menu2.deleteLater.assert_called_once()
        assert len(base_dialog._context_menus) == 0


class TestBaseDialogMemoryLeaks:
    """Тесты для проверки предотвращения memory leaks в диалогах."""
    
    def test_no_dangling_menu_references(self, qtbot):
        """✅ ТЕСТ: Проверяет отсутствие dangling references на context menus."""
        # Arrange & Act: Create and destroy dialog
        dialog = BaseDialog()
        qtbot.addWidget(dialog)
        
        # Add some mock menus
        mock_menu = Mock(spec=QMenu)
        dialog._context_menus = [mock_menu]
        
        # Close dialog (triggers cleanup)
        dialog.close()
        
        # Assert: Menu cleanup called
        mock_menu.deleteLater.assert_called_once()
    
    def test_context_menu_cleanup_on_dialog_destruction(self, qtbot):
        """✅ ТЕСТ: Проверяет cleanup при уничтожении диалога."""
        # Arrange: Create dialog with context menus
        dialog = BaseDialog()
        qtbot.addWidget(dialog)
        
        # Setup context menus
        widget = QLineEdit()
        qtbot.addWidget(widget)
        
        mock_menu = Mock(spec=QMenu)
        
        with patch('app.views.windows.dialogs.base_dialog.create_context_menu', 
                  return_value=mock_menu):
            dialog._show_context_menu(widget, widget.pos())
        
        # Verify menu was tracked
        assert len(dialog._context_menus) == 1
        
        # Act: Close dialog
        dialog.close()
        
        # Assert: Menu was cleaned up
        mock_menu.deleteLater.assert_called_once()
        assert len(dialog._context_menus) == 0
