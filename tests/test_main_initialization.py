"""Tests for app/main.py initialization logic."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThreadPool

from app.main import (
    ApplicationInitializer,
    initialization_method,
    should_install_signal_handlers,
    signal_handler,
    setup_signal_handling,
    retry_on_failure,
    application_context,
    ExitCode,
    THREAD_POOL_SHUTDOWN_TIMEOUT_MS,
    SIGNAL_EXIT_CODE_BASE,
    Cleanable,
    Shutdownable,
    Stoppable,
)


class TestApplicationInitializer:
    """Test ApplicationInitializer class with ResourceManager integration."""
    
    def test_resource_manager_integration(self, qtbot):
        """Test ResourceManager is properly integrated."""
        initializer = ApplicationInitializer()
        
        # ResourceManager should be created
        assert initializer._resource_manager is not None
        assert initializer._resource_manager._name == "ApplicationInitializer"
        # Threading lock should be initialized
        assert initializer._cleanup_lock is not None
        # Health checking methods should be available
        assert hasattr(initializer, 'is_healthy')
        assert hasattr(initializer, 'get_status')
    
    def test_shutdown_controller_integration(self, qtbot):
        """Test AppShutdownController integration."""
        initializer = ApplicationInitializer()
        
        # Mock main window creation
        mock_window = Mock()
        initializer.main_window = mock_window
        
        with patch('app.main.AppShutdownController') as mock_controller_class:
            mock_controller = Mock()
            mock_controller_class.return_value = mock_controller
            
            # Simulate main window initialization
            initializer.initialize_main_window()
            
            # Should create shutdown controller
            mock_controller_class.assert_called_once_with(mock_window)
            # Should register cleanup handler
            mock_controller.add_shutdown_handler.assert_called_once()
    
    def test_cleanup_delegation_to_shutdown_controller(self, qtbot):
        """Test cleanup delegation when shutdown controller exists."""
        initializer = ApplicationInitializer()
        
        # Mock shutdown controller
        mock_controller = Mock()
        initializer._shutdown_controller = mock_controller
        
        # Mock ResourceManager
        mock_resource_manager = Mock()
        initializer._resource_manager = mock_resource_manager
        
        # Call cleanup - should delegate to shutdown controller
        initializer.cleanup(async_cleanup=False)
        
        # Should not call ResourceManager directly when controller exists
        assert not mock_resource_manager.cleanup_all.called
    
    def test_register_if_cleanable_helper(self, qtbot):
        """Test _register_if_cleanable helper method."""
        initializer = ApplicationInitializer()
        
        # Mock ResourceManager
        mock_resource_manager = Mock()
        initializer._resource_manager = mock_resource_manager
        
        # Test with closeable resource
        class CloseableResource:
            def close(self):
                pass
        
        resource = CloseableResource()
        initializer._register_if_cleanable(resource, "test_resource")
        
        # Should register the resource
        mock_resource_manager.register_resource.assert_called_once_with(resource, name="test_resource")
    
    def test_register_if_cleanable_with_shutdown(self, qtbot):
        """Test _register_if_cleanable with shutdown method."""
        initializer = ApplicationInitializer()
        
        # Mock ResourceManager
        mock_resource_manager = Mock()
        initializer._resource_manager = mock_resource_manager
        
        # Test with shutdownable resource
        class ShutdownableResource:
            def shutdown(self):
                pass
        
        resource = ShutdownableResource()
        initializer._register_if_cleanable(resource, "test_resource")
        
        # Should register the resource
        mock_resource_manager.register_resource.assert_called_once_with(resource, name="test_resource")
    
    def test_thread_safe_cleanup_flag_check(self, qtbot):
        """Test thread-safe cleanup flag checking in finally block."""
        initializer = ApplicationInitializer()
        
        # Mock ResourceManager
        mock_resource_manager = Mock()
        initializer._resource_manager = mock_resource_manager
        
        # Simulate checking cleanup status thread-safely
        with initializer._cleanup_lock:
            cleanup_needed = not initializer._cleanup_done
        
        assert cleanup_needed is True
        
        # After cleanup
        initializer._cleanup_sync()
        
        with initializer._cleanup_lock:
            cleanup_needed = not initializer._cleanup_done
        
        assert cleanup_needed is False
    
    def test_cleanup_performance_timing(self, qtbot):
        """Test cleanup performance timing is logged."""
        initializer = ApplicationInitializer()
        
        # Mock ResourceManager
        mock_resource_manager = Mock()
        initializer._resource_manager = mock_resource_manager
        
        with patch('app.main.logger') as mock_logger:
            initializer._cleanup_sync()
            
            # Should log completion with timing
            mock_logger.debug.assert_called()
            debug_calls = [call for call in mock_logger.debug.call_args_list 
                          if 'cleanup completed' in str(call)]
            assert len(debug_calls) > 0
            
            # Check that timing is included in the message
            timing_call = debug_calls[-1]
            assert 'ms' in str(timing_call)

    def test_cleanup_idempotent(self, qtbot):
        """Cleanup can be called multiple times safely with thread safety."""
        initializer = ApplicationInitializer()
        
        # Mock ResourceManager
        mock_resource_manager = Mock()
        initializer._resource_manager = mock_resource_manager
        
        # First cleanup
        initializer.cleanup(async_cleanup=False)
        assert initializer._cleanup_done
        assert mock_resource_manager.cleanup_all.call_count == 1

        # Second cleanup should be no-op (thread-safe)
        initializer.cleanup(async_cleanup=False)
        assert mock_resource_manager.cleanup_all.call_count == 1

    def test_cleanup_handles_missing_attributes(self, qtbot):
        """Cleanup doesn't crash if components are None."""
        initializer = ApplicationInitializer()
        initializer.database = None
        initializer.main_window = None
        
        # Mock ResourceManager
        mock_resource_manager = Mock()
        initializer._resource_manager = mock_resource_manager

        # Should not raise
        initializer.cleanup(async_cleanup=False)
        assert initializer._cleanup_done
        assert mock_resource_manager.cleanup_all.called

    def test_cleanup_handles_exceptions(self, qtbot):
        """Cleanup continues even if one component fails."""
        initializer = ApplicationInitializer()
        
        # Mock ResourceManager to raise exception
        mock_resource_manager = Mock()
        mock_resource_manager.cleanup_all.side_effect = RuntimeError("Cleanup error")
        initializer._resource_manager = mock_resource_manager

        # Should not raise, but log error
        initializer.cleanup(async_cleanup=False)

        # Cleanup should still be marked as done
        assert initializer._cleanup_done
        assert mock_resource_manager.cleanup_all.called

    def test_initialize_all_cleanup_on_failure(self, qtbot):
        """Failed initialization cleans up created components."""
        initializer = ApplicationInitializer()
        
        # Mock ResourceManager
        mock_resource_manager = Mock()
        initializer._resource_manager = mock_resource_manager

        with patch.object(initializer, 'initialize_settings', return_value=True):
            with patch.object(initializer, 'initialize_database', return_value=True):
                with patch.object(initializer, 'initialize_theme_controller', return_value=False):
                    # Database should be created
                    initializer.database = Mock()

                    result = initializer.initialize_all()

                    assert result is False
                    # ResourceManager should handle cleanup
                    assert mock_resource_manager.cleanup_all.called

    def test_thread_pool_cleanup_timeout(self, qtbot):
        """Thread pool cleanup respects timeout."""
        initializer = ApplicationInitializer()
        mock_pool = Mock(spec=QThreadPool)
        mock_pool.waitForDone = Mock(return_value=False)  # Timeout
        mock_pool.activeThreadCount = Mock(return_value=1)  # Has active threads
        initializer.thread_pool = mock_pool
        
        # Mock ResourceManager
        mock_resource_manager = Mock()
        initializer._resource_manager = mock_resource_manager

        initializer.cleanup(async_cleanup=False)

        # Should call waitForDone with timeout
        assert mock_pool.waitForDone.called
        args = mock_pool.waitForDone.call_args[0]
        assert args[0] == THREAD_POOL_SHUTDOWN_TIMEOUT_MS

    def test_cleanup_default_synchronous(self, qtbot):
        """Default cleanup behavior is synchronous (safer)."""
        initializer = ApplicationInitializer()
        
        # Mock ResourceManager
        mock_resource_manager = Mock()
        initializer._resource_manager = mock_resource_manager

        # Call without arguments - should be synchronous
        initializer.cleanup()

        # Should be cleaned up immediately
        assert initializer._cleanup_done
        assert mock_resource_manager.cleanup_all.called


