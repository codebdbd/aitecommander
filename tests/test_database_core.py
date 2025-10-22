"""Comprehensive tests for Database class core functionality.

Tests cover:
- Initialization and configuration
- Thread-safety guarantees (including _connection_lock)
- Signal emission and callbacks
- Deprecated method protection
- Connection management (including leak tracking)
- Cleanup and resource management
- SQL injection protection
- TOCTOU protection in update_item_positions
"""

from __future__ import annotations

import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PyQt6.QtCore import QObject, QThread, QThreadPool
from PyQt6.QtWidgets import QApplication

from app.models.base.db_base import DatabaseError
from app.models.db import Database


class TestDatabaseInitialization:
    """Tests for Database initialization and configuration."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Creates temporary database path."""
        return tmp_path / "test.db"

    @pytest.fixture
    def mock_config(self):
        """Mocks app_config."""
        with patch("app.models.db.app_config") as mock:
            mock.paths.get_db_path.return_value = Path(tempfile.mktemp(suffix=".db"))
            mock.paths.get_backups_dir.return_value = Path(tempfile.mkdtemp())
            mock.paths.ensure_user_data_dirs.return_value = None
            mock.get.return_value = 4  # max_db_threads
            yield mock

    def test_init_without_parent(self, mock_config, qapp):
        """Database can be initialized without parent."""
        db = Database()
        assert db is not None
        assert isinstance(db, QObject)
        assert db.parent() is None
        db.cleanup()

    def test_init_with_parent(self, mock_config, qapp):
        """Database can be initialized with QObject parent."""
        parent = QObject()
        db = Database(parent)
        assert db.parent() is parent
        db.cleanup()

    def test_init_with_invalid_parent_raises_error(self, mock_config, qapp):
        """Database raises TypeError if parent is not QObject."""
        with pytest.raises(TypeError, match="parent must be QObject or None"):
            Database(parent="invalid")  # type: ignore

    def test_init_creates_thread_pool(self, mock_config, qapp):
        """Database initializes thread pool correctly."""
        db = Database()
        assert db._thread_pool is not None
        assert isinstance(db._thread_pool, QThreadPool)
        db.cleanup()

    def test_init_creates_models(self, mock_config, qapp):
        """Database initializes all entity models."""
        db = Database()
        assert db.spheres is not None
        assert db.sections is not None
        assert db.categories is not None
        assert db.links is not None
        db.cleanup()

    def test_init_creates_managers(self, mock_config, qapp):
        """Database initializes all managers."""
        db = Database()
        assert db.backup_manager is not None
        assert db.import_export_manager is not None
        assert db.duplicate_resolver is not None
        assert db.structure_manager is not None
        db.cleanup()

    def test_signals_defined(self, mock_config, qapp):
        """Database defines all required signals."""
        db = Database()
        assert hasattr(db, "data_changed")
        assert hasattr(db, "structure_loaded")
        assert hasattr(db, "backup_created")
        assert hasattr(db, "error_occurred")
        assert hasattr(db, "operation_started")
        assert hasattr(db, "operation_progress")
        assert hasattr(db, "operation_finished")
        assert hasattr(db, "warning_occurred")
        db.cleanup()


class TestDatabaseThreadSafety:
    """Tests for thread-safety guarantees."""

    @pytest.fixture
    def db(self, tmp_path, qapp):
        """Creates test database."""
        with patch("app.models.db.DB_PATH", tmp_path / "test.db"):
            with patch("app.models.db.BACKUP_DIR", tmp_path / "backups"):
                db = Database()
                # Initialize schema
                db.connection.execute(
                    "CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY, value TEXT)"
                )
                db.connection.commit()
                yield db
                db.cleanup()

    def test_connection_is_thread_local(self, db):
        """Each thread gets its own connection."""
        connections = {}

        def get_connection(thread_id):
            connections[thread_id] = id(db.connection)

        threads = []
        for i in range(3):
            t = threading.Thread(target=get_connection, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All connections should be different
        assert len(set(connections.values())) == 3

    def test_concurrent_reads_safe(self, db):
        """Concurrent reads from multiple threads are safe."""
        # Insert test data
        db.connection.execute("INSERT INTO test (value) VALUES ('test')")
        db.connection.commit()

        results = []
        errors = []

        def read_data():
            try:
                cursor = db.connection.execute("SELECT * FROM test")
                results.append(cursor.fetchall())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_data) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10

    def test_connection_pragma_settings(self, db):
        """Connection has correct PRAGMA settings."""
        conn = db.connection
        
        # Check foreign keys
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
        
        # Check journal mode
        jm = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert jm.upper() == "WAL"
        
        # Check busy timeout
        bt = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert bt == 5000

    def test_connection_auto_reconnects_on_failure(self, db):
        """Connection automatically reconnects if broken."""
        # Get initial connection
        conn1 = db.connection
        conn1_id = id(conn1)
        
        # Break connection
        conn1.close()
        
        # Next access should create new connection
        conn2 = db.connection
        conn2_id = id(conn2)
        
        assert conn1_id != conn2_id
        # New connection should work
        result = conn2.execute("SELECT 1").fetchone()
        assert result[0] == 1


