from __future__ import annotations

import gc
import logging
import sqlite3
import threading
import time
import warnings
from contextlib import AbstractContextManager
from typing import Any, Callable, Protocol

from PyQt6.QtCore import (
    QCoreApplication,
    QObject,
    QT_TRANSLATE_NOOP,
    Qt,
    QThread,
    QThreadPool,
    pyqtBoundSignal,
    pyqtSignal,
    pyqtSlot,
)

from app.config_data import app_config
from app.core.database_manager import DatabaseManager
from app.core.paths.path_manager import PathManager

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
)

logger = logging.getLogger(__name__)
_DB_CONTEXT = "DatabaseInit"
_DB_APPLY_MIGRATIONS = QT_TRANSLATE_NOOP(
    _DB_CONTEXT, "Applying migrations..."
)
_DB_INIT_DEFAULTS = QT_TRANSLATE_NOOP(
    _DB_CONTEXT, "Initializing default data..."
)


def _tr_db(text: str) -> str:
    return QCoreApplication.translate(_DB_CONTEXT, text)


class FinishedCallback(Protocol):
    """Callback protocol for finished operations."""
    def __call__(self, result: Any) -> None: ...


class ErrorCallback(Protocol):
    """Callback protocol for error handling."""
    def __call__(self, exception: Exception, traceback: str) -> None: ...


class ProgressCallback(Protocol):
    """Callback protocol for progress updates."""
    def __call__(self, current: int, total: int, message: str) -> None: ...

