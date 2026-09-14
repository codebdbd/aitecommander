import importlib
import logging
import sqlite3

import pytest

migrate_mod = importlib.import_module("app.models.migrations.0003_change_link_unique")
migrate = migrate_mod.migrate


def test_migration_0003_preserves_duplicate_links_by_renaming() -> None:
    logger = logging.getLogger("test_migration_0003")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Setup base schema with old unique index: UNIQUE(category_id, url, args, type)
    conn.executescript(
        """
        CREATE TABLE sphere (id INTEGER PRIMARY KEY, name TEXT UNIQUE);
        INSERT INTO sphere (id, name) VALUES (1, 'Main');
        CREATE TABLE section (id INTEGER PRIMARY KEY, sphere_id INTEGER, name TEXT);
        INSERT INTO section (id, sphere_id, name) VALUES (1, 1, 'Sec');
        CREATE TABLE category (id INTEGER PRIMARY KEY, section_id INTEGER, name TEXT);
        INSERT INTO category (id, section_id, name) VALUES (1, 1, 'Cat');

        CREATE TABLE link (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id  INTEGER NOT NULL,
            name         TEXT    NOT NULL,
            url          TEXT    NOT NULL,
            type         TEXT    NOT NULL,
            notes        TEXT    DEFAULT '',
            is_favorite  INTEGER DEFAULT 0,
            last_used    TEXT    DEFAULT NULL,
            icon_path    TEXT    DEFAULT 'default.ico',
            args         TEXT    DEFAULT '',
            browser_key  TEXT    DEFAULT NULL,
            position     INTEGER DEFAULT 0,
            UNIQUE(category_id, url, args, type)
        );
        """
    )

    # Insert two links with the same (category_id, name, url, args) but different type
    conn.execute(
        """
        INSERT INTO link (id, category_id, name, url, type, notes, is_favorite, args)
        VALUES (10, 1, 'Python Launcher', 'C:\\Python\\py.exe', 'program', 'Note 1', 1, '--version')
        """
    )
    conn.execute(
        """
        INSERT INTO link (id, category_id, name, url, type, notes, is_favorite, args)
        VALUES (20, 1, 'Python Launcher', 'C:\\Python\\py.exe', 'file', 'Note 2', 0, '--version')
        """
    )
    # Insert third link without conflicts
    conn.execute(
        """
        INSERT INTO link (id, category_id, name, url, type, notes, is_favorite, args)
        VALUES (30, 1, 'Google', 'https://google.com', 'web', 'Search', 1, '')
        """
    )
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM link").fetchone()[0] == 3

    # Run migration 0003
    migrate(conn, logger)

    # Verify that all 3 rows are preserved (NO rows were dropped or ignored)
    rows = conn.execute("SELECT id, name, type, notes FROM link ORDER BY id ASC").fetchall()
    assert len(rows) == 3

    # First link keeps original name
    assert rows[0]["id"] == 10
    assert rows[0]["name"] == "Python Launcher"
    assert rows[0]["notes"] == "Note 1"

    # Second link is safely renamed with its type
    assert rows[1]["id"] == 20
    assert rows[1]["name"] == "Python Launcher (file)"
    assert rows[1]["notes"] == "Note 2"

    # Third link is untouched
    assert rows[2]["id"] == 30
    assert rows[2]["name"] == "Google"

    # Verify that new table has UNIQUE(category_id, name, url, args)
    # Attempting to insert duplicate should raise IntegrityError now
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO link (category_id, name, url, type, args)
            VALUES (1, 'Google', 'https://google.com', 'web', '')
            """
        )