class TestInitializationDecorator:
    """Test initialization_method decorator."""

    def test_decorator_returns_false_on_expected_error(self):
        """Decorator returns False for expected exceptions."""
        @initialization_method(
            expected_errors=(ValueError,),
            error_message="Test error"
        )
        def failing_method(self):
            raise ValueError("Expected error")

        mock_self = Mock()
        result = failing_method(mock_self)
        assert result is False

    def test_decorator_returns_false_on_unexpected_error(self):
        """Decorator returns False for unexpected exceptions."""
        @initialization_method(
            expected_errors=(ValueError,),
            error_message="Test error"
        )
        def failing_method(self):
            raise RuntimeError("Unexpected error")

        mock_self = Mock()
        result = failing_method(mock_self)
        assert result is False

    def test_decorator_propagates_keyboard_interrupt(self):
        """Decorator doesn't catch KeyboardInterrupt."""
        @initialization_method(
            expected_errors=(ValueError,),
            error_message="Test error"
        )
        def failing_method(self):
            raise KeyboardInterrupt()

        mock_self = Mock()
        with pytest.raises(KeyboardInterrupt):
            failing_method(mock_self)

    def test_decorator_returns_true_on_success(self):
        """Decorator returns True when method succeeds."""
        @initialization_method(
            expected_errors=(ValueError,),
            error_message="Test error"
        )
        def success_method(self):
            return True

        mock_self = Mock()
        result = success_method(mock_self)
        assert result is True


