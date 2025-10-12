"""Module for managing database backups."""

import datetime
import logging
import os
import sqlite3
import time
from pathlib import Path

from ..base.db_base import DatabaseError
from ..types.constants import BACKUP_RETRY_ATTEMPTS, BACKUP_RETRY_DELAY

logger = logging.getLogger(__name__)


class BackupManager:
    """Database backup management."""

    def __init__(self, db):
        """
        Args:
            db: Database instance for accessing connection and signals
        """
        self.db = db

    def backup(self, backup_dir: Path):
        """Creates database backup and deletes old copies when limit is exceeded.

        Args:
            backup_dir: Directory for storing backups

        Raises:
            DatabaseError: When backup creation fails
        """
        operation = "backup"
        try:
            self.db.operation_started.emit(operation, 2)
            max_bak = self._get_max_backups()

            # 1) Create new backup
            self.db.operation_progress.emit(operation, 0, 2, "Creating backup...")
            now = datetime.datetime.now()
            timestamp = now.strftime("%Y%m%d_%H%M%S_%f")
            dst = backup_dir / f"links_{timestamp}.db"

            with sqlite3.connect(self.db.db_path) as src, sqlite3.connect(dst) as dest:
                src.backup(dest)
            logger.info("Backup created: %s", dst)

            # Explicitly update file timestamp
            try:
                os.utime(dst, None)
            except Exception:
                pass

            # 2) Cleanup beyond limit
            self.db.operation_progress.emit(
                operation, 1, 2, "Cleaning up old copies..."
            )
            files = sorted(backup_dir.glob("links_*.db"))

            if len(files) > max_bak:
                candidates = [f for f in files if f != dst]
                deleted_count = 0
                target_deletions = len(files) - max_bak

                for attempt in range(BACKUP_RETRY_ATTEMPTS):
                    files_to_try = [f for f in candidates if f.exists()]
                    if not files_to_try or deleted_count >= target_deletions:
                        break

                    for old_file in files_to_try:
                        if deleted_count >= target_deletions:
                            break
                        try:
                            old_file.unlink()
                            deleted_count += 1
                            if old_file in candidates:
                                candidates.remove(old_file)
                        except Exception as del_err:
                            logger.warning(
                                "Failed to delete old backup %s: %s",
                                old_file,
                                del_err,
                                exc_info=False,
                            )

                    if (
                        attempt < BACKUP_RETRY_ATTEMPTS - 1
                        and deleted_count < target_deletions
                    ):
                        time.sleep(BACKUP_RETRY_DELAY)

            self.db.operation_finished.emit(operation, True)

            # Notify UI about successful backup creation
            try:
                self.db.backup_created.emit(str(dst))
            except Exception as signal_err:
                logger.debug(
                    "Error sending backup_created signal: %s",
                    signal_err,
                    exc_info=True,
                )
        except Exception as e:
            logger.error("Error creating backup: %s", e, exc_info=True)
            self.db.operation_finished.emit(operation, False)
            try:
                self.db.error_occurred.emit("Backup error", str(e))
            except Exception:
                pass
            raise DatabaseError(f"Failed to create backup: {e}") from e

    def _get_max_backups(self) -> int:
        """Returns maximum number of backups from user settings."""
        from app.config_data import app_config

        return app_config.settings.get_max_backups()