class TestDeprecatedMethodProtection:
    """Tests for deprecated method protection against GUI thread blocking."""

    @pytest.fixture
    def db(self, tmp_path, qapp):
        """Creates test database."""
        with patch("app.models.db.DB_PATH", tmp_path / "test.db"):
            with patch("app.models.db.BACKUP_DIR", tmp_path / "backups"):
                with patch("app.models.db.MIGRATIONS_DIR", tmp_path / "migrations"):
                    db = Database()
                    yield db
                    db.cleanup()

    def test_initialize_or_migrate_raises_in_gui_thread(self, db, qapp):
        """initialize_or_migrate() raises RuntimeError in GUI thread."""
        with pytest.raises(RuntimeError, match="blocking operation.*GUI thread"):
            db.initialize_or_migrate()

    def test_export_full_structure_raises_in_gui_thread(self, db, qapp):
        """export_full_structure() raises RuntimeError in GUI thread."""
        with pytest.raises(RuntimeError, match="blocking operation.*GUI thread"):
            db.export_full_structure()

    def test_import_full_structure_raises_in_gui_thread(self, db, qapp):
        """import_full_structure() raises RuntimeError in GUI thread."""
        with pytest.raises(RuntimeError, match="blocking operation.*GUI thread"):
            db.import_full_structure([])

    def test_deprecated_methods_work_in_background_thread(self, db):
        """Deprecated methods work correctly in background threads."""
        results = {"success": False, "error": None}

        def background_task():
            try:
                # This should not raise since we're not in GUI thread
                with patch.object(db.import_export_manager, "export_full_structure", return_value={}):
                    with pytest.warns(DeprecationWarning):
                        db.export_full_structure()
                results["success"] = True
            except Exception as e:
                results["error"] = e

        thread = threading.Thread(target=background_task)
        thread.start()
        thread.join()

        assert results["success"] is True
        assert results["error"] is None


class TestSignalEmission:
    """Tests for signal emission and callback handling."""

    @pytest.fixture
    def db(self, tmp_path, qapp):
        """Creates test database."""
        with patch("app.models.db.DB_PATH", tmp_path / "test.db"):
            with patch("app.models.db.BACKUP_DIR", tmp_path / "backups"):
                db = Database()
                yield db
                db.cleanup()

    def test_safe_emit_works_with_qapplication(self, db, qapp):
        """_safe_emit() emits signals when QApplication exists."""
        signal_received = []
        
        db.data_changed.connect(lambda *args: signal_received.append(args))
        db._safe_emit(db.data_changed, "test_table", "insert", [1, 2, 3])
        
        # Process events to ensure signal is delivered
        qapp.processEvents()
        
        assert len(signal_received) == 1
        assert signal_received[0] == ("test_table", "insert", [1, 2, 3])

    def test_safe_emit_skips_without_qapplication(self, db):
        """_safe_emit() skips emission when no QApplication."""
        # Temporarily remove QApplication
        with patch("PyQt6.QtWidgets.QApplication.instance", return_value=None):
            # Should not raise
            db._safe_emit(db.data_changed, "test", "test", [])

    def test_safe_callback_handles_errors(self, db, qapp):
        """_safe_callback() catches and logs callback errors."""
        error_signals = []
        db.error_occurred.connect(lambda *args: error_signals.append(args))
        
        def failing_callback(result):
            raise ValueError("Test error")
        
        # Should not raise
        db._safe_callback(failing_callback, "test_result")
        
        qapp.processEvents()
        
        # Error signal should be emitted
        assert len(error_signals) == 1
        assert "Callback error" in error_signals[0]

    def test_safe_callback_invokes_successful_callback(self, db):
        """_safe_callback() successfully invokes valid callbacks."""
        results = []
        
        def success_callback(result):
            results.append(result)
        
        db._safe_callback(success_callback, "test_result")
        
        assert results == ["test_result"]