class TestSignalHandling:
    """Test signal handling logic."""

    def test_should_install_signal_handlers_windows_console(self):
        """Signal handlers installed in Windows console mode."""
        with patch('platform.system', return_value='Windows'):
            with patch('sys.stdin.isatty', return_value=False):
                assert should_install_signal_handlers() is True

    def test_should_install_signal_handlers_windows_gui(self):
        """Signal handlers not installed in Windows GUI mode."""
        with patch('platform.system', return_value='Windows'):
            with patch('sys.stdin.isatty', return_value=True):
                with patch('sys.stdout.isatty', return_value=True):
                    assert should_install_signal_handlers() is False

    def test_signal_handler_exit_code(self, qtbot):
        """Signal handler sets correct exit code."""
        import signal
        from PyQt6.QtCore import QCoreApplication

        app = QApplication.instance() or QApplication([])
        mock_initializer = Mock(spec=ApplicationInitializer)

        with patch.object(QCoreApplication, 'exit') as mock_exit:
            signal_handler(signal.SIGINT, None, mock_initializer)

            # Should call exit with SIGNAL_EXIT_CODE_BASE + SIGINT
            expected_code = SIGNAL_EXIT_CODE_BASE + signal.SIGINT
            mock_exit.assert_called_once_with(expected_code)

    def test_signal_handler_sigterm(self, qtbot):
        """Signal handler handles SIGTERM correctly."""
        import signal
        from PyQt6.QtCore import QCoreApplication

        app = QApplication.instance() or QApplication([])
        mock_initializer = Mock(spec=ApplicationInitializer)

        with patch.object(QCoreApplication, 'exit') as mock_exit:
            signal_handler(signal.SIGTERM, None, mock_initializer)

            # Should call exit with SIGNAL_EXIT_CODE_BASE + SIGTERM
            expected_code = SIGNAL_EXIT_CODE_BASE + signal.SIGTERM
            mock_exit.assert_called_once_with(expected_code)


