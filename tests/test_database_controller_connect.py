from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from app.controllers.ui.dialogs.database_controller import DatabaseController
from app.core.database_manager import DatabaseManager
from app.services.database_restore_worker import DatabaseRestoreWorker


def _create_valid_database(db_path: Path, *, wal_mode: bool = False) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        if wal_mode:
            conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE sphere (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                position INTEGER DEFAULT 0,
                icon_path TEXT
            );
            CREATE TABLE section (
                id INTEGER PRIMARY KEY,
                sphere_id INTEGER NOT NULL REFERENCES sphere(id),
                name TEXT NOT NULL,
                position INTEGER DEFAULT 0,
                icon_path TEXT
            );
            CREATE TABLE category (
                id INTEGER PRIMARY KEY,
                section_id INTEGER NOT NULL REFERENCES section(id),
                name TEXT NOT NULL,
                position INTEGER DEFAULT 0,
                icon_path TEXT
            );
            CREATE TABLE link (
                id INTEGER PRIMARY KEY,
                category_id INTEGER NOT NULL REFERENCES category(id),
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                args TEXT,
                type TEXT DEFAULT 'web',
                browser_key TEXT,
                icon_path TEXT,
                position INTEGER DEFAULT 0,
                notes TEXT,
                is_favorite INTEGER DEFAULT 0,
                last_used TEXT
            );
            INSERT INTO sphere (id, name) VALUES (1, 'Main Sphere');
            INSERT INTO section (id, sphere_id, name) VALUES (1, 1, 'Main Section');
            INSERT INTO category (id, section_id, name) VALUES (1, 1, 'Main Cat');
            INSERT INTO link (id, category_id, name, url) VALUES (1, 1, 'Test Link', 'https://example.com');
            PRAGMA user_version = 1;
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_connect_database_rejects_when_already_restoring() -> None:
    controller = DatabaseController(MagicMock())
    controller._is_restoring = True
    controller._emit_error = MagicMock()
    controller.dialogs = MagicMock()

    controller.handle_connect_database()

    controller._emit_error.assert_called_once()
    controller.dialogs.get_connect_file.assert_not_called()


def test_connect_database_rejects_invalid_file(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.txt"
    bad_file.write_text("not a database file", encoding="utf-8")

    db_mock = MagicMock()
    db_mock.close_all = MagicMock()
    controller = DatabaseController(db_mock)
    controller._emit_error = MagicMock()
    controller.database_connected = MagicMock()

    # Synchronously run worker for bad_file
    worker = DatabaseRestoreWorker(db_mock, bad_file)
    error_called = False

    def on_error(err_msg: str):
        nonlocal error_called
        error_called = True
        controller._on_connect_error(err_msg)

    worker.signals.error.connect(on_error)
    worker.run()

    assert error_called
    controller._emit_error.assert_called_once()
    controller.database_connected.emit.assert_not_called()
    assert controller._is_restoring is False


def test_connect_database_rejects_missing_required_tables(tmp_path: Path) -> None:
    incomplete_db = tmp_path / "incomplete.db"
    conn = sqlite3.connect(str(incomplete_db))
    conn.execute("CREATE TABLE other_table (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    db_mock = MagicMock()
    db_mock.close_all = MagicMock()
    controller = DatabaseController(db_mock)
    controller._emit_error = MagicMock()
    controller.database_connected = MagicMock()

    worker = DatabaseRestoreWorker(db_mock, incomplete_db)
    error_called = False

    def on_error(err_msg: str):
        nonlocal error_called
        error_called = True
        controller._on_connect_error(err_msg)

    worker.signals.error.connect(on_error)
    worker.run()

    assert error_called
    controller._emit_error.assert_called_once()
    controller.database_connected.emit.assert_not_called()
    assert controller._is_restoring is False


def test_connect_database_success_with_wal_source(tmp_path: Path) -> None:
    live_dir = tmp_path / "app_data"
    live_dir.mkdir()
    live_db_path = live_dir / "links.db"
    DatabaseManager.configure(live_db_path)

    # Initial live database
    _create_valid_database(live_db_path)

    # External source database with WAL mode
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    external_db_path = external_dir / "external.db"
    _create_valid_database(external_db_path, wal_mode=True)

    # Add extra record into external WAL DB
    ext_conn = sqlite3.connect(str(external_db_path))
    ext_conn.execute("INSERT INTO sphere (id, name) VALUES (2, 'External Sphere')")
    ext_conn.commit()
    # Keep ext_conn open or closed - WAL file exists
    ext_conn.close()

    db_mock = MagicMock()
    db_mock.close_all = MagicMock(side_effect=DatabaseManager.close_all)

    controller = DatabaseController(db_mock)
    controller._emit_success = MagicMock()
    connected_db = None

    def on_connected(new_db):
        nonlocal connected_db
        connected_db = new_db

    controller.database_connected.connect(on_connected)

    worker = DatabaseRestoreWorker(db_mock, external_db_path)
    worker.signals.success.connect(controller._on_connect_success)
    worker.signals.error.connect(controller._on_connect_error)
    worker.run()

    assert connected_db is not None
    controller._emit_success.assert_called_once()
    assert controller._is_restoring is False

    # Verify that data from external WAL database was completely transferred
    verify_conn = sqlite3.connect(str(live_db_path))
    rows = verify_conn.execute("SELECT name FROM sphere ORDER BY id").fetchall()
    verify_conn.close()

    sphere_names = [r[0] for r in rows]
    assert "Main Sphere" in sphere_names
    assert "External Sphere" in sphere_names

    DatabaseManager.close_all()
    DatabaseManager.configure(None)