SCHEMA_PATH = PathManager.app_root() / "models" / "schema.sql"
MIGRATIONS_DIR = PathManager.app_root() / "models" / "migrations"
PATHS = app_config.paths
_ORG_NAME = app_config.get("app.org_name", PathManager.DEFAULT_ORG_NAME)
_APP_NAME = app_config.get("app.name", PathManager.DEFAULT_APP_NAME)
BACKUP_DIR = PathManager.backups_dir(_ORG_NAME, _APP_NAME)


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

    def __init__(self, parent: QObject | None = None):
        """Initializes Database. Raises TypeError if parent is not QObject or None."""
        if parent is not None and not isinstance(parent, QObject):
            raise TypeError(f"parent must be QObject or None, got {type(parent).__name__}")
        
        super().__init__(parent)

        self.db_path = str(DatabaseManager.get_db_path())
        self._backup_lock = threading.Lock()
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

    def transaction(self) -> AbstractContextManager[None]:
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
        db_path = DatabaseManager.get_db_path()
        is_new = not db_path.exists()
        
        try:
            self.operation_started.emit(operation, 1)
            
            with db_lock:
                self.operation_progress.emit(
                    operation, 0, 1, _tr_db(_DB_APPLY_MIGRATIONS)
                )
                try:
                    applied = DatabaseManager.ensure_schema()
                    logger.info("Migrations applied: %d", applied)
                except Exception as migration_err:
                    logger.error("Migration failed: %s", migration_err, exc_info=True)
                    self.operation_finished.emit(operation, False)
                    raise DatabaseError(f"Migration failed: {migration_err}") from migration_err
            
            if is_new or self._is_sphere_empty():
                try:
                    self.operation_progress.emit(
                        operation, 1, 1, _tr_db(_DB_INIT_DEFAULTS)
                    )
                    with db_lock:
                        self.spheres.initialize_default_spheres()
                except Exception as init_err:
                    logger.error("Failed to initialize default data: %s", init_err, exc_info=True)
                    self.operation_finished.emit(operation, False)
                    raise DatabaseError(f"Failed to initialize default data: {init_err}") from init_err
            
            self.operation_finished.emit(operation, True)
            logger.info("Database initialization completed successfully")
        
        except DatabaseError:
            if is_new and db_path.exists():
                try:
                    self.close()
                    db_path.unlink()
                    logger.info("Removed incomplete database file after initialization failure")
                except Exception as cleanup_err:
                    logger.warning("Failed to remove incomplete database: %s", cleanup_err)
            raise
        
        except Exception as e:
            self.operation_finished.emit(operation, False)
            logger.error("Unexpected error during initialization: %s", e, exc_info=True)
            
            if is_new and db_path.exists():
                try:
                    self.close()
                    db_path.unlink()
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
        on_finished: FinishedCallback | None = None,
        on_error: ErrorCallback | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        """Initializes DB in background thread. Callbacks: on_finished(stats), on_error(e, tb), on_progress(c, t, m)."""
        try:
            from .workers import InitializationWorker

            worker = InitializationWorker(MIGRATIONS_DIR)
            
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

    class _CallbackDispatcher(QObject):
        """Helper QObject to marshal callbacks back to the GUI thread."""

        invoke = pyqtSignal(object, tuple, dict)

        def __init__(self) -> None:
            parent = QCoreApplication.instance()
            super().__init__(parent)
            self.invoke.connect(
                self._execute, Qt.ConnectionType.QueuedConnection  # type: ignore[arg-type]
            )

        @pyqtSlot(object, tuple, dict)
        def _execute(
            self, callback: Callable[..., Any], args: tuple, kwargs: dict
        ) -> None:
            try:
                callback(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "Error in GUI callback %s: %s",
                    getattr(callback, "__name__", repr(callback)),
                    exc,
                    exc_info=True,
                )

    _callback_dispatcher: _CallbackDispatcher | None = None

    def _get_callback_dispatcher(self) -> _CallbackDispatcher | None:
        """Return shared dispatcher if QApplication is running."""
        app = QCoreApplication.instance()
        if app is None:
            return None
        if Database._callback_dispatcher is None:
            Database._callback_dispatcher = Database._CallbackDispatcher()
        return Database._callback_dispatcher

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
    
    def _safe_callback(self, callback: Callable, *args: Any, **kwargs: Any) -> None:
        """Invoke callbacks on the GUI thread when possible."""
        dispatcher = self._get_callback_dispatcher()
        if dispatcher is None:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(
                    "Error in user callback %s: %s",
                    getattr(callback, "__name__", repr(callback)),
                    e,
                    exc_info=True,
                )
                self._safe_emit(self.error_occurred, "Callback error", str(e))
            return

        try:
            dispatcher.invoke.emit(callback, args, kwargs)
        except Exception as e:  # pragma: no cover - defensive
            logger.error(
                "Failed to dispatch callback %s: %s",
                getattr(callback, "__name__", repr(callback)),
                e,
                exc_info=True,
            )
    
    def _ensure_not_gui_thread(self, method_name: str) -> None:
        """Ensures method is not called from GUI thread. Raises RuntimeError if violated."""
        try:
            from PyQt6.QtWidgets import QApplication
            
            app = QApplication.instance()
            if app is not None and QThread.currentThread() == app.thread():
                raise RuntimeError(f"{method_name}() is a blocking operation and must not be called from GUI thread. Use {method_name}_async() instead.")
        except ImportError:
            pass

    def _is_sphere_empty(self) -> bool:
        try:
            row = self.connection.execute("SELECT 1 FROM sphere LIMIT 1").fetchone()
            return row is None
        except Exception:
            return False

    def __enter__(self) -> Database:
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
        """Return database connection from DatabaseManager."""
        return DatabaseManager.get_connection()


    def get_section_id_by_category(self, category_id: int) -> int | None:
        """Returns section_id for given category."""
        row = self.categories.get_category_by_id(category_id)
        return row["section_id"] if row else None

    def get_sphere_id_by_section(self, section_id: int) -> int | None:
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
                
                # UPDATE ╨▒╨░╤В╤З╨░╨╝╨╕ (╨┐╤А╨╛╨▓╨╡╤А╨║╨░ ╤Г╨╢╨╡ ╨▓╤Л╨┐╨╛╨╗╨╜╨╡╨╜╨░)
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
        """Optimized ID existence check with adaptive batching."""
        if not ids:
            return
        
        safe_table_name = self._escape_identifier(table_name)
        
        # ╨Р╨┤╨░╨┐╤В╨╕╨▓╨╜╤Л╨╣ ╤А╨░╨╖╨╝╨╡╤А ╨▒╨░╤В╤З╨░ ╨╜╨░ ╨╛╤Б╨╜╨╛╨▓╨╡ SQLITE_MAX_COMPOUND_SELECT
        max_batch = min(500, 32766 // 2)
        
        if len(ids) <= max_batch:
            # ╨С╤Л╤Б╤В╤А╤Л╨╣ ╨┐╤Г╤В╤М: VALUES ╨┤╨╗╤П ╨╝╨░╨╗╤Л╤Е/╤Б╤А╨╡╨┤╨╜╨╕╤Е ╤Б╨┐╨╕╤Б╨║╨╛╨▓
            placeholders = ",".join(f"({id_val})" for id_val in ids)
            
            query = f"""
                WITH input_ids(id) AS (VALUES {placeholders})
                SELECT input_ids.id 
                FROM input_ids
                LEFT JOIN {safe_table_name} t ON input_ids.id = t.id
                WHERE t.id IS NULL
            """
            
            missing = self.connection.execute(query).fetchall()
            
            if missing:
                missing_ids = [row["id"] for row in missing]
                raise ValidationError(
                    f"Records with ID not found: {missing_ids} in table {table_name}"
                )
        else:
            # ╨Ф╨╗╤П ╨▒╨╛╨╗╤М╤И╨╕╤Е ╤Б╨┐╨╕╤Б╨║╨╛╨▓: temp table (╤Н╤Д╤Д╨╡╨║╤В╨╕╨▓╨╜╨╡╨╡ ╨┤╨╗╤П 10000+ ID)
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
                        raise ValidationError(
                            f"Records with ID not found: {missing_ids} in table {table_name}"
                        )
                finally:
                    self.connection.execute("DELETE FROM _check_ids")
    
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
        on_finished: FinishedCallback | None = None,
        on_error: ErrorCallback | None = None,
        on_progress: ProgressCallback | None = None,
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
        on_finished: FinishedCallback | None = None,
        on_error: ErrorCallback | None = None,
        on_progress: ProgressCallback | None = None,
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

            worker = ImportStructureWorker(data)
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
        with self._backup_lock:
            return self.backup_manager.backup(BACKUP_DIR)

    def backup_async(
        self,
        on_finished: FinishedCallback | None = None,
        on_error: ErrorCallback | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        """Creates backup in background thread. Callbacks: on_finished(result), on_error(e, tb), on_progress(c, t, m)."""
        from .workers import BackupWorker

        if not self._backup_lock.acquire(blocking=False):
            logger.info("Backup already in progress; skipping async backup request")
            return

        def _release_backup_lock(*_args):
            if self._backup_lock.locked():
                self._backup_lock.release()

        try:
            worker = BackupWorker(BACKUP_DIR, app_config.settings.get_max_backups())
        except Exception:
            _release_backup_lock()
            raise

        worker.signals.finished.connect(_release_backup_lock)
        worker.signals.error.connect(_release_backup_lock)
        worker.signals.cancelled.connect(_release_backup_lock)
        
        if on_finished:
            worker.signals.finished.connect(lambda result: self._safe_callback(on_finished, result))
        if on_error:
            worker.signals.error.connect(lambda e, tb: self._safe_callback(on_error, e, tb))
        if on_progress:
            worker.signals.progress.connect(lambda c, t, m: self._safe_callback(on_progress, c, t, m))
        try:
            self._thread_pool.start(worker)
            logger.info("Started async backup")
        except Exception:
            _release_backup_lock()
            raise

    def export_section_tree(self, section_id: int) -> dict[str, Any]:
        return self.import_export_manager.export_section_tree(section_id)

    def import_section_tree(self, tree: dict[str, Any]) -> int:
        return self.import_export_manager.import_section_tree(tree)

    def import_section_trees_bulk(self, trees: list[dict[str, Any]]) -> None:
        return self.import_export_manager.import_section_trees_bulk(trees)

    def export_category_tree(self, category_id: int) -> dict[str, Any]:
        return self.import_export_manager.export_category_tree(category_id)

    def import_category_tree(self, tree: dict[str, Any]) -> int:
        return self.import_export_manager.import_category_tree(tree)

    def import_category_trees_bulk(self, trees: list[dict[str, Any]]) -> None:
        return self.import_export_manager.import_category_trees_bulk(trees)

    def is_connected(self) -> bool:
        return DatabaseManager.is_connected()


    def close(self) -> None:
        """Close database connection for current thread."""
        try:
            DatabaseManager.close()
            logger.debug("Database connection closed")
        except Exception as e:
            logger.error("Error closing connection: %s", e, exc_info=True)


    def close_all(self) -> None:
        """Close ALL database connections from all threads. Required for DB restore."""
        logger.info("Closing all database connections...")
        try:
            DatabaseManager.close_all()
        finally:
            gc.collect()
        logger.info("All database connections closed")


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
                        logger.warning(
                            "Thread pool did not finish within %dms timeout, some workers may still be running. Active threads: %d",
                            timeout_ms,
                            self._thread_pool.activeThreadCount(),
                        )
                except Exception as e:
                    logger.warning("Error waiting for thread pool: %s", e)

            try:
                DatabaseManager.close_all()
            except Exception as e:
                logger.warning("Error closing database connections: %s", e)

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


