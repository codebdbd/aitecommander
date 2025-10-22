import logging
import sqlite3
import threading
import time
import warnings
from pathlib import Path
from typing import Any, Callable, ContextManager, Optional, Protocol

from PyQt6.QtCore import QObject, QThread, QThreadPool, pyqtBoundSignal, pyqtSignal

from app.config_data import app_config
from app.utils.db.migrations import MigrationRunner

from .base.db_base import DatabaseBase, DatabaseError, ValidationError, db_lock
from .entities.category_model import CategoryModel
from .entities.link_model import LinkModel
from .entities.section_model import SectionModel
from .entities.sphere_model import SphereModel
from .managers.backup_manager import BackupManager
from .managers.duplicate_resolver import DuplicateResolver
from .managers.import_export_manager import ImportExportManager
from .managers.structure_manager import StructureManager
from .types.constants import (
    FORBIDDEN_IDENTIFIER_CHARS,
    MAX_IDENTIFIER_LENGTH,
    SLOW_OPERATION_THRESHOLD_MS,
    SQLITE_SAFE_BATCH_SIZE,
    SQLITE_SAFE_SELECT_CHUNK,
)

logger = logging.getLogger(__name__)


class FinishedCallback(Protocol):
    """Callback protocol for finished operations."""
    def __call__(self, result: Any) -> None: ...


class ErrorCallback(Protocol):
    """Callback protocol for error handling."""
    def __call__(self, exception: Exception, traceback: str) -> None: ...


class ProgressCallback(Protocol):
    """Callback protocol for progress updates."""
    def __call__(self, current: int, total: int, message: str) -> None: ...

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
PATHS = app_config.paths
DB_PATH = PATHS.get_db_path()
BACKUP_DIR = PATHS.get_backups_dir()


