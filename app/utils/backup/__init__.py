"""Backup utilities: creation and retention logic.

Public API:
- create_backup(src_db_path: Path, backups_dir: Path) -> Path
- apply_retention(backups_dir: Path, max_backups: int, keep: set[Path], *, attempts: int = 3, sleep_sec: float = 0.1) -> "RetentionResult"

"""
from .backup_manager import create_backup, apply_retention, RetentionResult
