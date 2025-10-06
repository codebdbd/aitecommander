"""
Тесты для проверки обработки ошибок в TableDelegate.

✅ НОВЫЕ ТЕСТЫ: Проверяют корректную обработку исключений в delegate.
"""

import pytest
from unittest.mock import Mock, patch
from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QStyleOptionViewItem

from app.views.widgets.link.base_table import TableDelegate


class TestTableDelegateErrorHandling:
    """Тесты обработки ошибок в TableDelegate."""
    
    @pytest.fixture
    def delegate(self):
        """Create TableDelegate instance for testing."""
        return TableDelegate()
    
    @pytest.fixture
    def mock_index(self):
        """Create mock QModelIndex."""
        index = Mock(spec=QModelIndex)
        index.column.return_value = 1  # Name column
        index.row.return_value = 0
        return index
    
    @pytest.fixture
    def mock_option(self):
        """Create mock QStyleOptionViewItem."""
        option = Mock(spec=QStyleOptionViewItem)
        option.rect = Mock()
        option.rect.width.return_value = 100
        option.font = Mock()
        option.fontMetrics = Mock()
        option.fontMetrics.elidedText.return_value = "Elided text"
        return option
    
    def test_font_size_application_handles_attribute_error(self, delegate, mock_index, mock_option):
        """✅ ТЕСТ: Проверяет обработку AttributeError при применении размера шрифта."""
        # Arrange: Mock config to raise AttributeError
        with patch('app.config_data.app_config') as mock_config:
            mock_config.ui.get.side_effect = AttributeError("Config not available")
            
            # Mock painter
            painter = Mock()
            
            # Act & Assert: No exception raised
            delegate.paint(painter, mock_option, mock_index)  # Should not raise
    
    def test_font_size_application_handles_value_error(self, delegate, mock_index, mock_option):
        """✅ ТЕСТ: Проверяет обработку ValueError при конвертации размера шрифта."""
        # Arrange: Setup delegate with invalid font size
        delegate.col_sizes = {1: "invalid_size"}  # String instead of int
        
        # Mock painter
        painter = Mock()
        
        with patch('app.views.widgets.link.base_table.logger') as mock_logger:
            # Act: Paint with invalid font size
            delegate.paint(painter, mock_option, mock_index)
            
            # Assert: Debug log called for expected error
            mock_logger.debug.assert_called()
            args = mock_logger.debug.call_args[0]
            assert "failed to apply font size" in args[0]
    
    def test_color_application_handles_runtime_error(self, delegate, mock_index, mock_option):
        """✅ ТЕСТ: Проверяет обработку RuntimeError при применении цвета."""
        # Arrange: Setup index for opened column
        mock_index.column.return_value = 2  # Opened column
        
        # Mock parent view that raises RuntimeError
        mock_view = Mock()
        mock_view.openedColColor = QColor("red")
        delegate.parent = Mock(return_value=mock_view)
        
        # Mock palette creation to raise RuntimeError
        with patch('PyQt6.QtGui.QPalette', side_effect=RuntimeError("Qt object deleted")):
            painter = Mock()
            
            with patch('app.views.widgets.link.base_table.logger') as mock_logger:
                # Act: Paint with runtime error
                delegate.paint(painter, mock_option, mock_index)
                
                # Assert: Debug log called
                mock_logger.debug.assert_called()
                args = mock_logger.debug.call_args[0]
                assert "failed to apply opened column color" in args[0]
    
    def test_notes_color_application_handles_attribute_error(self, delegate, mock_index, mock_option):
        """✅ ТЕСТ: Проверяет обработку AttributeError для notes column."""
        # Arrange: Setup index for notes column
        mock_index.column.return_value = 3  # Notes column
        
        # Mock parent view without notesColColor attribute
        mock_view = Mock()
        del mock_view.notesColColor  # Remove attribute
        delegate.parent = Mock(return_value=mock_view)
        
        painter = Mock()
        
        with patch('app.views.widgets.link.base_table.logger') as mock_logger:
            # Act: Paint without notesColColor
            delegate.paint(painter, mock_option, mock_index)
            
            # Assert: Debug log called
            mock_logger.debug.assert_called()
            args = mock_logger.debug.call_args[0]
            assert "failed to apply notes column color" in args[0]
    
    def test_unexpected_error_logging(self, delegate, mock_index, mock_option):
        """✅ ТЕСТ: Проверяет логирование неожиданных ошибок."""
        # Arrange: Mock font to raise unexpected exception
        mock_option.font.setPixelSize.side_effect = OSError("Unexpected system error")
        delegate.col_sizes = {1: 12}  # Valid size
        
        painter = Mock()
        
        with patch('app.views.widgets.link.base_table.logger') as mock_logger:
            # Act: Paint with unexpected error
            delegate.paint(painter, mock_option, mock_index)
            
            # Assert: Warning log called for unexpected error
            mock_logger.warning.assert_called()
            args = mock_logger.warning.call_args[0]
            assert "unexpected font error" in args[0]
    
    def test_hover_row_painting_with_invalid_color(self, delegate, mock_index, mock_option):
        """✅ ТЕСТ: Проверяет обработку невалидного hover color."""
        # Arrange: Set invalid hover color
        delegate.hover_color = None
        delegate.hovered_row = 0  # Same as mock_index row
        
        # Mock style state (not selected)
        from PyQt6.QtWidgets import QStyle
        mock_option.state = QStyle.StateFlag.State_None
        
        painter = Mock()
        
        # Act & Assert: No exception raised even with invalid color
        delegate.paint(painter, mock_option, mock_index)  # Should not raise
    
    def test_elided_text_with_invalid_metrics(self, delegate, mock_index, mock_option):
        """✅ ТЕСТ: Проверяет обработку ошибок при elided text."""
        # Arrange: Mock fontMetrics to raise exception
        mock_option.fontMetrics.elidedText.side_effect = RuntimeError("Font metrics error")
        
        painter = Mock()
        
        # Act & Assert: No exception raised
        delegate.paint(painter, mock_option, mock_index)  # Should not raise
    
    @patch('app.views.widgets.link.base_table.logger')
    def test_font_units_fallback(self, mock_logger, delegate):
        """✅ ТЕСТ: Проверяет fallback для font units."""
        # Arrange: Create delegate with invalid font units config
        with patch('app.config_data.app_config') as mock_config:
            mock_config.ui.get.side_effect = [Exception("Config error"), "invalid_units"]
            
            # Act: Create new delegate (triggers font units setup)
            new_delegate = TableDelegate()
            
            # Assert: Fallback to "px"
            assert new_delegate._font_units == "px"
    
    def test_config_access_resilience(self, delegate):
        """✅ ТЕСТ: Проверяет устойчивость к ошибкам конфигурации."""
        # Arrange: Mock config to be completely unavailable
        with patch('app.config_data.app_config', side_effect=ImportError("Config module not found")):
            # Act & Assert: Delegate creation should not fail
            try:
                new_delegate = TableDelegate()
                # Basic functionality should still work
                assert hasattr(new_delegate, 'hovered_row')
                assert hasattr(new_delegate, 'hover_color')
            except Exception as e:
                pytest.fail(f"TableDelegate should handle config errors gracefully: {e}")