class Database(QObject):
    """Main class for working with database. Inherits from QObject to support Qt signals and reactive UI updates."""

    data_changed = pyqtSignal(str, str, list)
    structure_loaded = pyqtSignal()
    backup_created = pyqtSignal(str)
    error_occurred = pyqtSignal(str, str)
    operation_started = pyqtSignal(str, int)
    operation_progress = pyqtSignal(str, int, int, str)
    operation_finished = pyqtSignal(str, bool)
    warning_occurred = pyqtSignal(str, str)

    def __init__(self, parent: Optional[QObject] = None):
        """Initializes Database. Raises TypeError if parent is not QObject or None."""
        if parent is not None and not isinstance(parent, QObject):
            raise TypeError(f"parent must be QObject or None, got {type(parent).__name__}")
        
        super().__init__(parent)

        self.db_path = str(DB_PATH)
        self.thread_local = threading.local()
        self._active_connections = {}  # Track connections by thread ID for cleanup
        self._connection_lock = threading.Lock()  # Separate lock for connection management
        self._base = DatabaseBase(self)
        pool = QThreadPool.globalInstance()
        if pool is None:
            raise RuntimeError("QThreadPool.globalInstance() returned None")
        self._thread_pool: QThreadPool = pool
        max_threads = app_config.get("threading.max_db_threads", 4)
        self._thread_pool.setMaxThreadCount(max_threads)
        self.spheres = SphereModel(self)
        self.sections = SectionModel(self)
        self.categories = CategoryModel(self)
        self.links = LinkModel(self)
        self.backup_manager = BackupManager(self)
        self.import_export_manager = ImportExportManager(self)
        self.duplicate_resolver = DuplicateResolver(self)
        self.structure_manager = StructureManager(self)
        self._cleaned_up = False

    def commit(self) -> None:
        return self._base.commit()

    def rollback(self) -> None:
        return self._base.rollback()

    def transaction(self) -> ContextManager[None]:
        return self._base.transaction()

    def prepare_dirs(self) -> None:
        """Creates necessary user directories for data."""
        PATHS.ensure_user_data_dirs()

    def initialize_or_migrate(self) -> None:
        """Deprecated: Use initialize_or_migrate_async(). Raises RuntimeError if called from GUI thread."""
        self._ensure_not_gui_thread("initialize_or_migrate")
        
        warnings.warn(
            "Method initialize_or_migrate() is deprecated. Use initialize_or_migrate_async().",
            DeprecationWarning,
            stacklevel=2,
        )
        operation = "initialize_or_migrate"
        is_new = not DB_PATH.exists()
        
        try:
            self.operation_started.emit(operation, 1)
            
            with db_lock:
                self.operation_progress.emit(operation, 0, 1, "Applying migrations...")
                try:
                    conn = self.connection
                    runner = MigrationRunner(conn, MIGRATIONS_DIR)
                    applied = runner.run_all_pending()
                    logger.info("Migrations applied: %d", applied)
                except Exception as migration_err:
                    logger.error("Migration failed: %s", migration_err, exc_info=True)
                    self.operation_finished.emit(operation, False)
                    raise DatabaseError(f"Migration failed: {migration_err}") from migration_err
            
            if is_new:
                try:
                    self.operation_progress.emit(operation, 1, 1, "Initializing default data...")
                    with db_lock:
                        self.spheres.initialize_default_spheres()
                except Exception as init_err:
                    logger.error("Failed to initialize default data: %s", init_err, exc_info=True)
                    self.operation_finished.emit(operation, False)
                    raise DatabaseError(f"Failed to initialize default data: {init_err}") from init_err
            
            self.operation_finished.emit(operation, True)
            logger.info("Database initialization completed successfully")
        
        except DatabaseError:
            if is_new and DB_PATH.exists():
                try:
                    self.close()
                    DB_PATH.unlink()
                    logger.info("Removed incomplete database file after initialization failure")
                except Exception as cleanup_err:
                    logger.warning("Failed to remove incomplete database: %s", cleanup_err)
            raise
        
        except Exception as e:
            self.operation_finished.emit(operation, False)
            logger.error("Unexpected error during initialization: %s", e, exc_info=True)
            
            if is_new and DB_PATH.exists():
                try:
                    self.close()
                    DB_PATH.unlink()
                    logger.info("Removed incomplete database file after unexpected error")
                except Exception as cleanup_err:
                    logger.warning("Failed to remove incomplete database: %s", cleanup_err)
            
            raise DatabaseError(f"Database initialization failed: {e}") from e
        
        finally:
            try:
                self.close()
            except Exception as close_err:
                logger.warning("Error closing connection during cleanup: %s", close_err)

    def initialize_or_migrate_async(
        self,
        on_finished: Optional[FinishedCallback] = None,
        on_error: Optional[ErrorCallback] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> None:
        """Initializes DB in background thread. Callbacks: on_finished(stats), on_error(e, tb), on_progress(c, t, m)."""
        try:
            from .workers import InitializationWorker

            worker = InitializationWorker(self.db_path, MIGRATIONS_DIR)
            
            def on_worker_finished(stats):
                self._safe_emit(self.operation_finished, "initialize_or_migrate", True)
                logger.info("Async DB initialization completed: %s", stats)
            
            def on_worker_error(e, tb):
                self._safe_emit(self.error_occurred, "Initialization error", str(e))
                self._safe_emit(self.operation_finished, "initialize_or_migrate", False)
                logger.error("Async DB initialization failed: %s\n%s", e, tb)
            
            worker.signals.finished.connect(on_worker_finished)
            worker.signals.error.connect(on_worker_error)
            
            if on_finished:
                worker.signals.finished.connect(lambda result: self._safe_callback(on_finished, result))
            if on_error:
                worker.signals.error.connect(lambda e, tb: self._safe_callback(on_error, e, tb))
            if on_progress:
                worker.signals.progress.connect(lambda c, t, m: self._safe_callback(on_progress, c, t, m))

            self._safe_emit(self.operation_started, "initialize_or_migrate", 1)
            self._thread_pool.start(worker)
            logger.info("Started async DB initialization")
        except Exception as e:
            logger.error("Failed to start async DB initialization: %s", e, exc_info=True)
            self._safe_emit(self.error_occurred, "Initialization error", str(e))
            self._safe_emit(self.operation_finished, "initialize_or_migrate", False)
            if on_error:
                self._safe_callback(on_error, e, "")

    def _safe_emit(self, signal: pyqtBoundSignal, *args: Any) -> None:
        """Emit Qt signal only when QApplication exists. Prevents crashes in tests/CLI."""
        try:
            from PyQt6.QtWidgets import QApplication

            if QApplication.instance() is None:
                logger.debug("Skipping signal emit (no QApplication): %s", signal.__class__.__name__)
                return
            
            signal.emit(*args)

        except Exception as e:
            logger.warning("Error emitting signal %s: %s", signal.__class__.__name__, e, exc_info=True)
    
    def _safe_callback(self, callback: Callable, *args: Any) -> None:
        """Safely invoke user callback with error handling."""
        try:
            callback(*args)
        except Exception as e:
            logger.error("Error in user callback %s: %s", getattr(callback, '__name__', repr(callback)), e, exc_info=True)
            self._safe_emit(self.error_occurred, "Callback error", str(e))
    
    def _ensure_not_gui_thread(self, method_name: str) -> None:
        """Ensures method is not called from GUI thread. Raises RuntimeError if violated."""
        try:
            from PyQt6.QtWidgets import QApplication
            
            app = QApplication.instance()
            if app is not None and QThread.currentThread() == app.thread():
                raise RuntimeError(f"{method_name}() is a blocking operation and must not be called from GUI thread. Use {method_name}_async() instead.")
        except ImportError:
            pass

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            self.close()
        except Exception as e:
            logger.warning("Error in __exit__ during close: %s", e)
            if exc_type is None:
                raise

    @property
    def connection(self) -> sqlite3.Connection:
        """Returns thread-local DB connection. WARNING: All write operations MUST use db_lock for synchronization."""
        with self._connection_lock:
            conn = getattr(self.thread_local, "conn", None)
            if conn is not None:
                try:
                    conn.execute("SELECT 1").fetchone()
                    return conn
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    try:
                        del self.thread_local.conn
                    except Exception:
                        pass
                    thread_id = threading.get_ident()
                    if thread_id in self._active_connections:
                        del self._active_connections[thread_id]
            
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
            self.thread_local.conn = conn
            thread_id = threading.get_ident()
            self._active_connections[thread_id] = conn
            return conn

    def get_section_id_by_category(self, category_id: int) -> Optional[int]:
        """Returns section_id for given category."""
        row = self.categories.get_category_by_id(category_id)
        return row["section_id"] if row else None

    def get_sphere_id_by_section(self, section_id: int) -> Optional[int]:
        """Returns sphere_id for given section."""
        return self.sections.get_sphere_id_by_section(section_id)

    def update_item_positions(self, table_name: str, ids_in_order: list[int]) -> None:
        """Updates 'position' field for list of items in specified table."""
        from .types.constants import VALID_POSITION_TABLES

        if table_name not in VALID_POSITION_TABLES:
            raise ValidationError(
                f"Invalid table name for position update: {table_name}"
            )
        
        safe_table_name = self._escape_identifier(table_name)

        try:
            ids = self._validate_ids(ids_in_order)
            if not ids:
                logger.debug("update_item_positions: empty ID list for table %s", table_name)
                return
            
            with db_lock:
                _t0 = time.perf_counter()
                
                self._check_ids_exist(table_name, ids)
                
                # UPDATE батчами (проверка уже выполнена)
                id_pos_pairs = [(item_id, i) for i, item_id in enumerate(ids)]
                with self.connection:
                    batches = 0
                    for start in range(0, len(id_pos_pairs), SQLITE_SAFE_BATCH_SIZE):
                        chunk = id_pos_pairs[start : start + SQLITE_SAFE_BATCH_SIZE]
                        values_sql = ",".join(["(?,?)"] * len(chunk))
                        params = []
                        for _id, pos in chunk:
                            params.extend([_id, pos])
                        
                        sql = f"""
                            WITH newpos(id, position) AS (
                                VALUES {values_sql}
                            )
                            UPDATE {safe_table_name}
                            SET position = (
                                SELECT newpos.position FROM newpos WHERE newpos.id = {safe_table_name}.id
                            )
                            WHERE id IN (SELECT id FROM newpos)
                            """
                        self.connection.execute(sql, tuple(params))
                        batches += 1
                _t1 = time.perf_counter()
                duration_ms = (_t1 - _t0) * 1000.0
                if duration_ms > SLOW_OPERATION_THRESHOLD_MS:
                    logger.info("update_item_positions: table=%s, count=%d, batches=%d, duration_ms=%.2f", table_name, len(ids), batches, duration_ms)
                else:
                    logger.debug("update_item_positions: table=%s, count=%d, batches=%d, duration_ms=%.2f", table_name, len(ids), batches, duration_ms)
            
            logger.debug("Updated positions (%s items) in table %s", len(ids), table_name)
            self._safe_emit(self.data_changed, table_name, "update_positions", ids)
        except ValidationError:
            raise
        except Exception as e:
            logger.error("Error updating positions in table %s: %s", table_name, e, exc_info=True)
            raise DatabaseError(f"Failed to update positions: {e}") from e

    def _validate_ids(self, ids_in_order: list[int]) -> list[int]:
        """Checks and normalizes input IDs. Throws ValidationError on mismatches."""
        ids = list(ids_in_order or [])
        if not ids:
            return []

        for v in ids:
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ValidationError(f"Incorrect ID in position list: {v}")

        if len(set(ids)) != len(ids):
            raise ValidationError("ID list contains duplicates")

        return ids
    
    def _check_ids_exist(self, table_name: str, ids: list[int]) -> None:
        """Checks that all IDs exist in table. Raises ValidationError if any missing."""
        if not ids:
            return
        
        safe_table_name = self._escape_identifier(table_name)
        
        if len(ids) > SQLITE_SAFE_SELECT_CHUNK:
            with self.connection:
                self.connection.execute(
                    "CREATE TEMP TABLE IF NOT EXISTS _check_ids (id INTEGER PRIMARY KEY)"
                )
                try:
                    self.connection.executemany(
                        "INSERT OR IGNORE INTO _check_ids VALUES (?)",
                        [(id_val,) for id_val in ids]
                    )
                    
                    missing = self.connection.execute(f"""
                        SELECT id FROM _check_ids
                        WHERE id NOT IN (SELECT id FROM {safe_table_name})
                    """).fetchall()
                    
                    if missing:
                        missing_ids = [row["id"] for row in missing]
                        raise ValidationError(f"Records with ID not found: {missing_ids} in table {table_name}")
                finally:
                    self.connection.execute("DELETE FROM _check_ids")
        else:
            existing_ids = set()
            for s in range(0, len(ids), SQLITE_SAFE_SELECT_CHUNK):
                part = ids[s : s + SQLITE_SAFE_SELECT_CHUNK]
                placeholders = ",".join(["?"] * len(part))
                rows = self.connection.execute(
                    f"SELECT id FROM {safe_table_name} WHERE id IN ({placeholders})",
                    tuple(part)
                ).fetchall()
                existing_ids.update(row["id"] for row in rows)
            
            if len(existing_ids) != len(ids):
                missing_ids = [_id for _id in ids if _id not in existing_ids]
                raise ValidationError(f"Records with ID not found: {missing_ids} in table {table_name}")
    
    def _escape_identifier(self, identifier: str) -> str:
        """Escapes SQL identifier to prevent injection. Returns quoted identifier."""
        if not identifier:
            raise ValidationError("Identifier cannot be empty")
        
        if len(identifier) > MAX_IDENTIFIER_LENGTH:
            raise ValidationError(f"Identifier too long: {len(identifier)} > {MAX_IDENTIFIER_LENGTH}")
        
        if FORBIDDEN_IDENTIFIER_CHARS & set(identifier):
            forbidden_found = FORBIDDEN_IDENTIFIER_CHARS & set(identifier)
            raise ValidationError(f"Invalid characters in identifier: {forbidden_found}")
        
        first_char = identifier[0]
        if not (first_char.isalpha() or first_char == '_'):
            raise ValidationError(f"Identifier must start with letter or underscore: {identifier}")
        
        return f'"{identifier}"'


    def export_full_structure(self) -> dict[str, list]:
        """Deprecated: Use export_full_structure_async(). Raises RuntimeError if called from GUI thread."""
        self._ensure_not_gui_thread("export_full_structure")
        
        warnings.warn(
            "Method export_full_structure() is deprecated. Use export_full_structure_async().",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.import_export_manager.export_full_structure()

    def export_full_structure_async(
        self,
        on_finished: Optional[FinishedCallback] = None,
        on_error: Optional[ErrorCallback] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> None:
        """Exports structure in background thread. Callbacks: on_finished(result), on_error(e, tb), on_progress(c, t, m)."""
        try:
            from .workers import ExportStructureWorker

            worker = ExportStructureWorker(self.db_path)
            
            if on_finished:
                worker.signals.finished.connect(lambda result: self._safe_callback(on_finished, result))
            if on_error:
                worker.signals.error.connect(lambda e, tb: self._safe_callback(on_error, e, tb))
            if on_progress:
                worker.signals.progress.connect(lambda c, t, m: self._safe_callback(on_progress, c, t, m))

            self._thread_pool.start(worker)
            logger.info("Started async structure export")
        except Exception as e:
            logger.error("Failed to start async structure export: %s", e, exc_info=True)
            self._safe_emit(self.error_occurred, "Export error", str(e))
            if on_error:
                self._safe_callback(on_error, e, "")

    def get_full_structure(self) -> list[dict[str, Any]]:
        return self.structure_manager.get_full_structure()

    def import_full_structure(self, data: list[dict[str, Any]]) -> dict[str, int]:
        """Deprecated: Use import_full_structure_async(). Raises RuntimeError if called from GUI thread."""
        self._ensure_not_gui_thread("import_full_structure")
        
        warnings.warn(
            "Method import_full_structure() is deprecated. Use import_full_structure_async().",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.structure_manager.import_full_structure(data)

    def import_full_structure_async(
        self,
        data: list[dict[str, Any]],
        on_finished: Optional[FinishedCallback] = None,
        on_error: Optional[ErrorCallback] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> None:
        """Imports data in background thread. Callbacks: on_finished(stats), on_error(e, tb), on_progress(c, t, m)."""
        if not data:
            logger.warning("import_full_structure_async called with empty data")
            if on_finished:
                self._safe_callback(on_finished, {"imported": 0})
            return
        
        if not isinstance(data, list):
            error_msg = f"Data must be a list, got {type(data).__name__}"
            logger.error(error_msg)
            self._safe_emit(self.error_occurred, "Import error", error_msg)
            if on_error:
                self._safe_callback(on_error, TypeError(error_msg), "")
            return
        
        try:
            from .workers import ImportStructureWorker

            worker = ImportStructureWorker(self.db_path, data)
            worker.signals.finished.connect(lambda stats: self.structure_loaded.emit())
            worker.signals.error.connect(lambda e, tb: self.error_occurred.emit("Import error", str(e)))
            
            if on_finished:
                worker.signals.finished.connect(lambda result: self._safe_callback(on_finished, result))
            if on_error:
                worker.signals.error.connect(lambda e, tb: self._safe_callback(on_error, e, tb))
            if on_progress:
                worker.signals.progress.connect(lambda c, t, m: self._safe_callback(on_progress, c, t, m))

            self._thread_pool.start(worker)
            logger.info("Started async structure import")
        except Exception as e:
            logger.error("Failed to start async structure import: %s", e, exc_info=True)
            self._safe_emit(self.error_occurred, "Import error", str(e))
            if on_error:
                self._safe_callback(on_error, e, "")

    def backup(self) -> str:
        return self.backup_manager.backup(BACKUP_DIR)

    def backup_async(
        self,
        on_finished: Optional[FinishedCallback] = None,
        on_error: Optional[ErrorCallback] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> None:
        """Creates backup in background thread. Callbacks: on_finished(result), on_error(e, tb), on_progress(c, t, m)."""
        from .workers import BackupWorker

        worker = BackupWorker(self.db_path, BACKUP_DIR)
        
        if on_finished:
            worker.signals.finished.connect(lambda result: self._safe_callback(on_finished, result))
        if on_error:
            worker.signals.error.connect(lambda e, tb: self._safe_callback(on_error, e, tb))
        if on_progress:
            worker.signals.progress.connect(lambda c, t, m: self._safe_callback(on_progress, c, t, m))
        self._thread_pool.start(worker)
        logger.info("Started async backup")

    def export_section_tree(self, section_id: int) -> dict[str, Any]:
        return self.import_export_manager.export_section_tree(section_id)

    def import_section_tree(self, tree: dict[str, Any]) -> int:
        return self.import_export_manager.import_section_tree(tree)

    def export_category_tree(self, category_id: int) -> dict[str, Any]:
        return self.import_export_manager.export_category_tree(category_id)

    def import_category_tree(self, tree: dict[str, Any]) -> int:
        return self.import_export_manager.import_category_tree(tree)

    def import_category_trees_bulk(self, trees: list[dict[str, Any]]) -> None:
        return self.import_export_manager.import_category_trees_bulk(trees)

    def is_connected(self) -> bool:
        try:
            conn = getattr(self.thread_local, "conn", None)
            if conn is not None:
                conn.execute("SELECT 1").fetchone()
                return True
            return False
        except Exception:
            return False

    def close(self) -> None:
        try:
            thread_id = threading.get_ident()
            if hasattr(self.thread_local, "conn"):
                try:
                    with db_lock:
                        self.thread_local.conn.execute("PRAGMA wal_checkpoint(FULL)")
                        self.thread_local.conn.commit()
                    logger.debug("WAL checkpoint completed before closing")
                except Exception as checkpoint_err:
                    logger.warning("Error WAL checkpoint when closing: %s", checkpoint_err, exc_info=True)
                self.thread_local.conn.close()
                del self.thread_local.conn
                with self._connection_lock:
                    if thread_id in self._active_connections:
                        del self._active_connections[thread_id]
                logger.debug("Database connection closed")
        except Exception as e:
            logger.error("Error closing connection: %s", e, exc_info=True)

    def detect_case_insensitive_duplicates(self) -> dict[str, list[dict[str, Any]]]:
        return self.duplicate_resolver.detect_case_insensitive_duplicates()

    def resolve_case_insensitive_duplicates(self, strategy: str = "rename") -> dict[str, int]:
        return self.duplicate_resolver.resolve_case_insensitive_duplicates(strategy)

    def create_nocase_unique_indexes(self) -> None:
        return self.duplicate_resolver.create_nocase_unique_indexes()

    def cleanup(self) -> None:
        """Releases Database resources. Waits for workers, closes connections, releases models. Idempotent."""
        if self._cleaned_up:
            return

        try:
            logger.debug("Database cleanup started")
            if hasattr(self, "_thread_pool") and self._thread_pool:
                try:
                    logger.debug("Waiting for thread pool to finish...")
                    timeout_ms = app_config.get("threading.cleanup_timeout_ms", 5000)
                    if not self._thread_pool.waitForDone(timeout_ms):
                        logger.warning("Thread pool did not finish within %dms timeout, some workers may still be running. Active threads: %d", timeout_ms, self._thread_pool.activeThreadCount())
                except Exception as e:
                    logger.warning("Error waiting for thread pool: %s", e)
            try:
                self.close()
            except Exception as e:
                logger.warning("Error closing database connection: %s", e)
            
            with self._connection_lock:
                for thread_id, conn in list(self._active_connections.items()):
                    try:
                        conn.close()
                        logger.debug("Closed leaked connection from thread %s", thread_id)
                    except Exception as e:
                        logger.warning("Error closing leaked connection: %s", e)
                self._active_connections.clear()
            for attr in [
                "spheres",
                "sections",
                "categories",
                "links",
                "backup_manager",
                "import_export_manager",
                "duplicate_resolver",
                "structure_manager",
            ]:
                if hasattr(self, attr):
                    try:
                        delattr(self, attr)
                    except Exception:
                        pass

            self._cleaned_up = True
            logger.debug("Database cleanup completed")

        except Exception as exc:
            logger.error("Error during Database cleanup: %s", exc, exc_info=True)