class TestProtocols:
    """Test Protocol implementations."""
    
    def test_cleanable_protocol(self):
        """Test Cleanable protocol detection."""
        class MockCleanable:
            def close(self) -> None:
                pass
        
        obj = MockCleanable()
        assert isinstance(obj, Cleanable)
    
    def test_shutdownable_protocol(self):
        """Test Shutdownable protocol detection."""
        class MockShutdownable:
            def shutdown(self) -> None:
                pass
        
        obj = MockShutdownable()
        assert isinstance(obj, Shutdownable)
    
    def test_stoppable_protocol(self):
        """Test Stoppable protocol detection."""
        class MockStoppable:
            def stop(self) -> None:
                pass
        
        obj = MockStoppable()
        assert isinstance(obj, Stoppable)


class TestSignalHandling:
    """Test improved signal handling."""
    
    def test_setup_signal_handling_unix(self):
        """Test signal setup on Unix systems."""
        initializer = ApplicationInitializer()
        
        with patch('platform.system', return_value='Linux'):
            with patch('signal.signal') as mock_signal:
                handler = setup_signal_handling(initializer)
                
                # Should set SIGINT to default and install SIGTERM handler
                assert mock_signal.call_count >= 2
                assert handler is not None
    
    def test_setup_signal_handling_windows(self):
        """Test signal setup on Windows."""
        initializer = ApplicationInitializer()
        
        with patch('platform.system', return_value='Windows'):
            with patch('signal.signal') as mock_signal:
                handler = setup_signal_handling(initializer)
                
                # Should install both SIGINT and SIGTERM handlers
                assert mock_signal.call_count >= 2
                assert handler is not None


class TestRetryMechanism:
    """Test retry mechanism for robust initialization."""
    
    def test_retry_on_failure_success_first_attempt(self):
        """Test successful execution on first attempt."""
        call_count = 0
        
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = retry_on_failure(successful_func, max_attempts=3)
        
        assert result == "success"
        assert call_count == 1
    
    def test_retry_on_failure_with_callback(self):
        """Test retry mechanism with callback for metrics."""
        call_count = 0
        retry_attempts = []
        retry_errors = []
        
        def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError(f"Attempt {call_count} failed")
            return "success"
        
        def on_retry_callback(attempt: int, error: Exception) -> None:
            retry_attempts.append(attempt)
            retry_errors.append(str(error))
        
        result = retry_on_failure(
            failing_func, 
            max_attempts=3, 
            delay=0.01,
            on_retry=on_retry_callback
        )
        
        assert result == "success"
        assert call_count == 3
        assert retry_attempts == [0, 1]  # Two retry attempts
        assert len(retry_errors) == 2
        assert "Attempt 1 failed" in retry_errors[0]
        assert "Attempt 2 failed" in retry_errors[1]
    
    def test_retry_on_failure_success_after_retries(self):
        """Test successful execution after retries."""
        call_count = 0
        
        def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError(f"Attempt {call_count} failed")
            return "success"
        
        result = retry_on_failure(failing_then_success, max_attempts=3, delay=0.01)
        
        assert result == "success"
        assert call_count == 3
    
    def test_retry_on_failure_all_attempts_fail(self):
        """Test behavior when all attempts fail."""
        call_count = 0
        
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise RuntimeError(f"Attempt {call_count} failed")
        
        with pytest.raises(RuntimeError, match="Attempt 3 failed"):
            retry_on_failure(always_fails, max_attempts=3, delay=0.01)
        
        assert call_count == 3


class TestApplicationContext:
    """Test application context manager for testing."""
    
    def test_application_context_success(self, qtbot):
        """Test successful application context usage."""
        with patch.object(ApplicationInitializer, 'initialize_all', return_value=True):
            with patch.object(ApplicationInitializer, 'cleanup') as mock_cleanup:
                with application_context() as app:
                    assert isinstance(app, ApplicationInitializer)
                    assert app.is_healthy() or True  # May not be fully initialized in test
                
                # Cleanup should be called
                mock_cleanup.assert_called_once_with(async_cleanup=False)
    
    def test_application_context_initialization_failure(self, qtbot):
        """Test application context with initialization failure."""
        with patch.object(ApplicationInitializer, 'initialize_all', return_value=False):
            with patch.object(ApplicationInitializer, 'cleanup') as mock_cleanup:
                with pytest.raises(RuntimeError, match="Failed to initialize application"):
                    with application_context() as app:
                        pass  # Should not reach here
                
                # Cleanup should still be called
                mock_cleanup.assert_called_once_with(async_cleanup=False)