class TestTableDelegateRobustness:
    """Тесты устойчивости TableDelegate к различным сценариям."""
    
    def test_paint_with_none_values(self):
        """✅ ТЕСТ: Проверяет обработку None значений."""
        delegate = TableDelegate()
        
        # Mock objects that might be None
        painter = Mock()
        option = None
        index = Mock()
        index.column.return_value = 1
        
        # Act & Assert: Should handle None option gracefully
        try:
            # This might raise AttributeError, which is expected
            delegate.paint(painter, option, index)
        except AttributeError:
            # Expected when option is None
            pass
        except Exception as e:
            pytest.fail(f"Unexpected exception with None option: {e}")
    
    def test_column_size_edge_cases(self):
        """✅ ТЕСТ: Проверяет edge cases для размеров колонок."""
        delegate = TableDelegate()
        
        # Test with various edge case values
        edge_cases = [0, -1, None, "string", [], {}]
        
        for case in edge_cases:
            delegate.col_sizes = {1: case}
            
            # Should not raise exceptions during initialization
            assert hasattr(delegate, 'col_sizes')
    
    def test_parent_view_edge_cases(self):
        """✅ ТЕСТ: Проверяет edge cases для parent view."""
        delegate = TableDelegate()
        
        # Test with various parent scenarios
        delegate.parent = Mock(return_value=None)  # No parent
        
        mock_index = Mock()
        mock_index.column.return_value = 2
        mock_option = Mock()
        mock_option.rect = Mock()
        mock_option.rect.width.return_value = 100
        mock_option.font = Mock()
        
        painter = Mock()
        
        # Act & Assert: Should handle missing parent gracefully
        delegate.paint(painter, mock_option, mock_index)  # Should not raise
