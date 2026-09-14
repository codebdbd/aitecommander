from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.database_restore_worker import DatabaseRestoreWorker


def _build_valid_test_db(path: Path, *, user_version: int = 1) -> None:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("CREATE TABLE sphere (id INTEGER PRIMARY KEY, name TEXT);")
    conn.execute("CREATE TABLE section (id INTEGER PRIMARY KEY, sphere_id INTEGER REFERENCES sphere(id), name TEXT);")
    conn.execute("CREATE TABLE category (id INTEGER PRIMARY KEY, section_id INTEGER REFERENCES section(id), name TEXT);")
    conn.execute("CREATE TABLE link (id INTEGER PRIMARY KEY, category_id INTEGER REFERENCES category(id), name TEXT);")
    conn.execute(f"PRAGMA user_version = {user_version};")
    conn.commit()
    conn.close()


def test_verify_backup_rejects_nonexistent_file(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does_not_exist.db"
    worker = DatabaseRestoreWorker(MagicMock(), nonexistent)

    with pytest.raises(ValueError, match="does not exist|не существует|does_not_exist"):
        worker._verify_backup_integrity(nonexistent)

    # Must NOT create empty file on check
    assert not nonexistent.exists()


def test_verify_backup_rejects_empty_file(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.db"
    empty_file.touch()

    worker = DatabaseRestoreWorker(MagicMock(), empty_file)

    with pytest.raises(ValueError, match="empty|пуст"):
        worker._verify_backup_integrity(empty_file)


def test_verify_backup_rejects_corrupted_file(tmp_path: Path) -> None:
    corrupted = tmp_path / "corrupted.db"
    corrupted.write_bytes(b"This is completely invalid sqlite database data 1234567890")

    worker = DatabaseRestoreWorker(MagicMock(), corrupted)

    with pytest.raises(ValueError, match="integrity check failed|file is not a database|не является"):
        worker._verify_backup_integrity(corrupted)


def test_verify_backup_rejects_database_missing_required_tables(tmp_path: Path) -> None:
    wrong_db = tmp_path / "alien_app.db"
    conn = sqlite3.connect(wrong_db)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT);")
    conn.commit()
    conn.close()

    worker = DatabaseRestoreWorker(MagicMock(), wrong_db)

    with pytest.raises(ValueError, match="missing required table"):
        worker._verify_backup_integrity(wrong_db)


def test_verify_backup_rejects_future_schema_version(tmp_path: Path) -> None:
    future_db = tmp_path / "future.db"
    _build_valid_test_db(future_db, user_version=999)

    worker = DatabaseRestoreWorker(MagicMock(), future_db, max_supported_version=7)

    with pytest.raises(ValueError, match="newer than supported"):
        worker._verify_backup_integrity(future_db)


def test_verify_backup_rejects_foreign_key_violations(tmp_path: Path) -> None:
    fk_corrupted_db = tmp_path / "fk_corrupted.db"
    conn = sqlite3.connect(fk_corrupted_db)
    # Create tables without foreign keys enforced during insertion to create orphan records
    conn.execute("PRAGMA foreign_keys = OFF;")
    conn.execute("CREATE TABLE sphere (id INTEGER PRIMARY KEY, name TEXT);")
    conn.execute("CREATE TABLE section (id INTEGER PRIMARY KEY, sphere_id INTEGER REFERENCES sphere(id), name TEXT);")
    conn.execute("CREATE TABLE category (id INTEGER PRIMARY KEY, section_id INTEGER REFERENCES section(id), name TEXT);")
    conn.execute("CREATE TABLE link (id INTEGER PRIMARY KEY, category_id INTEGER REFERENCES category(id), name TEXT);")
    # Insert link with non-existent category_id 999
    conn.execute("INSERT INTO link (id, category_id, name) VALUES (1, 999, 'Broken link');")
    conn.commit()
    conn.close()

    worker = DatabaseRestoreWorker(MagicMock(), fk_corrupted_db)

    with pytest.raises(ValueError, match="Foreign key integrity check failed"):
        worker._verify_backup_integrity(fk_corrupted_db)


def test_verify_backup_accepts_valid_database(tmp_path: Path) -> None:
    valid_db = tmp_path / "valid.db"
    _build_valid_test_db(valid_db, user_version=7)

    worker = DatabaseRestoreWorker(MagicMock(), valid_db)
    # Should not raise any exceptions
    worker._verify_backup_integrity(valid_db)


def test_verify_backup_rejects_missing_required_columns(tmp_path: Path) -> None:
    # 1. Sphere missing 'name'
    bad_sphere = tmp_path / "bad_sphere.db"
    conn = sqlite3.connect(bad_sphere)
    conn.execute("CREATE TABLE sphere (id INTEGER PRIMARY KEY);")
    conn.execute("CREATE TABLE section (id INTEGER PRIMARY KEY, sphere_id INTEGER, name TEXT);")
    conn.execute("CREATE TABLE category (id INTEGER PRIMARY KEY, section_id INTEGER, name TEXT);")
    conn.execute("CREATE TABLE link (id INTEGER PRIMARY KEY, category_id INTEGER, name TEXT);")
    conn.commit()
    conn.close()

    worker = DatabaseRestoreWorker(MagicMock(), bad_sphere)
    with pytest.raises(ValueError, match="missing required column.*name"):
        worker._verify_backup_integrity(bad_sphere)

    # 2. Link missing 'category_id'
    bad_link = tmp_path / "bad_link.db"
    conn = sqlite3.connect(bad_link)
    conn.execute("CREATE TABLE sphere (id INTEGER PRIMARY KEY, name TEXT);")
    conn.execute("CREATE TABLE section (id INTEGER PRIMARY KEY, sphere_id INTEGER, name TEXT);")
    conn.execute("CREATE TABLE category (id INTEGER PRIMARY KEY, section_id INTEGER, name TEXT);")
    conn.execute("CREATE TABLE link (id INTEGER PRIMARY KEY, name TEXT);")
    conn.commit()
    conn.close()

    worker = DatabaseRestoreWorker(MagicMock(), bad_link)
    with pytest.raises(ValueError, match="missing required column.*category_id"):
        worker._verify_backup_integrity(bad_link)


def test_restore_applies_pending_migrations_on_staging(tmp_path: Path) -> None:
    live_db = tmp_path / "live.db"
    backup_v1 = tmp_path / "backup_v1.db"

    # Create live DB
    conn = sqlite3.connect(live_db)
    conn.execute("CREATE TABLE marker (val TEXT);")
    conn.commit()
    conn.close()

    # Create v1 backup (without browser_key column on link)
    conn = sqlite3.connect(backup_v1)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("CREATE TABLE sphere (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, position INTEGER NOT NULL DEFAULT 0, icon_path TEXT DEFAULT '');")
    conn.execute("CREATE TABLE section (id INTEGER PRIMARY KEY AUTOINCREMENT, sphere_id INTEGER NOT NULL REFERENCES sphere(id) ON DELETE CASCADE, name TEXT NOT NULL, icon_path TEXT DEFAULT '', position INTEGER NOT NULL DEFAULT 0, UNIQUE(sphere_id, name));")
    conn.execute("CREATE TABLE category (id INTEGER PRIMARY KEY AUTOINCREMENT, section_id INTEGER NOT NULL REFERENCES section(id) ON DELETE CASCADE, name TEXT NOT NULL, icon_path TEXT DEFAULT '', position INTEGER NOT NULL DEFAULT 0, UNIQUE(section_id, name));")
    conn.execute("CREATE TABLE link (id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE, name TEXT NOT NULL, url TEXT NOT NULL, type TEXT NOT NULL, notes TEXT DEFAULT '', is_favorite INTEGER NOT NULL DEFAULT 0, last_used TEXT DEFAULT NULL, icon_path TEXT NOT NULL DEFAULT 'default.ico', args TEXT DEFAULT '', position INTEGER NOT NULL DEFAULT 0, UNIQUE(category_id, name, url, args));")
    conn.execute("INSERT INTO sphere (name) VALUES ('Test Sphere');")
    conn.execute("INSERT INTO section (sphere_id, name) VALUES (1, 'Test Section');")
    conn.execute("INSERT INTO category (section_id, name) VALUES (1, 'Test Category');")
    conn.execute("INSERT INTO link (category_id, name, url, type) VALUES (1, 'Test Link', 'https://example.com', 'web');")
    conn.execute("PRAGMA user_version = 1;")
    conn.commit()
    conn.close()

    mock_db = MagicMock()
    worker = DatabaseRestoreWorker(mock_db, backup_v1)

    from unittest.mock import patch

    from app.core.database_manager import DatabaseManager

    with patch.object(DatabaseManager, "get_db_path", return_value=live_db):
        with patch("app.services.database_restore_worker.Database"):
            with patch.object(worker, "_verify_live_database"):
                worker._restore_database(backup_v1)

    # Restored live DB should have user_version upgraded and browser_key column present
    check_conn = sqlite3.connect(live_db)
    ver = check_conn.execute("PRAGMA user_version").fetchone()[0]
    cols = {r[1] for r in check_conn.execute("PRAGMA table_info('link')").fetchall()}
    check_conn.close()

    assert ver >= 7
    assert "browser_key" in cols


def test_restore_aborts_and_keeps_live_db_if_staging_migration_fails(tmp_path: Path) -> None:
    live_db = tmp_path / "live.db"
    backup_db = tmp_path / "backup.db"

    # Create live DB with original marker
    conn = sqlite3.connect(live_db)
    conn.execute("CREATE TABLE original_live (val TEXT);")
    conn.execute("INSERT INTO original_live VALUES ('untouched');")
    conn.commit()
    conn.close()

    # Create backup with valid base schema
    _build_valid_test_db(backup_db, user_version=1)

    mock_db = MagicMock()
    worker = DatabaseRestoreWorker(mock_db, backup_db)

    from unittest.mock import patch

    from app.core.database_manager import DatabaseManager

    with patch.object(DatabaseManager, "get_db_path", return_value=live_db):
        with patch.object(worker, "_migrate_and_validate_staged_database", side_effect=ValueError("Migration syntax error")):
            with pytest.raises(ValueError, match="Migration syntax error"):
                worker._restore_database(backup_db)

    # Live DB must remain intact
    conn = sqlite3.connect(live_db)
    row = conn.execute("SELECT val FROM original_live").fetchone()
    conn.close()
    assert row is not None and row[0] == "untouched"

    # Temporary staging files must not exist
    tmp_target = live_db.with_name(f"{live_db.name}.restore_tmp")
    orig_backup = live_db.with_name(f"{live_db.name}.orig_bak")
    assert not tmp_target.exists()
    assert not orig_backup.exists()


def test_restore_rolls_back_if_live_db_verification_fails(tmp_path: Path) -> None:
    live_db = tmp_path / "live.db"
    backup_db = tmp_path / "backup.db"

    # Create live DB
    conn = sqlite3.connect(live_db)
    conn.execute("CREATE TABLE original_live (val TEXT);")
    conn.execute("INSERT INTO original_live VALUES ('must_be_restored');")
    conn.commit()
    conn.close()

    # Create backup with full valid schema
    conn = sqlite3.connect(backup_db)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("CREATE TABLE sphere (id INTEGER PRIMARY KEY, name TEXT, position INTEGER DEFAULT 0, icon_path TEXT DEFAULT '');")
    conn.execute("CREATE TABLE section (id INTEGER PRIMARY KEY, sphere_id INTEGER REFERENCES sphere(id), name TEXT, position INTEGER DEFAULT 0, icon_path TEXT DEFAULT '');")
    conn.execute("CREATE TABLE category (id INTEGER PRIMARY KEY, section_id INTEGER REFERENCES section(id), name TEXT, position INTEGER DEFAULT 0, icon_path TEXT DEFAULT '');")
    conn.execute("CREATE TABLE link (id INTEGER PRIMARY KEY, category_id INTEGER REFERENCES category(id), name TEXT, url TEXT DEFAULT '', type TEXT DEFAULT 'web', position INTEGER DEFAULT 0, icon_path TEXT DEFAULT '', is_favorite INTEGER DEFAULT 0, browser_key TEXT DEFAULT NULL);")
    conn.execute("PRAGMA user_version = 7;")
    conn.commit()
    conn.close()

    mock_db = MagicMock()
    worker = DatabaseRestoreWorker(mock_db, backup_db)

    from unittest.mock import patch

    from app.core.database_manager import DatabaseManager

    with patch.object(DatabaseManager, "get_db_path", return_value=live_db):
        with patch("app.services.database_restore_worker.Database"):
            with patch.object(worker, "_verify_live_database", side_effect=RuntimeError("Corrupt index on live query")):
                with pytest.raises(ValueError) as exc_info:
                    worker._restore_database(backup_db)
                assert "Corrupt index on live query" in str(exc_info.value)

    # Live DB must have been rolled back from orig_backup!
    conn = sqlite3.connect(live_db)
    row = conn.execute("SELECT val FROM original_live").fetchone()
    conn.close()
    assert row is not None and row[0] == "must_be_restored"

    # Temporary and backup artifacts cleaned up
    tmp_target = live_db.with_name(f"{live_db.name}.restore_tmp")
    orig_backup = live_db.with_name(f"{live_db.name}.orig_bak")
    assert not tmp_target.exists()
    assert not orig_backup.exists()
