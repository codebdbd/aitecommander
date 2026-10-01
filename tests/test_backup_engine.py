"""Unit tests for database backup engine and rotation logic."""

import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models.managers.backup_manager import purge_old_backups
from app.models.workers.backup_worker import BackupWorker


def test_purge_old_backups_cleans_orphaned_tmp_files(tmp_path: Path) -> None:
    """Orphaned .tmp files must be deleted while active keep_tmp is preserved."""
    # Create orphaned .tmp files
    orphan1 = tmp_path / "aite_bd_20260101_000000_000001.tmp"
    orphan1.write_bytes(b"garbage")
    orphan2 = tmp_path / "aite_bd_20260101_000000_000002.tmp"
    orphan2.write_bytes(b"garbage")

    # Active backup being written
    keep_file = tmp_path / "aite_bd_20260101_000000_000003.db"
    keep_tmp = tmp_path / "aite_bd_20260101_000000_000003.tmp"
    keep_tmp.write_bytes(b"active")

    logger = MagicMock()
    purge_old_backups(
        tmp_path,
        max_backups=5,
        keep=keep_file,
        attempts=1,
        delay=0.01,
        logger=logger,
    )

    assert not orphan1.exists()
    assert not orphan2.exists()
    assert keep_tmp.exists()


def test_purge_old_backups_rotation_by_mtime(tmp_path: Path) -> None:
    """Rotation must respect mtime and delete older backups down to max_backups."""
    # Create 5 backups with explicit modification times
    files = []
    base_time = time.time() - 1000
    for idx in range(5):
        f = tmp_path / f"aite_bd_20260101_000000_00000{idx}.db"
        f.write_bytes(b"data")
        # Ensure older idx has older mtime
        os_time = base_time + idx * 50
        import os
        os.utime(f, (os_time, os_time))
        files.append(f)

    logger = MagicMock()
    # Keep max 3 backups
    deleted_count = purge_old_backups(
        tmp_path,
        max_backups=3,
        keep=files[-1],
        attempts=1,
        delay=0.01,
        logger=logger,
    )

    assert deleted_count == 2
    # The two oldest must be removed
    assert not files[0].exists()
    assert not files[1].exists()
    # The three newest must remain
    assert files[2].exists()
    assert files[3].exists()
    assert files[4].exists()


def test_backup_worker_creates_valid_backup_with_quick_check(tmp_path: Path) -> None:
    """BackupWorker must successfully create backup and pass quick_check."""
    db_file = tmp_path / "source.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT)")
    conn.execute("INSERT INTO test VALUES (1, 'hello')")
    conn.commit()

    backup_dir = tmp_path / "backups"
    worker = BackupWorker(backup_dir, max_backups=5)

    result = worker.do_work(conn)
    conn.close()

    assert "backup_path" in result
    backup_path = Path(result["backup_path"])
    assert backup_path.exists()
    assert backup_path.stat().st_size > 0

    # Verify backup database content
    b_conn = sqlite3.connect(backup_path)
    cur = b_conn.execute("SELECT val FROM test WHERE id = 1")
    row = cur.fetchone()
    b_conn.close()
    assert row is not None
    assert row[0] == "hello"


def test_backup_worker_fails_on_quick_check_error(tmp_path: Path) -> None:
    """BackupWorker must raise sqlite3.DatabaseError and clean up .tmp if quick_check fails."""
    db_file = tmp_path / "source.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
    conn.commit()

    backup_dir = tmp_path / "backups"
    worker = BackupWorker(backup_dir, max_backups=5)

    # Subclass sqlite3.Connection to simulate quick_check failure on .tmp file
    class CorruptedConnection(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if "quick_check" in sql.lower():
                class FakeCursor:
                    def fetchone(self):
                        return ["*** btree corruption ***"]
                return FakeCursor()
            return super().execute(sql, *args, **kwargs)

    orig_connect = sqlite3.connect

    def fake_connect(path, *args, **kwargs):
        if ".tmp" in str(path):
            kwargs["factory"] = CorruptedConnection
        return orig_connect(path, *args, **kwargs)

    with patch("sqlite3.connect", side_effect=fake_connect):
        with pytest.raises(sqlite3.DatabaseError, match="Backup quick_check failed"):
            worker.do_work(conn)

    conn.close()
    # Ensure no .tmp or .db remained
    assert list(backup_dir.glob("*.tmp")) == []
    assert list(backup_dir.glob("*.db")) == []


def test_restore_dialog_detects_all_supported_backup_formats(tmp_path: Path) -> None:
    """RestoreDbDialog must discover .db, .zip and .bak files."""
    from PyQt6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])

    from app.views.windows.dialogs.restore_db_dialog import RestoreDbDialog
    (tmp_path / "aite_bd_20260101_100000.db").write_bytes(b"db_data")
    (tmp_path / "aite_bd_20260101_110000.zip").write_bytes(b"zip_data")
    (tmp_path / "links.db.bak").write_bytes(b"bak_data")
    (tmp_path / "unrelated.txt").write_bytes(b"text")

    dlg = RestoreDbDialog(backup_dir=tmp_path)
    files = dlg._get_backup_files()
    file_names = {f.name for f in files}

    assert "aite_bd_20260101_100000.db" in file_names
    assert "aite_bd_20260101_110000.zip" in file_names
    assert "links.db.bak" in file_names
    assert "unrelated.txt" not in file_names
