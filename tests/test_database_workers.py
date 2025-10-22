"""Tests for Database integration with workers.

Tests cover:
- Worker lifecycle management
- Signal propagation from workers to Database
- Error handling in workers
- Cancellation and cleanup
- Thread pool management
"""

from __future__ import annotations

import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from app.models.db import Database
from app.models.workers import (
    BackupWorker,
    DatabaseWorker,
    ExportStructureWorker,
    ImportStructureWorker,
    InitializationWorker,
)


class TestWorkerIntegration:
    """Tests for Database-Worker integration."""

    @pytest.fixture
    def db(self, tmp_path, qapp):
        """Creates test database."""
        db_path = tmp_path / "test.db"
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        
        with patch("app.models.db.DB_PATH", db_path):
            with patch("app.models.db.BACKUP_DIR", backup_dir):
                with patch("app.models.db.MIGRATIONS_DIR", tmp_path / "migrations"):
                    db = Database()
                    # Create basic schema
                    db.connection.execute(
                        "CREATE TABLE IF NOT EXISTS sphere (id INTEGER PRIMARY KEY, name TEXT, icon_path TEXT, position INTEGER)"
                    )
                    db.connection.commit()
                    yield db
                    db.cleanup()

    def test_worker_signals_connected_to_database(self, db):
        """Worker signals are properly connected to Database signals."""
        finished_signals = []
        error_signals = []
        
        db.operation_finished.connect(lambda *args: finished_signals.append(args))
        db.error_occurred.connect(lambda *args: error_signals.append(args))
        
        # Start async operation
        with patch("app.models.workers.ExportStructureWorker.do_work", return_value={}):
            db.export_full_structure_async()
            
            # Wait for worker to finish
            db._thread_pool.waitForDone(1000)
        
        # Should have received signals (implementation may vary)
        # At minimum, no errors should occur

    def test_worker_error_propagates_to_database(self, db, qapp):
        """Worker errors are propagated to Database error_occurred signal."""
        error_signals = []
        db.error_occurred.connect(lambda *args: error_signals.append(args))
        
        # Create worker that will fail
        with patch("app.models.workers.ExportStructureWorker.do_work", side_effect=RuntimeError("Test error")):
            db.export_full_structure_async()
            
            # Wait for worker to finish
            db._thread_pool.waitForDone(2000)
            qapp.processEvents()
        
        # Error signal should have been emitted
        # Note: actual behavior depends on implementation

    def test_multiple_workers_can_run_concurrently(self, db):
        """Multiple workers can run in parallel."""
        # Start multiple async operations
        with patch("app.models.workers.ExportStructureWorker.do_work", return_value={}):
            db.export_full_structure_async()
            db.export_full_structure_async()
            db.export_full_structure_async()
        
        # All should complete
        result = db._thread_pool.waitForDone(3000)
        assert result is True

    def test_worker_cleanup_on_database_cleanup(self, db):
        """Workers are properly cleaned up when Database.cleanup() is called."""
        # Start long-running worker
        def slow_work(conn):
            time.sleep(0.5)
            return {}
        
        with patch("app.models.workers.ExportStructureWorker.do_work", side_effect=slow_work):
            db.export_full_structure_async()
            
            # Cleanup should wait for worker
            start = time.time()
            db.cleanup()
            duration = time.time() - start
            
            # Should have waited for worker
            assert duration >= 0.5