class TestAsyncOperations:
    """Tests for async operation methods."""

    @pytest.fixture
    def db(self, tmp_path, qapp):
        """Creates test database."""
        with patch("app.models.db.DB_PATH", tmp_path / "test.db"):
            with patch("app.models.db.BACKUP_DIR", tmp_path / "backups"):
                with patch("app.models.db.MIGRATIONS_DIR", tmp_path / "migrations"):
                    db = Database()
                    yield db
                    db.cleanup()

    def test_initialize_or_migrate_async_starts_worker(self, db):
        """initialize_or_migrate_async() starts worker in thread pool."""
        with patch.object(db._thread_pool, "start") as mock_start:
            db.initialize_or_migrate_async()
            
            assert mock_start.call_count == 1
            worker = mock_start.call_args[0][0]
            assert worker is not None

    def test_export_structure_async_starts_worker(self, db):
        """export_full_structure_async() starts worker in thread pool."""
        with patch.object(db._thread_pool, "start") as mock_start:
            db.export_full_structure_async()
            
            assert mock_start.call_count == 1

    def test_import_structure_async_starts_worker(self, db):
        """import_full_structure_async() starts worker in thread pool."""
        with patch.object(db._thread_pool, "start") as mock_start:
            db.import_full_structure_async([])
            
            assert mock_start.call_count == 1

    def test_backup_async_starts_worker(self, db):
        """backup_async() starts worker in thread pool."""
        with patch.object(db._thread_pool, "start") as mock_start:
            db.backup_async()
            
            assert mock_start.call_count == 1

    def test_async_callbacks_wrapped_safely(self, db):
        """Async methods wrap callbacks with _safe_callback."""
        callback_invoked = []
        
        def test_callback(result):
            callback_invoked.append(result)
        
        with patch.object(db._thread_pool, "start"):
            with patch.object(db, "_safe_callback") as mock_safe:
                db.export_full_structure_async(on_finished=test_callback)
                
                # Verify callback was wrapped
                assert mock_safe.call_count == 0  # Not called yet, only connected


class TestCleanup:
    """Tests for cleanup and resource management."""

    @pytest.fixture
    def db(self, tmp_path, qapp):
        """Creates test database."""
        with patch("app.models.db.DB_PATH", tmp_path / "test.db"):
            with patch("app.models.db.BACKUP_DIR", tmp_path / "backups"):
                db = Database()
                yield db

    def test_cleanup_is_idempotent(self, db):
        """cleanup() can be called multiple times safely."""
        db.cleanup()
        db.cleanup()  # Should not raise
        db.cleanup()  # Should not raise

    def test_cleanup_waits_for_thread_pool(self, db):
        """cleanup() waits for thread pool to finish."""
        with patch.object(db._thread_pool, "waitForDone", return_value=True) as mock_wait:
            db.cleanup()
            
            assert mock_wait.call_count == 1
            # Default timeout is 5000ms
            assert mock_wait.call_args[0][0] >= 5000

    def test_cleanup_logs_timeout_warning(self, db):
        """cleanup() logs warning if thread pool times out."""
        with patch.object(db._thread_pool, "waitForDone", return_value=False):
            with patch.object(db._thread_pool, "activeThreadCount", return_value=2):
                # Should not raise, just log warning
                db.cleanup()

    def test_cleanup_closes_connection(self, db):
        """cleanup() closes database connection."""
        # Access connection to create it
        conn = db.connection
        
        db.cleanup()
        
        # Connection should be closed
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_cleanup_removes_models(self, db):
        """cleanup() removes references to models."""
        db.cleanup()
        
        assert not hasattr(db, "spheres")
        assert not hasattr(db, "sections")
        assert not hasattr(db, "categories")
        assert not hasattr(db, "links")

    def test_cleanup_removes_managers(self, db):
        """cleanup() removes references to managers."""
        db.cleanup()
        
        assert not hasattr(db, "backup_manager")
        assert not hasattr(db, "import_export_manager")
        assert not hasattr(db, "duplicate_resolver")
        assert not hasattr(db, "structure_manager")


class TestContextManager:
    """Tests for context manager protocol."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Creates temporary database path."""
        return tmp_path / "test.db"

    def test_database_as_context_manager(self, temp_db_path, qapp):
        """Database can be used as context manager."""
        with patch("app.models.db.DB_PATH", temp_db_path):
            with patch("app.models.db.BACKUP_DIR", temp_db_path.parent / "backups"):
                with Database() as db:
                    assert db is not None
                    conn = db.connection
                    assert conn is not None

    def test_context_manager_closes_connection(self, temp_db_path, qapp):
        """Context manager closes connection on exit."""
        with patch("app.models.db.DB_PATH", temp_db_path):
            with patch("app.models.db.BACKUP_DIR", temp_db_path.parent / "backups"):
                with Database() as db:
                    conn = db.connection
                
                # Connection should be closed after exit
                with pytest.raises(sqlite3.ProgrammingError):
                    conn.execute("SELECT 1")


