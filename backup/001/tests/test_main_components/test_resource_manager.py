"""Unit tests for ResourceManager."""

from unittest.mock import Mock

from app.views.main_components.resource_manager import ResourceManager, managed_resource


class TestResourceManager:
    """Tests for ResourceManager class."""
    
    def test_init(self):
        """Test ResourceManager initialization."""
        manager = ResourceManager("Test")
        
        assert manager._name == "Test"
        assert manager._cleaned_up is False
        assert len(manager._resources) == 0
        assert len(manager._cleanup_errors) == 0
    
    def test_register_resource_with_explicit_cleanup(self):
        """Test registering resource with explicit cleanup function."""
        manager = ResourceManager("Test")
        cleanup_called = []
        
        def cleanup():
            cleanup_called.append(True)
        
        resource = object()
        manager.register_resource(resource, cleanup, "test_resource")
        
        assert len(manager._resources) == 1
        assert cleanup_called == []  # Not called yet
    
    def test_cleanup_all_calls_cleanup_functions(self):
        """Test that cleanup_all calls all registered cleanup functions."""
        manager = ResourceManager("Test")
        cleanup_calls = []
        
        def cleanup1():
            cleanup_calls.append(1)
        
        def cleanup2():
            cleanup_calls.append(2)
        
        manager.register_resource(object(), cleanup1, "resource1")
        manager.register_resource(object(), cleanup2, "resource2")
        
        manager.cleanup_all()
        
        # Should be called in reverse order (LIFO)
        assert cleanup_calls == [2, 1]
        assert manager.is_cleaned_up()
    
    def test_cleanup_all_handles_errors(self):
        """Test that cleanup_all continues even if a cleanup function raises."""
        manager = ResourceManager("Test")
        cleanup_calls = []
        
        def cleanup1():
            cleanup_calls.append(1)
        
        def cleanup2():
            raise RuntimeError("Cleanup failed")
        
        def cleanup3():
            cleanup_calls.append(3)
        
        manager.register_resource(object(), cleanup1, "resource1")
        manager.register_resource(object(), cleanup2, "resource2")
        manager.register_resource(object(), cleanup3, "resource3")
        
        manager.cleanup_all()
        
        # All cleanups should be attempted despite error
        assert cleanup_calls == [3, 1]  # 2 failed but others succeeded
        assert len(manager.get_cleanup_errors()) == 1
        assert manager.is_cleaned_up()
    
    def test_cleanup_all_is_idempotent(self):
        """Test that cleanup_all can be called multiple times safely."""
        manager = ResourceManager("Test")
        cleanup_calls = []
        
        def cleanup():
            cleanup_calls.append(True)
        
        manager.register_resource(object(), cleanup, "resource")
        
        manager.cleanup_all()
        manager.cleanup_all()  # Second call
        
        # Should only be called once
        assert cleanup_calls == [True]
    
    def test_register_after_cleanup_is_no_op(self):
        """Test that registering after cleanup does nothing."""
        manager = ResourceManager("Test")
        manager.cleanup_all()
        
        cleanup_called = []
        manager.register_resource(object(), lambda: cleanup_called.append(True), "late")
        
        assert len(manager._resources) == 0
        assert cleanup_called == []
    
    def test_auto_detect_cleanup_for_qt_timer(self):
        """Test auto-detection of cleanup method for QTimer-like object."""
        manager = ResourceManager("Test")
        
        # Mock object with stop() method
        mock_timer = Mock()
        mock_timer.stop = Mock()
        
        manager.register_resource(mock_timer, None, "timer")  # None = auto-detect
        manager.cleanup_all()
        
        mock_timer.stop.assert_called_once()
    
    def test_auto_detect_cleanup_for_qt_widget(self):
        """Test auto-detection of cleanup method for QWidget-like object."""
        manager = ResourceManager("Test")
        
        # Mock object with deleteLater() method
        mock_widget = Mock()
        mock_widget.deleteLater = Mock()
        
        manager.register_resource(mock_widget, None, "widget")
        manager.cleanup_all()
        
        mock_widget.deleteLater.assert_called_once()
    
    def test_auto_detect_cleanup_for_file_like(self):
        """Test auto-detection of cleanup method for file-like object."""
        manager = ResourceManager("Test")
        
        # Mock file-like object
        mock_file = Mock()
        mock_file.close = Mock()
        
        manager.register_resource(mock_file, None, "file")
        manager.cleanup_all()
        
        mock_file.close.assert_called_once()
    
    def test_context_manager(self):
        """Test ResourceManager as context manager."""
        cleanup_called = []
        
        with ResourceManager("Test") as manager:
            manager.register_resource(
                object(), 
                lambda: cleanup_called.append(True),
                "resource"
            )
        
        # Should auto-cleanup on exit
        assert cleanup_called == [True]
    
    def test_context_manager_with_exception(self):
        """Test that context manager cleans up even on exception."""
        cleanup_called = []
        
        try:
            with ResourceManager("Test") as manager:
                manager.register_resource(
                    object(),
                    lambda: cleanup_called.append(True),
                    "resource"
                )
                raise ValueError("Test error")
        except ValueError:
            pass
        
        # Should still cleanup
        assert cleanup_called == [True]


class TestManagedResource:
    """Tests for managed_resource context manager."""
    
    def test_managed_resource_cleans_up(self):
        """Test that managed_resource cleans up on exit."""
        cleanup_called = []
        resource = object()
        
        with managed_resource(resource, lambda: cleanup_called.append(True), "test"):
            assert cleanup_called == []  # Not cleaned yet
        
        assert cleanup_called == [True]
    
    def test_managed_resource_provides_resource(self):
        """Test that managed_resource provides the resource."""
        resource = object()
        
        with managed_resource(resource, lambda: None, "test") as provided:
            assert provided is resource
    
    def test_managed_resource_cleans_up_on_exception(self):
        """Test that managed_resource cleans up even on exception."""
        cleanup_called = []
        
        try:
            with managed_resource(object(), lambda: cleanup_called.append(True), "test"):
                raise RuntimeError("Test")
        except RuntimeError:
            pass
        
        assert cleanup_called == [True]
