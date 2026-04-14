"""Worker for creating database backups in background thread."""

import logging
import sqlite3
import time

from PyQt6.QtCore import QCoreApplication, QT_TRANSLATE_NOOP
from pathlib import Path
from typing import TYPE_CHECKING

from app.models.managers.backup_manager import purge_old_backups
from app.models.types.constants import BACKUP_RETRY_ATTEMPTS, BACKUP_RETRY_DELAY

from .base_worker import DatabaseWorker

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
_BACKUP_CONTEXT = "BackupWorker"
_PREPARING_BACKUP = QT_TRANSLATE_NOOP(_BACKUP_CONTEXT, "Preparing backup...")
_CREATING_BACKUP = QT_TRANSLATE_NOOP(_BACKUP_CONTEXT, "Creating backup...")
_CLEANUP_BACKUPS = QT_TRANSLATE_NOOP(
    _BACKUP_CONTEXT, "Cleaning up old backups..."
)
_BACKUP_COMPLETED = QT_TRANSLATE_NOOP(_BACKUP_CONTEXT, "Backup completed")


def _tr_backup(text: str) -> str:
    return QCoreApplication.translate(_BACKUP_CONTEXT, text)


class BackupWorker(DatabaseWorker):
    """Worker for performing backup() in background thread.

    Creates a backup copy of the database.
    """

    def __init__(self, backup_dir: Path, max_backups: int = 10):
        """
        Args:
            backup_dir: Directory for saving backups
            max_backups: Maximum number of backup files to keep
        """
        super().__init__()
        self.backup_dir = backup_dir
        self.max_backups = max_backups

    def do_work(self, connection: sqlite3.Connection) -> dict[str, str]:
        """Performs database backup.

        Args:
            connection: Database connection

        Returns:
            Dictionary with backup file information or empty dict on cancellation
        """
        from datetime import datetime

        self.emit_progress(0, 3, _tr_backup(_PREPARING_BACKUP))

        # Create backup directory if it doesn't exist
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            logger.error("Failed to create backup directory %s: %s", self.backup_dir, e)
            raise

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_filename = f"aite_bd_{timestamp}.db"
        backup_path = self.backup_dir / backup_filename

        if self.is_cancelled:
            return {}

        self.emit_progress(1, 3, _tr_backup(_CREATING_BACKUP))

        # Execute checkpoint for WAL mode
        try:
            connection.execute("PRAGMA wal_checkpoint(FULL)")
        except Exception as e:
            logger.warning("Failed to execute checkpoint: %s", e)
            # Continue with copying even if checkpoint failed

        # Copy database using SQLite backup API (safe and consistent)
        temp_path = backup_path.with_suffix('.tmp')
        try:
            dest_conn = sqlite3.connect(temp_path)
            try:
                connection.backup(dest_conn)
            finally:
                dest_conn.close()
            
            temp_path.replace(backup_path)  # Atomic operation (works on Windows)
            logger.info("Backup created: %s", backup_path)
        except (OSError, PermissionError, sqlite3.Error) as e:
            logger.error("Failed to create backup %s: %s", backup_path, e)
            # Clean up temporary file if it exists
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise

        if self.is_cancelled:
            # Delete created backup if operation is cancelled
            if backup_path.exists():
                try:
                    backup_path.unlink()
                except OSError as e:
                    logger.warning("Failed to delete backup file on cancellation %s: %s", backup_path, e)
            return {}

        self.emit_progress(2, 3, _tr_backup(_CLEANUP_BACKUPS))

        purge_old_backups(
            self.backup_dir,
            self.max_backups,
            keep=backup_path,
            attempts=BACKUP_RETRY_ATTEMPTS,
            delay=BACKUP_RETRY_DELAY,
            logger=logger,
            sleeper=time.sleep,
        )

        self.emit_progress(3, 3, _tr_backup(_BACKUP_COMPLETED))

        return {"backup_path": str(backup_path), "backup_filename": backup_filename}