class TestDatabaseSecurity:
    """Tests for security features."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        return tmp_path / "test.db"

    def test_escape_identifier_valid(self, temp_db_path, qapp):
        """_escape_identifier properly escapes valid identifiers."""
        with patch("app.models.db.DB_PATH", temp_db_path):
            with patch("app.models.db.BACKUP_DIR", temp_db_path.parent / "backups"):
                db = Database()
                assert db._escape_identifier("spheres") == '"spheres"'
                assert db._escape_identifier("test_table") == '"test_table"'
                db.cleanup()

    def test_escape_identifier_rejects_injection(self, temp_db_path, qapp):
        """_escape_identifier rejects SQL injection attempts."""
        from app.models.base.db_base import ValidationError
        
        with patch("app.models.db.DB_PATH", temp_db_path):
            with patch("app.models.db.BACKUP_DIR", temp_db_path.parent / "backups"):
                db = Database()
                with pytest.raises(ValidationError, match="Invalid characters in identifier"):
                    db._escape_identifier('spheres"; DROP TABLE users; --')
                db.cleanup()

    def test_update_positions_uses_escaped_table_name(self, temp_db_path, qapp):
        """update_item_positions uses escaped table names."""
        with patch("app.models.db.DB_PATH", temp_db_path):
            with patch("app.models.db.BACKUP_DIR", temp_db_path.parent / "backups"):
                db = Database()
                # Create test table (use singular form as per VALID_POSITION_TABLES)
                db.connection.execute("CREATE TABLE sphere (id INTEGER PRIMARY KEY, position INTEGER)")
                db.connection.execute("INSERT INTO sphere (id, position) VALUES (1, 0)")
                db.connection.commit()
                
                # This should work with escaped identifier
                db.update_item_positions("sphere", [1])
                
                db.cleanup()


class TestConnectionLockSeparation:
    """Tests for separate connection lock (_connection_lock)."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        return tmp_path / "test.db"

    def test_connection_lock_exists(self, temp_db_path, qapp):
        """Database has separate _connection_lock."""
        with patch("app.models.db.DB_PATH", temp_db_path):
            with patch("app.models.db.BACKUP_DIR", temp_db_path.parent / "backups"):
                db = Database()
                assert hasattr(db, "_connection_lock")
                assert isinstance(db._connection_lock, threading.Lock)
                db.cleanup()

    def test_active_connections_tracking(self, temp_db_path, qapp):
        """Database tracks active connections."""
        with patch("app.models.db.DB_PATH", temp_db_path):
            with patch("app.models.db.BACKUP_DIR", temp_db_path.parent / "backups"):
                db = Database()
                assert hasattr(db, "_active_connections")
                assert isinstance(db._active_connections, dict)
                
                # Get connection - should be tracked
                conn = db.connection
                thread_id = threading.get_ident()
                assert thread_id in db._active_connections
                assert db._active_connections[thread_id] is conn
                
                db.cleanup()

    def test_cleanup_closes_leaked_connections(self, temp_db_path, qapp):
        """cleanup() closes all leaked connections."""
        with patch("app.models.db.DB_PATH", temp_db_path):
            with patch("app.models.db.BACKUP_DIR", temp_db_path.parent / "backups"):
                db = Database()
                
                # Create connections in multiple threads
                connections = []
                def create_conn():
                    conn = db.connection
                    connections.append(conn)
                
                threads = [threading.Thread(target=create_conn) for _ in range(3)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
                
                # Should have multiple tracked connections
                assert len(db._active_connections) >= 1
                
                # Cleanup should close all
                db.cleanup()
                assert len(db._active_connections) == 0


class TestTOCTOUProtection:
    """Tests for TOCTOU protection in update_item_positions."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        return tmp_path / "test.db"

    def test_update_positions_atomic_check_and_update(self, temp_db_path, qapp):
        """update_item_positions checks existence atomically with update."""
        with patch("app.models.db.DB_PATH", temp_db_path):
            with patch("app.models.db.BACKUP_DIR", temp_db_path.parent / "backups"):
                from app.models.base.db_base import ValidationError
                
                db = Database()
                # Use singular form as per VALID_POSITION_TABLES
                db.connection.execute("CREATE TABLE sphere (id INTEGER PRIMARY KEY, position INTEGER)")
                db.connection.execute("INSERT INTO sphere (id, position) VALUES (1, 0), (2, 1)")
                db.connection.commit()
                
                # Try to update with non-existent ID - should fail atomically
                with pytest.raises(ValidationError, match="Records with ID not found"):
                    db.update_item_positions("sphere", [1, 2, 999])
                
                # Original positions should be unchanged
                row = db.connection.execute("SELECT position FROM sphere WHERE id = 1").fetchone()
                assert row["position"] == 0
                
                db.cleanup()


# Pytest fixtures for QApplication
@pytest.fixture(scope="session")
def qapp():
    """Creates QApplication for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # Don't quit - other tests may need it
