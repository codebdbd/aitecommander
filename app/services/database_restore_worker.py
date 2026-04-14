"""Background worker for database restore operations."""

from __future__ import annotations

import gc
import logging
import os
import shutil
import sqlite3
import time

from PyQt6.QtCore import QCoreApplication, QObject, QRunnable, pyqtSignal

from app.core.database_manager import DatabaseManager
from app.models.db import Database

logger = logging.getLogger(__name__)


class DatabaseRestoreWorkerSignals(QObject):
    """Signals for DatabaseRestoreWorker."""

    success = pyqtSignal(object, str)  # new_db, backup_name
    error = pyqtSignal(str)  # error_message


class DatabaseRestoreWorker(QRunnable):
    """Worker for database restore in background thread."""

    def __init__(self, db, backup_path, *, sqlite_connect=None):
        super().__init__()
        self.db = db
        self.backup_path = backup_path
        self._sqlite_connect = sqlite_connect or sqlite3.connect
        self.signals = DatabaseRestoreWorkerSignals()

    def run(self):
        """Execute restore in background thread."""
        try:
            new_db, backup_name = self._restore_database(self.backup_path)
            self.signals.success.emit(new_db, backup_name)
        except Exception as exc:
            self.signals.error.emit(str(exc))

    def _restore_database(self, backup_path):
        """Perform database restore (blocking operation)."""
        db_path = DatabaseManager.get_db_path()

        self._verify_backup_integrity(backup_path)

        logger.info(f"Starting database restore from: {backup_path}")

        # Close ALL connections
        logger.info("Closing ALL database connections")
        self.db.close_all()

        # Force Python garbage collection
        gc.collect()

        self._prepare_target_database_for_restore(db_path)
        self._copy_backup_with_retries(backup_path, db_path)

        # Create new database connection
        logger.info("Creating new database connection")
        new_db = Database()
        logger.info("Database restore completed successfully")
        return new_db, backup_path.name

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

    def _verify_backup_integrity(self, backup_path):
        try:
            conn = self._open_sqlite_connection(backup_path)
            try:
                row = conn.execute("PRAGMA integrity_check").fetchone()
            finally:
                conn.close()
            result = row[0] if row else "unknown"
            if result != "ok":
                raise ValueError(f"Backup integrity check failed: {result}")
        except Exception as exc:
            raise ValueError(
                QCoreApplication.translate(
                    "DatabaseRestoreWorker",
                    "Backup integrity check failed: {error}",
                ).format(error=exc)
            ) from exc

    def _open_sqlite_connection(self, path, **kwargs):
        """Wrapper for sqlite connection creation to simplify tests and tracing."""
        return self._sqlite_connect(path, **kwargs)
