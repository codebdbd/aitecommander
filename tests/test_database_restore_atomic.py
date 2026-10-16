from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.database_manager import DatabaseManager
from app.services.database_restore_worker import DatabaseRestoreWorker


def _create_sqlite_db(path: Path, marker: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(
        "CREATE TABLE sphere (id INTEGER PRIMARY KEY, name TEXT, position INTEGER DEFAULT 0, icon_path TEXT DEFAULT '');"
    )
    conn.execute(
        "CREATE TABLE section (id INTEGER PRIMARY KEY, sphere_id INTEGER REFERENCES sphere(id), name TEXT, position INTEGER DEFAULT 0, icon_path TEXT DEFAULT '');"
    )
    conn.execute(
        "CREATE TABLE category (id INTEGER PRIMARY KEY, section_id INTEGER REFERENCES section(id), name TEXT, position INTEGER DEFAULT 0, icon_path TEXT DEFAULT '');"
    )
    conn.execute(
        "CREATE TABLE link (id INTEGER PRIMARY KEY, category_id INTEGER REFERENCES category(id), name TEXT, url TEXT DEFAULT '', type TEXT DEFAULT 'web', position INTEGER DEFAULT 0, icon_path TEXT DEFAULT '', is_favorite INTEGER DEFAULT 0, browser_key TEXT DEFAULT NULL, last_used TEXT DEFAULT NULL, notes TEXT DEFAULT '', args TEXT DEFAULT '');"
    )
    conn.execute("CREATE TABLE marker (val TEXT);")
    conn.execute("INSERT INTO marker VALUES (?);", (marker,))
    conn.execute("PRAGMA user_version = 7;")
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


def test_copy_backup_with_retries_fails_without_raw_copy_fallback(tmp_path: Path) -> None:
    src_db = tmp_path / "source.db"
    dest_db = tmp_path / "dest.db"
    _create_sqlite_db(src_db, "source_data")

    mock_db = MagicMock()
    worker = DatabaseRestoreWorker(mock_db, src_db)

    mock_src_conn = MagicMock()
    mock_src_conn.backup.side_effect = sqlite3.OperationalError("database is locked")

    with patch.object(worker, "_sqlite_connect", return_value=mock_src_conn):
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            worker._copy_backup_with_retries(src_db, dest_db, max_retries=2)

    # Ensure dest_db does not exist and raw copy was NOT used
    assert not dest_db.exists()



def test_restore_aborts_if_original_cannot_be_preserved(tmp_path):
    db_path = tmp_path / "live.db"
    backup_path = tmp_path / "backup.db"
    _create_sqlite_db(db_path, "critical_user_data")
    _create_sqlite_db(backup_path, "backup_data")
    worker = DatabaseRestoreWorker(MagicMock(), backup_path)
    real_replace = worker._restore_database.__globals__["os"].replace

    def failing_preservation(src, dst):
        if Path(src) == db_path:
            raise OSError("Cannot preserve original")
        return real_replace(src, dst)

    with (
        patch.object(DatabaseManager, "get_db_path", return_value=db_path),
        patch("app.services.database_restore_worker.Database"),
        patch("os.replace", side_effect=failing_preservation),
        patch("app.services.database_restore_worker.time.sleep"),
        pytest.raises(OSError, match="Cannot preserve original"),
    ):
        worker._restore_database(backup_path)
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT val FROM marker").fetchone()[0] == "critical_user_data"


@pytest.mark.parametrize("wal_exists", [True, False])
@pytest.mark.parametrize("failure", ["exception", "busy", "mode"])
def test_restore_keeps_wal_when_checkpoint_is_not_safe(tmp_path, failure, wal_exists):
    db_path = tmp_path / "live.db"
    wal_path = Path(str(db_path) + "-wal")
    if wal_exists:
        wal_path.write_bytes(b"committed data not yet checkpointed")
    conn = MagicMock()

    def execute(sql):
        cursor = MagicMock()
        if "wal_checkpoint" in sql:
            if failure == "exception":
                raise sqlite3.OperationalError("database is locked")
            cursor.fetchone.return_value = (1, 5, 2) if failure == "busy" else (0, 0, 0)
        elif "journal_mode" in sql:
            cursor.fetchone.return_value = ("wal" if failure == "mode" else "delete",)
        return cursor

    conn.execute.side_effect = execute
    worker = DatabaseRestoreWorker(MagicMock(), "backup.db", sqlite_connect=lambda *a, **kw: conn)
    with (
        patch("app.services.database_restore_worker.time.sleep"),
        pytest.raises((sqlite3.OperationalError, RuntimeError)),
    ):
        worker._prepare_target_database_for_restore(db_path)
    if wal_exists:
        assert wal_path.read_bytes() == b"committed data not yet checkpointed"
    else:
        assert not wal_path.exists()
    conn.close.assert_called_once()


def test_busy_sqlite_reader_preserves_committed_wal_data(tmp_path):
    db_path = tmp_path / "live.db"
    writer = sqlite3.connect(db_path)
    reader = sqlite3.connect(db_path)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE marker (val TEXT)")
        writer.execute("INSERT INTO marker VALUES ('original')")
        writer.commit()
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM marker").fetchall()
        writer.execute("UPDATE marker SET val='committed update'")
        writer.commit()
        wal_path = Path(str(db_path) + "-wal")
        wal_before = wal_path.read_bytes()
        worker = DatabaseRestoreWorker(MagicMock(), "backup.db")
        def connect(*args, **kwargs):
            return sqlite3.connect(db_path, timeout=0)
        with (
            patch.object(worker, "_open_sqlite_connection", side_effect=connect),
            pytest.raises(sqlite3.OperationalError, match="checkpoint is busy"),
        ):
            worker._prepare_target_database_for_restore(db_path)
        assert wal_path.read_bytes() == wal_before
        assert writer.execute("SELECT val FROM marker").fetchone()[0] == "committed update"
    finally:
        reader.close()
        writer.close()
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT val FROM marker").fetchone()[0] == "committed update"


def test_restore_corrupt_database_without_wal(tmp_path):
    db_path = tmp_path / "live.db"
    db_path.write_bytes(b"damaged database")
    backup_path = tmp_path / "backup.db"
    _create_sqlite_db(backup_path, "recovered data")
    worker = DatabaseRestoreWorker(MagicMock(), backup_path)
    with (
        patch.object(DatabaseManager, "get_db_path", return_value=db_path),
        patch("app.services.database_restore_worker.Database"),
        patch("app.services.database_restore_worker.time.sleep"),
    ):
        worker._restore_database(backup_path)
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT val FROM marker").fetchone()[0] == "recovered data"