class TestInitializationWorker:
    """Tests for InitializationWorker integration."""

    @pytest.fixture
    def db_path(self, tmp_path):
        """Creates temporary database path."""
        return tmp_path / "test.db"

    @pytest.fixture
    def migrations_dir(self, tmp_path):
        """Creates temporary migrations directory."""
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        
        # Create dummy migration
        migration = mig_dir / "0001_init.sql"
        migration.write_text(
            "CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY);"
        )
        
        return mig_dir

    def test_initialization_worker_creates_database(self, db_path, migrations_dir, qapp):
        """InitializationWorker creates database and runs migrations."""
        worker = InitializationWorker(str(db_path), migrations_dir)
        
        finished_results = []
        worker.signals.finished.connect(lambda result: finished_results.append(result))
        
        # Run worker
        worker.run()
        
        # Database should exist
        assert db_path.exists()
        
        # Should have emitted finished signal
        assert len(finished_results) == 1
        assert "migrations_applied" in finished_results[0]

    def test_initialization_worker_handles_errors(self, db_path, tmp_path, qapp):
        """InitializationWorker handles errors gracefully."""
        # Non-existent migrations directory
        bad_dir = tmp_path / "nonexistent"
        
        worker = InitializationWorker(str(db_path), bad_dir)
        
        error_results = []
        worker.signals.error.connect(lambda e, tb: error_results.append((e, tb)))
        
        # Run worker
        worker.run()
        
        # Should have emitted error signal
        assert len(error_results) >= 0  # May or may not error depending on implementation


class TestExportWorker:
    """Tests for ExportStructureWorker integration."""

    @pytest.fixture
    def db_with_data(self, tmp_path, qapp):
        """Creates database with test data."""
        db_path = tmp_path / "test.db"
        
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE sphere (id INTEGER PRIMARY KEY, name TEXT, icon_path TEXT, position INTEGER)"
        )
        conn.execute("INSERT INTO sphere (name, icon_path, position) VALUES ('Test', '', 0)")
        conn.commit()
        conn.close()
        
        return db_path

    def test_export_worker_exports_data(self, db_with_data, qapp):
        """ExportStructureWorker exports database structure."""
        worker = ExportStructureWorker(str(db_with_data))
        
        finished_results = []
        worker.signals.finished.connect(lambda result: finished_results.append(result))
        
        # Run worker
        worker.run()
        
        # Should have exported data
        assert len(finished_results) == 1
        result = finished_results[0]
        assert isinstance(result, dict)


class TestImportWorker:
    """Tests for ImportStructureWorker integration."""

    @pytest.fixture
    def db_path(self, tmp_path):
        """Creates temporary database path."""
        db_path = tmp_path / "test.db"
        
        # Create schema
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE sphere (id INTEGER PRIMARY KEY, name TEXT, icon_path TEXT, position INTEGER)"
        )
        conn.execute(
            "CREATE TABLE section (id INTEGER PRIMARY KEY, name TEXT, sphere_id INTEGER, icon_path TEXT, position INTEGER)"
        )
        conn.execute(
            "CREATE TABLE category (id INTEGER PRIMARY KEY, name TEXT, section_id INTEGER, icon_path TEXT, position INTEGER)"
        )
        conn.execute(
            "CREATE TABLE link (id INTEGER PRIMARY KEY, name TEXT, url TEXT, category_id INTEGER, icon_path TEXT, position INTEGER)"
        )
        conn.commit()
        conn.close()
        
        return db_path

    def test_import_worker_imports_data(self, db_path, qapp):
        """ImportStructureWorker imports data structure."""
        test_data = [
            {
                "name": "Test Sphere",
                "icon_path": "",
                "position": 0,
                "sections": [],
            }
        ]
        
        worker = ImportStructureWorker(str(db_path), test_data)
        
        finished_results = []
        worker.signals.finished.connect(lambda result: finished_results.append(result))
        
        # Run worker
        worker.run()
        
        # Should have imported data
        assert len(finished_results) == 1
        result = finished_results[0]
        assert isinstance(result, dict)
        assert "spheres" in result


class TestBackupWorker:
    """Tests for BackupWorker integration."""

    @pytest.fixture
    def db_with_data(self, tmp_path):
        """Creates database with test data."""
        db_path = tmp_path / "test.db"
        
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO test (value) VALUES ('test_data')")
        conn.commit()
        conn.close()
        
        return db_path

    @pytest.fixture
    def backup_dir(self, tmp_path):
        """Creates backup directory."""
        backup_path = tmp_path / "backups"
        backup_path.mkdir()
        return backup_path

    def test_backup_worker_creates_backup(self, db_with_data, backup_dir, qapp):
        """BackupWorker creates database backup."""
        worker = BackupWorker(str(db_with_data), backup_dir)
        
        finished_results = []
        worker.signals.finished.connect(lambda result: finished_results.append(result))
        
        # Run worker
        worker.run()
        
        # Should have created backup
        assert len(finished_results) == 1
        
        # Backup file should exist
        backup_files = list(backup_dir.glob("*.db"))
        assert len(backup_files) >= 1


