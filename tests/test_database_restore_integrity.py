from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.services.database_restore_worker import DatabaseRestoreWorker, REQUIRED_TABLES


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
