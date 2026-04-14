"""Module for managing database backups."""

import logging
import sqlite3
from pathlib import Path
from typing import Callable

from ..base.db_base import DatabaseError

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
    files = sorted(backup_dir.glob("aite_bd_*.db"))
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
    """Database backup management.
    
    Delegates actual backup operations to BackupWorker for consistency.
    This class provides a synchronous interface suitable for CLI/scripts.
    """

    def __init__(self, db):
        """
        Args:
            db: Database instance for accessing connection and signals
        """
        self.db = db

    def backup(self, backup_dir: Path) -> str:
        """Creates database backup synchronously.

        Args:
            backup_dir: Directory for storing backups

        Returns:
            Path to created backup file

        Raises:
            DatabaseError: When backup creation fails
            
        Note:
            This is a synchronous operation suitable for CLI/scripts.
            For GUI applications, use Database.backup_async() instead.
            
            This method delegates to BackupWorker to ensure consistent
            backup logic across sync and async operations.
        """
        from ..workers.backup_worker import BackupWorker
        
        operation = "backup"
        connection = None
        
        try:
            self.db.operation_started.emit(operation, 2)
            
            # Get max backups setting
            from app.config_data import app_config
            max_backups = app_config.settings.get_max_backups()
            
            # Create worker instance
            worker = BackupWorker(backup_dir, max_backups)
            
            # Open connection for synchronous execution
            connection = sqlite3.connect(self.db.db_path)
            
            # Execute backup synchronously
            result = worker.do_work(connection)
            
            if not result:
                raise DatabaseError("Backup was cancelled or returned empty result")
            
            backup_path = result.get("backup_path")
            if not backup_path:
                raise DatabaseError("Backup did not return a valid path")
            
            self.db.operation_finished.emit(operation, True)
            
            # Notify UI about successful backup creation
            try:
                self.db.backup_created.emit(backup_path)
            except Exception as signal_err:
                logger.debug(
                    "Error sending backup_created signal: %s",
                    signal_err,
                    exc_info=True,
                )
            
            return backup_path
            
        except Exception as e:
            logger.error("Error creating backup: %s", e, exc_info=True)
            self.db.operation_finished.emit(operation, False)
            try:
                self.db.error_occurred.emit("Backup error", str(e))
            except Exception:
                pass
            raise DatabaseError(f"Failed to create backup: {e}") from e
        finally:
            if connection:
                try:
                    connection.close()
                except Exception as close_err:
                    logger.warning("Error closing backup connection: %s", close_err)