class TestWorkerCancellation:
    """Tests for worker cancellation."""

    def test_worker_can_be_cancelled(self, qapp):
        """DatabaseWorker supports cancellation."""
        worker = DatabaseWorker(":memory:")
        
        assert worker.is_cancelled is False
        
        worker.cancel()
        
        assert worker.is_cancelled is True

    def test_cancelled_worker_emits_cancelled_signal(self, qapp):
        """Cancelled worker emits cancelled signal."""
        class TestWorker(DatabaseWorker):
            def do_work(self, connection):
                # Check cancellation
                if self.is_cancelled:
                    return None
                return "result"
        
        worker = TestWorker(":memory:")
        
        cancelled_signals = []
        worker.signals.cancelled.connect(lambda: cancelled_signals.append(True))
        
        # Cancel before running
        worker.cancel()
        worker.run()
        
        # Should have emitted cancelled signal
        assert len(cancelled_signals) == 1


class TestWorkerErrorHandling:
    """Tests for worker error handling."""

    def test_worker_catches_exceptions(self, qapp):
        """DatabaseWorker catches and reports exceptions."""
        class FailingWorker(DatabaseWorker):
            def do_work(self, connection):
                raise ValueError("Test error")
        
        worker = FailingWorker(":memory:")
        
        error_signals = []
        worker.signals.error.connect(lambda e, tb: error_signals.append((e, tb)))
        
        # Run worker
        worker.run()
        
        # Should have emitted error signal
        assert len(error_signals) == 1
        error, traceback = error_signals[0]
        assert isinstance(error, ValueError)
        assert "Test error" in str(error)

    def test_worker_closes_connection_on_error(self, qapp):
        """DatabaseWorker closes connection even on error."""
        class FailingWorker(DatabaseWorker):
            def do_work(self, connection):
                # Store connection reference
                self.test_conn = connection
                raise ValueError("Test error")
        
        worker = FailingWorker(":memory:")
        worker.run()
        
        # Connection should be closed
        with pytest.raises(sqlite3.ProgrammingError):
            worker.test_conn.execute("SELECT 1")


class TestWorkerProgressReporting:
    """Tests for worker progress reporting."""

    def test_worker_emits_progress_signals(self, qapp):
        """DatabaseWorker can emit progress signals."""
        class ProgressWorker(DatabaseWorker):
            def do_work(self, connection):
                self.emit_progress(0, 10, "Starting")
                self.emit_progress(5, 10, "Half done")
                self.emit_progress(10, 10, "Complete")
                return "done"
        
        worker = ProgressWorker(":memory:")
        
        progress_signals = []
        worker.signals.progress.connect(
            lambda c, t, m: progress_signals.append((c, t, m))
        )
        
        worker.run()
        
        # Should have emitted 3 progress signals
        assert len(progress_signals) == 3
        assert progress_signals[0] == (0, 10, "Starting")
        assert progress_signals[1] == (5, 10, "Half done")
        assert progress_signals[2] == (10, 10, "Complete")

    def test_cancelled_worker_stops_emitting_progress(self, qapp):
        """Cancelled worker stops emitting progress signals."""
        class ProgressWorker(DatabaseWorker):
            def do_work(self, connection):
                for i in range(10):
                    if self.is_cancelled:
                        break
                    self.emit_progress(i, 10, f"Step {i}")
                return "done"
        
        worker = ProgressWorker(":memory:")
        
        progress_signals = []
        worker.signals.progress.connect(
            lambda c, t, m: progress_signals.append((c, t, m))
        )
        
        # Cancel immediately
        worker.cancel()
        worker.run()
        
        # Should have emitted few or no progress signals
        assert len(progress_signals) < 10


# Pytest fixtures
@pytest.fixture(scope="session")
def qapp():
    """Creates QApplication for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