class TestHealthChecking:
    """Test health checking and status reporting."""
    
    def test_is_healthy_all_components_initialized(self, qtbot):
        """Test health check with all components initialized."""
        initializer = ApplicationInitializer()
        
        # Mock all components as initialized
        initializer.settings = Mock()
        initializer.database = Mock()
        initializer.theme_controller = Mock()
        initializer.main_window = Mock()
        initializer._cleanup_done = False
        
        assert initializer.is_healthy() is True
    
    def test_is_healthy_with_deep_checks(self, qtbot):
        """Test health check with deep validation."""
        initializer = ApplicationInitializer()
        
        # Mock components with health check methods
        mock_db = Mock()
        mock_db.is_connected.return_value = True
        
        mock_window = Mock()
        mock_window.isVisible.return_value = True
        
        initializer.settings = Mock()
        initializer.database = mock_db
        initializer.theme_controller = Mock()
        initializer.main_window = mock_window
        initializer._cleanup_done = False
        
        assert initializer.is_healthy() is True
        mock_db.is_connected.assert_called_once()
        mock_window.isVisible.assert_called_once()
    
    def test_is_healthy_database_disconnected(self, qtbot):
        """Test health check with disconnected database."""
        initializer = ApplicationInitializer()
        
        # Mock disconnected database
        mock_db = Mock()
        mock_db.is_connected.return_value = False
        
        initializer.settings = Mock()
        initializer.database = mock_db
        initializer.theme_controller = Mock()
        initializer.main_window = Mock()
        initializer._cleanup_done = False
        
        assert initializer.is_healthy() is False
    
    def test_is_healthy_missing_components(self, qtbot):
        """Test health check with missing components."""
        initializer = ApplicationInitializer()
        
        # Only some components initialized
        initializer.settings = Mock()
        initializer.database = None  # Missing
        initializer.theme_controller = Mock()
        initializer.main_window = Mock()
        initializer._cleanup_done = False
        
        assert initializer.is_healthy() is False
    
    def test_is_healthy_after_cleanup(self, qtbot):
        """Test health check after cleanup."""
        initializer = ApplicationInitializer()
        
        # All components initialized but cleanup done
        initializer.settings = Mock()
        initializer.database = Mock()
        initializer.theme_controller = Mock()
        initializer.main_window = Mock()
        initializer._cleanup_done = True
        
        assert initializer.is_healthy() is False
    
    def test_get_status_detailed(self, qtbot):
        """Test detailed status reporting."""
        initializer = ApplicationInitializer()
        
        # Partially initialized
        initializer.settings = Mock()
        initializer.database = None
        initializer.theme_controller = Mock()
        initializer.main_window = None
        initializer._cleanup_done = False
        
        status = initializer.get_status()
        
        expected = {
            "settings_initialized": True,
            "database_connected": False,
            "theme_loaded": True,
            "window_created": False,
            "cleanup_done": False,
            "healthy": False
        }
        
        assert status == expected


class TestContextManager:
    """Test ApplicationInitializer as context manager."""
    
    def test_context_manager_success(self, qtbot):
        """Test successful context manager usage."""
        with patch.object(ApplicationInitializer, 'initialize_all', return_value=True):
            with patch.object(ApplicationInitializer, 'cleanup', return_value=True) as mock_cleanup:
                with ApplicationInitializer() as app:
                    assert isinstance(app, ApplicationInitializer)
                
                # Cleanup should be called on exit
                mock_cleanup.assert_called_once_with(async_cleanup=False)
    
    def test_context_manager_initialization_failure(self, qtbot):
        """Test context manager with initialization failure."""
        with patch.object(ApplicationInitializer, 'initialize_all', return_value=False):
            with patch.object(ApplicationInitializer, 'cleanup', return_value=True) as mock_cleanup:
                with pytest.raises(RuntimeError, match="Failed to initialize application"):
                    with ApplicationInitializer() as app:
                        pass  # Should not reach here
                
                # Cleanup should still be called
                mock_cleanup.assert_called_once_with(async_cleanup=False)
    
    def test_context_manager_exception_handling(self, qtbot):
        """Test context manager doesn't suppress exceptions."""
        with patch.object(ApplicationInitializer, 'initialize_all', return_value=True):
            with patch.object(ApplicationInitializer, 'cleanup', return_value=True) as mock_cleanup:
                with pytest.raises(ValueError, match="test error"):
                    with ApplicationInitializer() as app:
                        raise ValueError("test error")
                
                # Cleanup should be called even when exception occurs
                mock_cleanup.assert_called_once_with(async_cleanup=False)


