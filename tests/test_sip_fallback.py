"""Tests for enhanced sip.isdeleted() fallback mechanism."""

import pytest
from unittest.mock import Mock, patch
from PyQt6.QtWidgets import QWidget, QApplication


class TestSipFallback:
    """Test enhanced sip.isdeleted() fallback functionality."""
    
    def test_fallback_with_none_object(self):
        """Test fallback correctly identifies None as deleted."""
        # Import the fallback function
        with patch('app.views.main_components.ui.topbar.top_bar_layout_manager._SIP_AVAILABLE', False):
            from app.views.main_components.ui.topbar.top_bar_layout_manager import _sip_isdeleted
            
            assert _sip_isdeleted(None) is True
    
    def test_fallback_with_valid_qt_object(self, qtbot):
        """Test fallback correctly identifies valid Qt object as not deleted."""
        with patch('app.views.main_components.ui.topbar.top_bar_layout_manager._SIP_AVAILABLE', False):
            from app.views.main_components.ui.topbar.top_bar_layout_manager import _sip_isdeleted
            
            widget = QWidget()
            qtbot.addWidget(widget)
            
            assert _sip_isdeleted(widget) is False
    
    def test_fallback_with_non_qt_object(self):
        """Test fallback correctly handles non-Qt objects."""
        with patch('app.views.main_components.ui.topbar.top_bar_layout_manager._SIP_AVAILABLE', False):
            from app.views.main_components.ui.topbar.top_bar_layout_manager import _sip_isdeleted
            
            # Non-Qt objects should not be considered "deleted"
            regular_object = {"key": "value"}
            assert _sip_isdeleted(regular_object) is False
    
    def test_fallback_with_deleted_qt_object(self, qtbot):
        """Test fallback detects deleted Qt objects via RuntimeError."""
        with patch('app.views.main_components.ui.topbar.top_bar_layout_manager._SIP_AVAILABLE', False):
            from app.views.main_components.ui.topbar.top_bar_layout_manager import _sip_isdeleted
            
            # Mock a Qt object that raises RuntimeError when accessed
            mock_widget = Mock()
            mock_widget.parent = Mock(side_effect=RuntimeError("wrapped C/C++ object has been deleted"))
            
            assert _sip_isdeleted(mock_widget) is True
    
    def test_fallback_statistics_tracking(self):
        """Test that fallback tracks usage statistics."""
        with patch('app.views.main_components.ui.topbar.top_bar_layout_manager._SIP_AVAILABLE', False):
            # Reset counters
            import app.views.main_components.ui.topbar.top_bar_layout_manager as module
            module._FALLBACK_CALL_COUNT = 0
            module._FALLBACK_ERROR_COUNT = 0
            
            from app.views.main_components.ui.topbar.top_bar_layout_manager import _sip_isdeleted, _get_fallback_stats
            
            # Make some calls
            _sip_isdeleted(None)
            _sip_isdeleted({"not": "qt"})
            
            stats = _get_fallback_stats()
            assert stats['sip_available'] is False
            assert stats['total_calls'] >= 2
            assert stats['success_rate'] > 0
    
    def test_fallback_warning_shown_once(self):
        """Test that warning is shown only once per session."""
        with patch('app.views.main_components.ui.topbar.top_bar_layout_manager._SIP_AVAILABLE', False):
            # Reset warning flag
            import app.views.main_components.ui.topbar.top_bar_layout_manager as module
            module._SIP_FALLBACK_WARNED = False
            
            from app.views.main_components.ui.topbar.top_bar_layout_manager import _sip_isdeleted
            
            with patch('logging.getLogger') as mock_logger:
                mock_log = Mock()
                mock_logger.return_value = mock_log
                
                # First call should log warning
                _sip_isdeleted(None)
                assert mock_log.info.called
                
                # Reset mock
                mock_log.reset_mock()
                
                # Second call should not log warning
                _sip_isdeleted(None)
                assert not mock_log.info.called
    
    def test_native_sip_statistics(self):
        """Test statistics when native sip is available."""
        with patch('app.views.main_components.ui.topbar.top_bar_layout_manager._SIP_AVAILABLE', True):
            from app.views.main_components.ui.topbar.top_bar_layout_manager import _get_fallback_stats
            
            stats = _get_fallback_stats()
            assert stats['sip_available'] is True
            assert stats['total_calls'] == 0
            assert stats['success_rate'] == 100.0


class TestTopBarLayoutManagerSipIntegration:
    """Test TopBarLayoutManager integration with sip fallback."""
    
    def test_get_sip_statistics_method(self, qtbot):
        """Test that TopBarLayoutManager exposes sip statistics."""
        from app.views.main_components.ui.topbar.top_bar_layout_manager import TopBarLayoutManager
        from unittest.mock import Mock
        
        # Mock window
        mock_window = Mock()
        mock_window.top_bar_host = QWidget()
        
        manager = TopBarLayoutManager(mock_window)
        
        stats = manager.get_sip_statistics()
        
        # Should return valid statistics dictionary
        assert isinstance(stats, dict)
        assert 'sip_available' in stats
        assert 'total_calls' in stats
        assert 'error_count' in stats
        assert 'success_rate' in stats
        
        # Cleanup
        manager.cleanup()
    
    def test_cleanup_logs_sip_statistics(self, qtbot):
        """Test that cleanup logs sip statistics when debug logging is enabled."""
        from app.views.main_components.ui.topbar.top_bar_layout_manager import TopBarLayoutManager
        from unittest.mock import Mock, patch
        
        # Mock window
        mock_window = Mock()
        mock_window.top_bar_host = QWidget()
        
        manager = TopBarLayoutManager(mock_window)
        
        with patch('app.views.main_components.ui.topbar.top_bar_layout_manager.logger') as mock_logger:
            mock_logger.isEnabledFor.return_value = True
            
            # Mock statistics to simulate fallback usage
            with patch.object(manager, 'get_sip_statistics') as mock_stats:
                mock_stats.return_value = {
                    'sip_available': False,
                    'total_calls': 10,
                    'error_count': 1,
                    'success_rate': 90.0
                }
                
                manager.cleanup()
                
                # Should log statistics
                mock_logger.debug.assert_called()
                debug_calls = [call for call in mock_logger.debug.call_args_list 
                              if 'sip fallback stats' in str(call)]
                assert len(debug_calls) > 0


@pytest.fixture
def qapp():
    """Ensure QApplication exists for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
