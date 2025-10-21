"""Module for managing database backups."""

import datetime
import logging
import os
import sqlite3
from pathlib import Path
from typing import Callable

from ..base.db_base import DatabaseError
from ..types.constants import BACKUP_RETRY_ATTEMPTS, BACKUP_RETRY_DELAY
from app.config_data import app_config

logger = logging.getLogger(__name__)


def purge_old_backups(
    backup_dir: Path,
    max_backups: int,
    *,
    keep: Path | None,
    attempts: int,
    delay: float,
    logger: logging.Logger,
    sleeper: Callable[[float], None] | None = None,
) -> int:
    """Remove outdated backup files, keeping at most ``max_backups`` files."""
    files = sorted(backup_dir.glob("osteen_path_*.db"))
    if not files or len(files) <= max_backups:
        return 0

    targets = [f for f in files if keep is None or f != keep]
    target_deletions = max(0, len(files) - max_backups)
    deleted = 0

    for attempt in range(max(1, attempts)):
        if deleted >= target_deletions:
            break

        remaining = [f for f in targets if f.exists()]
        if not remaining:
            break

        for old_file in list(remaining):
            if deleted >= target_deletions:
                break
            try:
                old_file.unlink()
                deleted += 1
                targets.remove(old_file)
                logger.info("Deleted old backup: %s", old_file.name)
            except Exception as del_err:
                logger.warning(
                    "Failed to delete old backup %s: %s", old_file, del_err
                )

        if deleted >= target_deletions:
            break
        if sleeper is not None and attempt < attempts - 1:
            sleeper(delay)

    if deleted < target_deletions:
        logger.warning(
            "Requested deletion of %d old backups, removed %d",
            target_deletions,
            deleted,
        )
    return deleted


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
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            dst = backup_dir / f"osteen_path_{timestamp}.db"
            backup_dir.mkdir(parents=True, exist_ok=True)

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
            files = sorted(backup_dir.glob("osteen_path_*.db"))

            if len(files) > max_bak:
                purge_old_backups(
                    backup_dir,
                    max_bak,
                    keep=dst,
                    attempts=BACKUP_RETRY_ATTEMPTS,
                    delay=BACKUP_RETRY_DELAY,
                    logger=logger,
                    sleeper=None,
                )

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
        return app_config.settings.get_max_backups()
