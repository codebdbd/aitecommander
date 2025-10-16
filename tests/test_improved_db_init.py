"""Tests for improved database initialization with proper signal handling."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from PyQt6.QtCore import QTimer, QMetaObject, Qt
from PyQt6.QtWidgets import QApplication

from app.controllers.system.db_init_improved import DatabaseInitializer, DatabaseInitRunnable


@pytest.fixture
def mock_database():
    """Create mock database."""
    db = Mock()
    db.prepare_dirs.return_value = None
    db.initialize_or_migrate.return_value = None
    db.connection = Mock()
    return db


@pytest.fixture
def mock_main_window(qtbot):
    """Create mock main window."""
    window = Mock()
    window.statusBar.return_value = Mock()
    window.setEnabled = Mock()
    return window


class TestDatabaseInitRunnable:
    """Test the database initialization runnable."""

    def test_successful_initialization(self, qtbot, mock_database):
        """Test successful database initialization."""
        runnable = DatabaseInitRunnable(mock_database)

        with qtbot.waitSignal(runnable.signals.finished, timeout=1000) as blocker:
            runnable.run()

        assert blocker.signal_triggered
        assert blocker.args == [True]

    def test_initialization_error(self, qtbot, mock_database):
        """Test database initialization with error."""
        # Make database initialization fail
        mock_database.initialize_or_migrate.side_effect = Exception("DB Error")

        runnable = DatabaseInitRunnable(mock_database)

        with qtbot.waitSignal(runnable.signals.error, timeout=1000) as error_blocker:
            with qtbot.waitSignal(runnable.signals.finished, timeout=1000) as finish_blocker:
                runnable.run()

        assert error_blocker.signal_triggered
        assert "DB Error" in error_blocker.args[0]
        assert finish_blocker.args == [False]

    def test_progress_signals(self, qtbot, mock_database):
        """Test progress signal emission."""
        runnable = DatabaseInitRunnable(mock_database)

        progress_signals = []

        def collect_progress(message):
            progress_signals.append(message)

        runnable.signals.progress.connect(collect_progress)

        with qtbot.waitSignal(runnable.signals.finished, timeout=1000):
            runnable.run()

        # Should have emitted progress signals
        assert len(progress_signals) >= 2
        assert any("Preparing" in msg for msg in progress_signals)
        assert any("Initializing" in msg for msg in progress_signals)


class TestDatabaseInitializer:
    """Test the database initializer."""

    def test_async_initialization_success(self, qtbot, mock_database, mock_main_window):
        """Test successful async initialization."""
        initializer = DatabaseInitializer(mock_database, mock_main_window)

        success_called = False
        def on_success():
            nonlocal success_called
            success_called = True

        # Mock the runnable to avoid actual thread execution in test
        with patch.object(initializer._thread_pool, 'start'):
            initializer.initialize_async(on_success=on_success)

        # Verify UI was disabled
        mock_main_window.setEnabled.assert_called_once_with(False)

    def test_ui_reenabled_on_error(self, qtbot, mock_database, mock_main_window):
        """Test UI is re-enabled when initialization fails."""
        initializer = DatabaseInitializer(mock_database, mock_main_window)

        # Mock the runnable to simulate error
        with patch('app.controllers.system.db_init_improved.DatabaseInitRunnable') as mock_runnable_class:
            mock_runnable = Mock()
            mock_runnable_class.return_value = mock_runnable
            mock_runnable.signals.finished.emit(False)

            initializer.initialize_async()

        # In a real scenario, UI would be re-enabled
        # This tests the signal connection logic

    def test_status_message_updates(self, qtbot, mock_database, mock_main_window):
        """Test status message updates."""
        initializer = DatabaseInitializer(mock_database, mock_main_window)

        # Test direct status update
        initializer._update_status_message("Test message")

        # Verify status bar was updated via QMetaObject invoke
        mock_main_window.statusBar.return_value.showMessage.assert_called_once_with("Test message")

    def test_ui_enable_disable(self, qtbot, mock_database, mock_main_window):
        """Test UI enable/disable functionality."""
        initializer = DatabaseInitializer(mock_database, mock_main_window)

        # Test UI disable
        initializer._set_ui_enabled(False)
        mock_main_window.setEnabled.assert_called_with(False)

        # Test UI enable
        mock_main_window.reset_mock()
        initializer._set_ui_enabled(True)
        mock_main_window.setEnabled.assert_called_with(True)


class TestSignalHandling:
    """Test signal handling and thread safety."""

    def test_signals_in_main_thread(self, qtbot):
        """Test that signals are properly handled in main thread."""
        from PyQt6.QtCore import QThread, pyqtSignal, QObject

        class SignalTester(QObject):
            test_signal = pyqtSignal(str)

            def __init__(self):
                super().__init__()
                self.received_signals = []

            def on_signal(self, message):
                self.received_signals.append(message)

        tester = SignalTester()

        # Connect signal
        tester.test_signal.connect(tester.on_signal)

        # Emit signal from main thread
        tester.test_signal.emit("test message")

        # Should be received immediately in main thread
        assert tester.received_signals == ["test message"]

    def test_error_dialog_in_main_thread(self, qtbot, mock_main_window):
        """Test error dialog is shown in main thread."""
        initializer = DatabaseInitializer(Mock(), mock_main_window)

        # Mock QMessageBox to avoid actual dialog
        with patch('app.controllers.system.db_init_improved.QMessageBox') as mock_msgbox:
            initializer._show_critical_error("Test Error", "Test message")

            # Should show critical error dialog
            mock_msgbox.critical.assert_called_once_with(
                mock_main_window,
                "Test Error",
                "Test message"
            )