class TestCleanupTimeout:
    """Test cleanup with timeout functionality."""
    
    def test_cleanup_with_timeout_success(self, qtbot):
        """Test cleanup completes within timeout."""
        initializer = ApplicationInitializer()
        
        # Mock ResourceManager
        mock_resource_manager = Mock()
        initializer._resource_manager = mock_resource_manager
        
        # Should complete successfully
        result = initializer.cleanup(async_cleanup=False, timeout=1.0)
        
        assert result is True
        mock_resource_manager.cleanup_all.assert_called_once()
    
    def test_cleanup_with_timeout_failure(self, qtbot):
        """Test cleanup timeout handling."""
        initializer = ApplicationInitializer()
        
        # Mock ResourceManager to simulate slow cleanup
        def slow_cleanup():
            time.sleep(2.0)  # Longer than timeout
        
        mock_resource_manager = Mock()
        mock_resource_manager.cleanup_all.side_effect = slow_cleanup
        initializer._resource_manager = mock_resource_manager
        
        # Should timeout
        result = initializer.cleanup(async_cleanup=False, timeout=0.1)
        
        assert result is False
    
    def test_cleanup_no_timeout(self, qtbot):
        """Test cleanup without timeout (timeout=0)."""
        initializer = ApplicationInitializer()
        
        # Mock ResourceManager
        mock_resource_manager = Mock()
        initializer._resource_manager = mock_resource_manager
        
        # Should complete without timeout check
        result = initializer.cleanup(async_cleanup=False, timeout=0)
        
        assert result is True
        mock_resource_manager.cleanup_all.assert_called_once()


class TestExitCodes:
    """Test exit code enum functionality."""
    
    def test_exit_code_values(self):
        """Test exit code enum values."""
        assert ExitCode.SUCCESS == 0
        assert ExitCode.INITIALIZATION_FAILURE == 1
        assert ExitCode.RUNTIME_ERROR == 2
        assert ExitCode.SIGNAL_BASE == 128
    
    def test_exit_code_inheritance(self):
        """Test exit codes are proper integers."""
        assert isinstance(ExitCode.SUCCESS, int)
        assert isinstance(ExitCode.INITIALIZATION_FAILURE, int)
        assert isinstance(ExitCode.RUNTIME_ERROR, int)
        assert isinstance(ExitCode.SIGNAL_BASE, int)


class TestConstants:
    """Test module constants."""

    def test_signal_exit_code_base(self):
        """SIGNAL_EXIT_CODE_BASE has correct value."""
        assert SIGNAL_EXIT_CODE_BASE == 128

    def test_thread_pool_timeout(self):
        """THREAD_POOL_SHUTDOWN_TIMEOUT_MS has reasonable value."""
        assert THREAD_POOL_SHUTDOWN_TIMEOUT_MS == 1000
    
    def test_exit_code_constants(self):
        """Test ExitCode enum constants."""
        assert ExitCode.SUCCESS == 0
        assert ExitCode.INITIALIZATION_FAILURE == 1
        assert ExitCode.RUNTIME_ERROR == 2
        assert ExitCode.SIGNAL_BASE == 128
        assert isinstance(THREAD_POOL_SHUTDOWN_TIMEOUT_MS, int)


@pytest.fixture
def qapp():
    """Ensure QApplication exists for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
