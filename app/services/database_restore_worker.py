"""Background worker for database restore operations."""

from __future__ import annotations

import gc
import logging
import os
import shutil
import sqlite3
import time
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QObject, QRunnable, pyqtSignal

from app.core.database_manager import DatabaseManager
from app.core.paths.path_manager import PathManager
from app.models.db import Database
from app.utils.db.migrations import MigrationRunner

logger = logging.getLogger(__name__)

REQUIRED_TABLES = frozenset({"sphere", "section", "category", "link"})


class DatabaseRestoreWorkerSignals(QObject):
    """Signals for DatabaseRestoreWorker."""

    success = pyqtSignal(object, str)  # new_db, backup_name
    error = pyqtSignal(str)  # error_message


class DatabaseRestoreWorker(QRunnable):
    """Worker for database restore in background thread."""

    def __init__(
        self,
        db,
        backup_path,
        *,
        sqlite_connect=None,
        max_supported_version: int | None = None,
    ):
        super().__init__()
        self.db = db
        self.backup_path = Path(backup_path)
        self._sqlite_connect = sqlite_connect or sqlite3.connect
        self._max_supported_version = max_supported_version
        self.signals = DatabaseRestoreWorkerSignals()

    def run(self):
        """Execute restore in background thread."""
        try:
            with DatabaseManager.maintenance_scope():
                new_db, backup_name = self._restore_database(self.backup_path)
            self.signals.success.emit(new_db, backup_name)
        except Exception as exc:
            self.signals.error.emit(str(exc))

    def _restore_database(self, backup_path: Path):
        """Perform database restore (blocking operation)."""
        db_path = Path(DatabaseManager.get_db_path())
        backup_path = Path(backup_path)

        self._verify_backup_integrity(backup_path)

        logger.info(f"Starting database restore from: {backup_path}")

        # Close ALL connections
        logger.info("Closing ALL database connections")
        self.db.close_all()

        # Force Python garbage collection
        gc.collect()

        self._prepare_target_database_for_restore(db_path)

        tmp_target = db_path.with_name(f"{db_path.name}.restore_tmp")
        orig_backup = db_path.with_name(f"{db_path.name}.orig_bak")

        try:
            # 1. Copy backup to temporary staging file first
            self._copy_backup_with_retries(backup_path, tmp_target)

            # 2. Verify integrity of the staged temporary file
            self._verify_backup_integrity(tmp_target)

            # 3. Preserve original database before replacement
            has_orig = False
            if db_path.exists():
                try:
                    if orig_backup.exists():
                        orig_backup.unlink()
                    os.replace(db_path, orig_backup)
                    has_orig = True
                    logger.info(f"Preserved original database as {orig_backup}")
                except Exception as e:
                    logger.warning(f"Failed to preserve original DB via rename: {e}")

            # 4. Atomically move staged DB to live target path
            try:
                os.replace(tmp_target, db_path)
                logger.info(f"Atomically replaced live database with restored file: {db_path}")
            except Exception as replace_err:
                logger.error(f"Failed to replace live database with {tmp_target}: {replace_err}")
                # Rollback from preserved original if possible
                if has_orig and orig_backup.exists():
                    try:
                        os.replace(orig_backup, db_path)
                        logger.info("Successfully rolled back to original database")
                    except Exception as rollback_err:
                        logger.critical(f"Failed to rollback original database: {rollback_err}")
                raise replace_err

            # 5. Create new database connection to verify live database
            logger.info("Creating new database connection")
            new_db = Database()

            # Clean up preserved original on success
            if has_orig and orig_backup.exists():
                try:
                    orig_backup.unlink(missing_ok=True)
                except Exception:
                    pass

            logger.info("Database restore completed successfully")
            return new_db, backup_path.name
        finally:
            if tmp_target.exists():
                try:
                    tmp_target.unlink(missing_ok=True)
                except Exception:
                    pass

    def _prepare_target_database_for_restore(self, db_path) -> None:
        """Prepare DB files/handles before replacing file from backup."""
        self._switch_journal_mode_for_restore(db_path)

        # Wait for Windows to release file handles
        time.sleep(1.0)

        self._remove_wal_sidecar_files(db_path)

    def _switch_journal_mode_for_restore(self, db_path) -> None:
        """Best-effort switch to DELETE journal mode before file replacement."""
        logger.info("Switching database to DELETE journal mode for restore")
        try:
            temp_conn = self._open_sqlite_connection(db_path, timeout=10.0)
            try:
                temp_conn.execute("PRAGMA mmap_size = 0")
                temp_conn.execute("PRAGMA journal_mode = DELETE")
                temp_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                temp_conn.commit()
                logger.info("Successfully switched to DELETE journal mode")
            finally:
                temp_conn.close()
                del temp_conn
                gc.collect()
        except Exception as journal_err:
            logger.warning(f"Failed to switch journal mode: {journal_err}")

    def _remove_wal_sidecar_files(self, db_path) -> None:
        """Remove SQLite sidecar files (`-wal`, `-shm`) before restore copy."""
        wal_path = f"{db_path}-wal"
        shm_path = f"{db_path}-shm"
        for extra_file in [wal_path, shm_path]:
            self._remove_sidecar_file_with_retry(extra_file)

    def _remove_sidecar_file_with_retry(self, extra_file: str) -> None:
        if not os.path.exists(extra_file):
            return
        try:
            logger.info(f"Removing {extra_file}")
            os.remove(extra_file)
            logger.info(f"Successfully removed {extra_file}")
        except Exception as exc:
            logger.warning(f"Could not remove {extra_file}: {exc}")
            try:
                time.sleep(0.5)
                os.remove(extra_file)
                logger.info(f"Successfully removed {extra_file} on retry")
            except Exception as retry_exc:
                logger.error(f"Failed to remove {extra_file} on retry: {retry_exc}")
                if "wal" in extra_file.lower():
                    raise self._build_locked_wal_error(extra_file) from retry_exc

    def _build_locked_wal_error(self, file_name: str) -> OSError:
        message = QCoreApplication.translate(
            "DatabaseRestoreWorker",
            (
                "Cannot restore database: WAL file {file_name} is locked. "
                "Please close all connections and try again."
            ),
        ).format(file_name=file_name)
        return OSError(message)

    def _copy_backup_with_retries(self, backup_path, db_path, *, max_retries: int = 3) -> None:
        """Copy backup DB file with retries to tolerate transient Windows locks."""
        logger.info(f"Copying backup {backup_path} to {db_path}")
        for attempt in range(max_retries):
            try:
                shutil.copy2(backup_path, str(db_path))
                logger.info(f"Successfully copied backup to {db_path}")
                return
            except OSError as copy_err:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Copy attempt {attempt + 1} failed: {copy_err}, retrying..."
                    )
                    time.sleep(1.0)
                    gc.collect()
                else:
                    logger.error(f"All {max_retries} copy attempts failed")
                    raise

    def _get_max_supported_schema_version(self) -> int:
        if self._max_supported_version is not None:
            return self._max_supported_version
        try:
            migrations_dir = PathManager.app_root() / "models" / "migrations"
            if not migrations_dir.exists():
                return 0
            runner = MigrationRunner(None, migrations_dir)
            all_migs = runner.discover()
            if not all_migs:
                return 0
            return max(m.version for m in all_migs)
        except Exception as exc:
            logger.warning("Could not determine max supported schema version: %s", exc)
            return 0

    def _verify_backup_integrity(self, backup_path: Path | str) -> None:
        path = Path(backup_path).resolve()
        if not path.is_file():
            raise ValueError(
                QCoreApplication.translate(
                    "DatabaseRestoreWorker",
                    "Backup file does not exist: {path}",
                ).format(path=path)
            )

        if path.stat().st_size == 0:
            raise ValueError(
                QCoreApplication.translate(
                    "DatabaseRestoreWorker",
                    "Backup file is empty: {path}",
                ).format(path=path)
            )

        try:
            backup_uri = f"{path.as_uri()}?mode=ro"
            conn = self._open_sqlite_connection(backup_uri, uri=True)
            try:
                # 1. PRAGMA integrity_check
                row = conn.execute("PRAGMA integrity_check").fetchone()
                result = row[0] if row else "unknown"
                if result != "ok":
                    raise ValueError(f"SQLite integrity check failed: {result}")

                # 2. Check required tables
                tables = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                missing_tables = REQUIRED_TABLES - tables
                if missing_tables:
                    raise ValueError(
                        f"Database is missing required table(s): {', '.join(sorted(missing_tables))}"
                    )

                # 3. Check schema version
                user_ver_row = conn.execute("PRAGMA user_version").fetchone()
                user_version = int(user_ver_row[0]) if user_ver_row else 0
                max_supported = self._get_max_supported_schema_version()
                if user_version < 0:
                    raise ValueError(f"Invalid schema version: {user_version}")
                if max_supported > 0 and user_version > max_supported:
                    raise ValueError(
                        f"Backup schema version ({user_version}) is newer than supported ({max_supported})"
                    )

                # 4. PRAGMA foreign_key_check
                fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
                if fk_violations:
                    raise ValueError(
                        f"Foreign key integrity check failed: {len(fk_violations)} violation(s) found"
                    )
            finally:
                conn.close()
        except Exception as exc:
            raise ValueError(
                QCoreApplication.translate(
                    "DatabaseRestoreWorker",
                    "Backup integrity check failed: {error}",
                ).format(error=exc)
            ) from exc

    def _open_sqlite_connection(self, path, **kwargs):
        """Wrapper for sqlite connection creation to simplify tests and tracing."""
        try:
            return self._sqlite_connect(path, **kwargs)
        except TypeError:
            return self._sqlite_connect(path)
