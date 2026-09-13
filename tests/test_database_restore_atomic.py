from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.core.database_manager import DatabaseManager
from app.services.database_restore_worker import DatabaseRestoreWorker


def _create_sqlite_db(path: Path, marker: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sphere (id INTEGER PRIMARY KEY);")
    conn.execute("CREATE TABLE section (id INTEGER PRIMARY KEY, sphere_id INTEGER REFERENCES sphere(id));")
    conn.execute("CREATE TABLE category (id INTEGER PRIMARY KEY, section_id INTEGER REFERENCES section(id));")
    conn.execute("CREATE TABLE link (id INTEGER PRIMARY KEY, category_id INTEGER REFERENCES category(id));")
    conn.execute("CREATE TABLE marker (val TEXT);")
    conn.execute("INSERT INTO marker VALUES (?);", (marker,))
    conn.commit()
    conn.close()


def test_atomic_restore_success(tmp_path: Path) -> None:
    db_path = tmp_path / "live.db"
    backup_path = tmp_path / "backup.db"

    _create_sqlite_db(db_path, "live_data")
    _create_sqlite_db(backup_path, "backup_data")

    mock_db = MagicMock()
    worker = DatabaseRestoreWorker(mock_db, backup_path)

    with patch.object(DatabaseManager, "get_db_path", return_value=db_path):
        with patch("app.services.database_restore_worker.Database"):
            new_db, name = worker._restore_database(backup_path)

    # 1. Live database now contains the restored backup data
    conn = sqlite3.connect(db_path)
    val = conn.execute("SELECT val FROM marker").fetchone()[0]
    conn.close()
    assert val == "backup_data"

    # 2. Temporary and backup artifacts are cleaned up
    tmp_target = db_path.with_name(f"{db_path.name}.restore_tmp")
    orig_backup = db_path.with_name(f"{db_path.name}.orig_bak")
    assert not tmp_target.exists()
    assert not orig_backup.exists()


def test_atomic_restore_rollback_on_replacement_error(tmp_path: Path) -> None:
    db_path = tmp_path / "live.db"
    backup_path = tmp_path / "backup.db"

    _create_sqlite_db(db_path, "critical_user_data")
    _create_sqlite_db(backup_path, "backup_data")

    mock_db = MagicMock()
    worker = DatabaseRestoreWorker(mock_db, backup_path)

    real_replace = worker._restore_database.__globals__["os"].replace
    tmp_target = db_path.with_name(f"{db_path.name}.restore_tmp")

    def failing_replace(src, dst):
        # Fail only when trying to replace live DB with tmp_target
        if str(src) == str(tmp_target) and str(dst) == str(db_path):
            raise OSError("Simulated disk/permission error on atomic replacement")
        return real_replace(src, dst)

    with patch.object(DatabaseManager, "get_db_path", return_value=db_path):
        with patch("os.replace", side_effect=failing_replace):
            with pytest.raises(OSError, match="Simulated disk/permission error"):
                worker._restore_database(backup_path)

    # Live database must be rolled back to original data without corruption
    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    val = conn.execute("SELECT val FROM marker").fetchone()[0]
    conn.close()
    assert val == "critical_user_data"

    # Temporary staging file must be cleaned up
    assert not tmp_target.exists()
