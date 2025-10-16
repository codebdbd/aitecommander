import logging
import sqlite3
import threading
import time
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt6.QtCore import QObject

from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal

from app.config_data import app_config
from app.utils.db.migrations import MigrationRunner
from .managers.backup_manager import BackupManager
from .managers.import_export_manager import ImportExportManager
from .managers.duplicate_resolver import DuplicateResolver
from .managers.structure_manager import StructureManager
from .types.constants import (
    SQLITE_SAFE_BATCH_SIZE,
    SQLITE_SAFE_SELECT_CHUNK,
)
from .base.db_base import DatabaseBase, DatabaseError, ValidationError, db_lock
from .entities.sphere_model import SphereModel
from .entities.section_model import SectionModel
from .entities.category_model import CategoryModel
from .entities.link_model import LinkModel

logger = logging.getLogger(__name__)

# File paths
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Database paths from centralized configuration
PATHS = app_config.paths
DB_PATH = PATHS.get_db_path()
BACKUP_DIR = PATHS.get_backups_dir()


class Database(QObject):
    """Main class for working with database.
    
    Inherits from QObject to support Qt signals and reactive UI updates.
    Uses composition to access basic DB operations.
    """
    
    # Qt signals to notify UI about data changes
    data_changed = pyqtSignal(str, str, list)  # table_name, operation, affected_ids
    structure_loaded = pyqtSignal()  # Structure loaded/imported
    backup_created = pyqtSignal(str)  # backup_path
    error_occurred = pyqtSignal(str, str)  # title, message
    
    # Progress signals for long operations
    operation_started = pyqtSignal(str, int)  # operation_name, total_items
    operation_progress = pyqtSignal(str, int, int, str)  # operation_name, current, total, message
    operation_finished = pyqtSignal(str, bool)  # operation_name, success
    warning_occurred = pyqtSignal(str, str)  # title, message
    
    def __init__(self, parent: Optional[QObject] = None):
        """Initializes Database.
        
        ✅ FIX: Added parent parameter for proper memory management.
        
        Args:
            parent: Parent QObject (optional)
        """
        # Initialize QObject with parent
        super().__init__(parent)
        
        self.db_path = str(DB_PATH)
        self.thread_local = threading.local()
        
        # Composition instead of inheritance from DatabaseBase
        self._base = DatabaseBase(self)
        
        # Thread pool for async operations
        self._thread_pool = QThreadPool.globalInstance()
        max_threads = app_config.get("threading.max_db_threads", 4)
        self._thread_pool.setMaxThreadCount(max_threads)

        # Initialize models after full Database initialization
        # ✅ FIX: Models are not QObject, parent not needed
        self.spheres = SphereModel(self)
        self.sections = SectionModel(self)
        self.categories = CategoryModel(self)
        self.links = LinkModel(self)
        
        # Initialize managers
        self.backup_manager = BackupManager(self)
        self.import_export_manager = ImportExportManager(self)
        self.duplicate_resolver = DuplicateResolver(self)
        self.structure_manager = StructureManager(self)
        
        # ✅ Flag to track cleanup
        self._cleaned_up = False
    
    # Delegate DatabaseBase methods through composition
    def commit(self) -> None:
        """Commits current transaction."""
        return self._base.commit()
    
    def rollback(self) -> None:
        """Rolls back current transaction."""
        return self._base.rollback()
    
    def transaction(self):
        """Transaction context manager with automatic commit/rollback."""
        return self._base.transaction()

    def prepare_dirs(self) -> None:
        """Creates necessary user directories for data.

        Call in background before first DB work to avoid blocking UI.
        """
        PATHS.ensure_user_data_dirs()

    def initialize_or_migrate(self) -> None:
        """Initializes new DB or performs migrations for existing one.

        .. deprecated::
            Use :meth:`initialize_or_migrate_async` to prevent UI blocking.
        
        Heavy operation: run in background (QRunnable) using global
        `db_lock` inside methods where needed.
        """
        warnings.warn(
            "Method initialize_or_migrate() is deprecated. Use initialize_or_migrate_async().",
            DeprecationWarning,
            stacklevel=2
        )
        operation = "initialize_or_migrate"
        try:
            self.operation_started.emit(operation, 1)
            is_new = not DB_PATH.exists()
            # Run migrations through MigrationRunner (will create schema via 0001_init)
            with db_lock:
                self.operation_progress.emit(operation, 0, 1, "Applying migrations...")
                runner = MigrationRunner(self.connection, MIGRATIONS_DIR)
                applied = runner.run_all_pending()
                logger.info("Migrations applied: %d", applied)

            # Initialize default data for new database (after migrations)
            if is_new:
                try:
                    self.operation_progress.emit(operation, 1, 1, "Initializing default data...")
                    self.spheres.initialize_default_spheres()
                except Exception as init_err:
                    logger.warning(
                        "Failed to initialize default spheres: %s",
                        init_err,
                        exc_info=True,
                    )
            self.operation_finished.emit(operation, True)
        except Exception as e:
            self.operation_finished.emit(operation, False)
            raise
        finally:
            # Close current thread connection (e.g. worker),
            # to avoid keeping connection open from background thread.
            try:
                self.close()
            except Exception:
                pass
    
    def initialize_or_migrate_async(
        self,
        on_finished: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_progress: Optional[Callable] = None
    ):
        """Initializes DB in background thread (RECOMMENDED).
        
        ✅ FIX: Added async method to prevent UI blocking.
        
        Args:
            on_finished: Callback on completion (stats: {is_new: bool, migrations_applied: int})
            on_error: Callback on error (exception, traceback)
            on_progress: Callback for progress (current, total, message)
            
        Example:
            >>> def on_done(stats):
            ...     print(f"Migrations applied: {stats['migrations_applied']}")
            >>> db.initialize_or_migrate_async(on_finished=on_done)
        """
        from .workers import InitializationWorker
        
        worker = InitializationWorker(self.db_path, MIGRATIONS_DIR)
        
        # Подключаем внутренние сигналы Database
        worker.signals.finished.connect(
            lambda stats: self._safe_emit(self.operation_finished, "initialize_or_migrate", True)
        )
        worker.signals.error.connect(
            lambda e, tb: self._safe_emit(self.error_occurred, "Initialization error", str(e))
        )
        
        # Подключаем пользовательские callbacks
        if on_finished:
            worker.signals.finished.connect(on_finished)
        if on_error:
            worker.signals.error.connect(on_error)
        if on_progress:
            worker.signals.progress.connect(on_progress)
        
        self._thread_pool.start(worker)
        logger.info("Started async DB initialization")
    
    def _safe_emit(self, signal: pyqtSignal, *args) -> None:
        """Safe signal emit with QApplication check.
        
        ✅ FIX: Added QApplication.instance() check before emit.
        
        Prevents crash when used outside Qt application (tests, CLI).
        
        Args:
            signal: Signal to emit
            *args: Signal arguments
        """
        try:
            from PyQt6.QtWidgets import QApplication
            
            # Check for QApplication instance
            if QApplication.instance() is None:
                logger.debug(
                    "Skipping signal emit (no QApplication): %s",
                    signal.__class__.__name__
                )
                return
            
            # Emit signal
            signal.emit(*args)
            
        except Exception as e:
            # Don't interrupt main operation on signal error
            logger.debug(
                "Error emitting signal %s: %s",
                signal.__class__.__name__,
                e,
                exc_info=True
            )

    def __enter__(self):
        """Allows using Database as context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @property
    def connection(self):
        """Returns thread-safe DB connection. IMPORTANT: use object from single thread only!
        For PyQt6 it's recommended to work with DB only in main thread or through separate worker with data transfer via signals/slots."""
        conn = getattr(self.thread_local, "conn", None)
        if conn is not None:
            # Light connection self-diagnostic: if closed/incorrect — reopen.
            try:
                conn.execute("SELECT 1").fetchone()
                return conn
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                # Unbind broken descriptor and create new one below
                try:
                    del self.thread_local.conn
                except Exception:
                    pass

        # Create new connection (lazily), without test query
        self.thread_local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.thread_local.conn.row_factory = sqlite3.Row
        self.thread_local.conn.execute("PRAGMA foreign_keys = ON")
        self.thread_local.conn.execute("PRAGMA journal_mode=WAL")
        return self.thread_local.conn

    # Helper methods

    def get_section_id_by_category(self, category_id: int) -> Optional[int]:
        """Returns section_id for given category."""
        row = self.categories.get_category_by_id(category_id)
        return row["section_id"] if row else None

    def get_sphere_id_by_section(self, section_id: int) -> Optional[int]:
        """Returns sphere_id for given section."""
        return self.sections.get_sphere_id_by_section(section_id)

    def update_item_positions(self, table_name: str, ids_in_order: List[int]):
        """Updates 'position' field for list of items in specified table."""
        from .types.constants import VALID_POSITION_TABLES
        
        if table_name not in VALID_POSITION_TABLES:
            raise ValidationError(
                f"Invalid table name for position update: {table_name}"
            )

        # Validation and existence check
        try:
            ids = self._validate_ids(ids_in_order)
            if not ids:
                logger.debug(
                    "update_item_positions: empty ID list for table %s",
                    table_name,
                )
                return

            self._ensure_ids_exist(table_name, ids)

            # Existence check and update performed under SINGLE db_lock
            with db_lock:
                _t0 = time.perf_counter()
                # --- Batch position update ---
                # Form (id, position) pairs according to order in ids
                id_pos_pairs = [(item_id, i) for i, item_id in enumerate(ids)]
                # SQLite parameter count limit by default ~999 — 2 parameters per record
                with self.connection:
                    batches = 0
                    for start in range(0, len(id_pos_pairs), SQLITE_SAFE_BATCH_SIZE):
                        chunk = id_pos_pairs[start : start + SQLITE_SAFE_BATCH_SIZE]
                        # Prepare VALUES placeholders and parameters (id, position)
                        values_sql = ",".join(["(?,?)"] * len(chunk))
                        params = []
                        for _id, pos in chunk:
                            params.extend([_id, pos])

                        sql = f"""
                            WITH newpos(id, position) AS (
                                VALUES {values_sql}
                            )
                            UPDATE {table_name}
                            SET position = (
                                SELECT newpos.position FROM newpos WHERE newpos.id = {table_name}.id
                            )
                            WHERE id IN (SELECT id FROM newpos)
                            """
                        self.connection.execute(sql, tuple(params))
                        batches += 1
                _t1 = time.perf_counter()
                logger.debug(
                    "update_item_positions: table=%s, count=%d, batches=%d, chunk=%d, duration_ms=%.2f",
                    table_name,
                    len(ids),
                    batches,
                    SQLITE_SAFE_BATCH_SIZE,
                    ((_t1 - _t0) * 1000.0),
                )
            logger.debug(
                "Updated positions (%s items) in table %s",
                len(ids),
                table_name,
            )
            
            # Notify UI about data change via Qt signal
            # ✅ FIX: Use _safe_emit
            self._safe_emit(self.data_changed, table_name, "update_positions", ids)
        except ValidationError:
            # Pass input data validation errors as is
            raise
        except Exception as e:
            logger.error(
                "Error updating positions in table %s: %s",
                table_name,
                e,
                exc_info=True,
            )
            raise DatabaseError(f"Failed to update positions: {e}")

    # === Helpers for update_item_positions ===
    def _validate_ids(self, ids_in_order: List[int]) -> List[int]:
        """Checks and normalizes input IDs: types, values, uniqueness.

        Returns list of int IDs. Throws ValidationError on mismatches.
        """
        ids = list(ids_in_order or [])
        if not ids:
            return []

        for v in ids:
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ValidationError(f"Incorrect ID in position list: {v}")

        if len(set(ids)) != len(ids):
            raise ValidationError("ID list contains duplicates")

        return ids

    def _ensure_ids_exist(self, table_name: str, ids: List[int]) -> None:
        """Checks existence of all specified IDs in table. Throws ValidationError if missing."""
        with db_lock:
            existing_ids = set()
            for s in range(0, len(ids), SQLITE_SAFE_SELECT_CHUNK):
                part = ids[s : s + SQLITE_SAFE_SELECT_CHUNK]
                placeholders = ",".join(["?"] * len(part))
                rows = self.connection.execute(
                    f"SELECT id FROM {table_name} WHERE id IN ({placeholders})",
                    tuple(part),
                ).fetchall()
                for row in rows:
                    try:
                        existing_ids.add(int(dict(row)["id"]))
                    except (KeyError, TypeError, ValueError) as e:
                        logger.warning("Error converting ID: %s", e)
                        continue
        missing = [i for i in ids if i not in existing_ids]
        if missing:
            raise ValidationError(
                f"Records with ID not found: {missing} in table {table_name}"
            )

    # Import/export methods
    def export_full_structure(self) -> Dict[str, List]:
        """Exports entire data structure from DB as dictionary (synchronously).
        
        .. deprecated::
            Use :meth:`export_full_structure_async` to prevent UI blocking.
        """
        warnings.warn(
            "Method export_full_structure() is deprecated. Use export_full_structure_async().",
            DeprecationWarning,
            stacklevel=2
        )
        return self.import_export_manager.export_full_structure()
    
    def export_full_structure_async(
        self,
        on_finished: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_progress: Optional[Callable] = None
    ):
        """Exports structure in background thread.
        
        Args:
            on_finished: Callback on completion (result: Dict[str, List])
            on_error: Callback on error (exception, traceback)
            on_progress: Callback for progress (current, total, message)
        """
        from .workers import ExportStructureWorker
        
        worker = ExportStructureWorker(self.db_path)
        
        if on_finished:
            worker.signals.finished.connect(on_finished)
        if on_error:
            worker.signals.error.connect(on_error)
        if on_progress:
            worker.signals.progress.connect(on_progress)
        
        self._thread_pool.start(worker)
        logger.info("Started async structure export")

    def get_full_structure(self) -> List[Dict]:
        """Returns full data structure as nested dictionaries."""
        return self.structure_manager.get_full_structure()

    def import_full_structure(self, data: List[Dict]):
        """Clears database and imports data from structure (synchronously).
        
        .. deprecated::
            Use :meth:`import_full_structure_async` to prevent UI blocking.
        """
        warnings.warn(
            "Method import_full_structure() is deprecated. Use import_full_structure_async().",
            DeprecationWarning,
            stacklevel=2
        )
        return self.structure_manager.import_full_structure(data)
    
    def import_full_structure_async(
        self,
        data: List[Dict],
        on_finished: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_progress: Optional[Callable] = None
    ):
        """Imports data in background thread (RECOMMENDED).
        
        Args:
            data: Data to import
            on_finished: Callback on completion (stats: {spheres, sections, categories, links})
            on_error: Callback on error (exception, traceback)
            on_progress: Callback for progress (current, total, message)
            
        Example:
            >>> def on_done(stats):
            ...     print(f"Imported {stats['spheres']} spheres")
            >>> db.import_full_structure_async(data, on_finished=on_done)
        """
        from .workers import ImportStructureWorker
        
        worker = ImportStructureWorker(self.db_path, data)
        
        # Подключаем внутренние сигналы Database
        worker.signals.finished.connect(lambda stats: self.structure_loaded.emit())
        worker.signals.error.connect(lambda e, tb: self.error_occurred.emit("Import error", str(e)))
        
        # Подключаем пользовательские callbacks
        if on_finished:
            worker.signals.finished.connect(on_finished)
        if on_error:
            worker.signals.error.connect(on_error)
        if on_progress:
            worker.signals.progress.connect(on_progress)
        
        self._thread_pool.start(worker)
        logger.info("Started async structure import")

    def backup(self):
        """Creates database backup (synchronously)."""
        return self.backup_manager.backup(BACKUP_DIR)
    
    def backup_async(
        self,
        on_finished: Optional[Callable] = None,
        on_progress: Optional[Callable] = None
    ):
        """Создаёт резервную копию в фоновом потоке.
        
        Args:
            on_finished: Callback при успешном завершении (result)
            on_error: Callback при ошибке (exception, traceback)
            on_progress: Callback для прогресса (current, total, message)
        """
        from .workers import BackupWorker
        
        worker = BackupWorker(self.db_path, BACKUP_DIR)
        
        if on_finished:
            worker.signals.finished.connect(on_finished)
        if on_error:
            worker.signals.error.connect(on_error)
        if on_progress:
            worker.signals.progress.connect(on_progress)
        
        # Start in thread pool
        self._thread_pool.start(worker)
        logger.info("Started async backup")

    def export_section_tree(self, section_id: int) -> dict:
        """Exports section along with all categories and links."""
        return self.import_export_manager.export_section_tree(section_id)

    def import_section_tree(self, tree: dict):
        """Restores section, its categories and all links from backup structure."""
        return self.import_export_manager.import_section_tree(tree)

    def export_category_tree(self, category_id: int) -> dict:
        """Exports category along with all links."""
        return self.import_export_manager.export_category_tree(category_id)

    def import_category_tree(self, tree: dict):
        """Restores category and all links from backup structure."""
        return self.import_export_manager.import_category_tree(tree)

    def import_category_trees_bulk(self, trees: List[dict]) -> None:
        """Imports multiple category subtrees in ONE transaction."""
        return self.import_export_manager.import_category_trees_bulk(trees)

    def is_connected(self) -> bool:
        """Checks if database connection is established."""
        try:
            conn = getattr(self.thread_local, "conn", None)
            if conn is not None:
                conn.execute("SELECT 1").fetchone()
                return True
            return False
        except Exception:
            return False

    def close(self):
        """Closes database connection."""
        try:
            if hasattr(self.thread_local, "conn"):
                try:
                    with db_lock:
                        self.thread_local.conn.execute("PRAGMA wal_checkpoint(FULL)")
                        self.thread_local.conn.commit()
                    logger.debug("WAL checkpoint completed before closing")
                except Exception as checkpoint_err:
                    logger.warning(
                        "Error WAL checkpoint when closing: %s",
                        checkpoint_err,
                        exc_info=True,
                    )
                self.thread_local.conn.close()
                del self.thread_local.conn
                logger.debug("Database connection closed")
        except Exception as e:
            logger.error("Error closing connection: %s", e, exc_info=True)

    def detect_case_insensitive_duplicates(self) -> dict:
        """Searches for case-insensitive name duplicates."""
        return self.duplicate_resolver.detect_case_insensitive_duplicates()

    def resolve_case_insensitive_duplicates(self, strategy: str = "rename") -> dict:
        """Resolves case-insensitive duplicates."""
        return self.duplicate_resolver.resolve_case_insensitive_duplicates(strategy)

    def create_nocase_unique_indexes(self) -> None:
        """Re-creates case-insensitive unique indexes for sphere/section/category."""
        return self.duplicate_resolver.create_nocase_unique_indexes()
    
    def cleanup(self) -> None:
        """Releases Database resources.
        
        ✅ FIX: Added cleanup method to prevent memory leaks.
        
        Called when closing application for proper completion:
        - Waits for all workers in thread pool to finish
        - Closes DB connections
        - Releases model and manager resources
        
        Idempotent - can be called multiple times.
        """
        if self._cleaned_up:
            return
        
        try:
            logger.debug("Database cleanup started")
            
            # 1. Wait for all workers to finish (max 5 seconds)
            if hasattr(self, '_thread_pool') and self._thread_pool:
                try:
                    logger.debug("Waiting for thread pool to finish...")
                    # waitForDone returns True if all finished, False if timeout
                    if not self._thread_pool.waitForDone(5000):
                        logger.warning(
                            "Thread pool did not finish within timeout, "
                            "some workers may still be running"
                        )
                except Exception as e:
                    logger.warning("Error waiting for thread pool: %s", e)
            
            # 2. Close DB connection
            try:
                self.close()
            except Exception as e:
                logger.warning("Error closing database connection: %s", e)
            
            # 3. Clear references to models and managers
            # (Python GC will free memory, but explicitly clear for clarity)
            for attr in ['spheres', 'sections', 'categories', 'links',
                        'backup_manager', 'import_export_manager', 
                        'duplicate_resolver', 'structure_manager']:
                if hasattr(self, attr):
                    try:
                        delattr(self, attr)
                    except Exception:
                        pass
            
            self._cleaned_up = True
            logger.debug("Database cleanup completed")
            
        except Exception as exc:
            logger.error("Error during Database cleanup: %s", exc, exc_info=True)
