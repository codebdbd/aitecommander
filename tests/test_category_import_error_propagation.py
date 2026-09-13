from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.models.base.db_base import DatabaseError
from app.models.db import Database
from app.models.managers.import_export_manager import ImportExportManager


import contextlib


class DummyDb:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    @contextlib.contextmanager
    def transaction(self):
        self.connection.execute("SAVEPOINT test_tx")
        try:
            yield
            self.connection.execute("RELEASE SAVEPOINT test_tx")
        except Exception:
            self.connection.execute("ROLLBACK TO SAVEPOINT test_tx")
            raise

    def backup_async(self, **kwargs):
        pass


@pytest.fixture
def test_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema = Path("app/models/schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.execute("INSERT INTO sphere (id, name) VALUES (1, 'Sphere 1');")
    conn.execute("INSERT INTO section (id, sphere_id, name) VALUES (1, 1, 'Section 1');")
    conn.commit()

    db = DummyDb(conn)
    yield db
    conn.close()


def test_import_category_tree_propagates_link_insertion_error(test_db) -> None:
    manager = ImportExportManager(test_db)

    # Category tree with duplicate links that violate UNIQUE(category_id, name, url, args)
    tree = {
        "category": {
            "name": "Corrupted Category",
            "section_id": 1,
            "position": 0,
        },
        "links": [
            {
                "name": "Duplicate Link",
                "url": "https://example.com",
                "args": "--param",
                "type": "web",
            },
            {
                "name": "Duplicate Link",
                "url": "https://example.com",
                "args": "--param",
                "type": "web",
            },
        ],
    }

    # Must NOT silently swallow error; must raise DatabaseError
    with pytest.raises(DatabaseError, match="Failed to insert link 'Duplicate Link'"):
        manager.import_category_tree(tree)

    # Must rollback the entire transaction: category must not exist
    conn = test_db.connection
    cat = conn.execute("SELECT * FROM category WHERE name = 'Corrupted Category'").fetchone()
    assert cat is None, "Category should be rolled back after link insertion failure"

    links = conn.execute("SELECT * FROM link WHERE name = 'Duplicate Link'").fetchall()
    assert len(links) == 0, "Duplicate links should be rolled back"


def test_import_category_trees_bulk_rolls_back_on_error(test_db) -> None:
    manager = ImportExportManager(test_db)

    trees = [
        {
            "category": {"name": "Good Cat", "section_id": 1, "position": 0},
            "links": [{"name": "Good Link", "url": "https://ok.com", "type": "web"}],
        },
        {
            "category": {"name": "Bad Cat", "section_id": 1, "position": 1},
            "links": [
                {"name": "Dupe", "url": "https://bad.com", "args": "", "type": "web"},
                {"name": "Dupe", "url": "https://bad.com", "args": "", "type": "web"},
            ],
        },
    ]

    with pytest.raises(DatabaseError, match="Failed to import category trees"):
        manager.import_category_trees_bulk(trees)

    # Whole batch must be rolled back
    conn = test_db.connection
    cats = conn.execute("SELECT * FROM category WHERE name IN ('Good Cat', 'Bad Cat')").fetchall()
    assert len(cats) == 0, "Bulk import transaction must be rolled back completely"


def test_import_category_tree_success(test_db) -> None:
    manager = ImportExportManager(test_db)

    tree = {
        "category": {"name": "Valid Cat", "section_id": 1, "position": 0},
        "links": [
            {"name": "Link 1", "url": "https://a.com", "args": "", "type": "web"},
            {"name": "Link 2", "url": "https://b.com", "args": "", "type": "web"},
        ],
    }

    manager.import_category_tree(tree)

    conn = test_db.connection
    cat = conn.execute("SELECT * FROM category WHERE name = 'Valid Cat'").fetchone()
    assert cat is not None
    links = conn.execute("SELECT * FROM link WHERE category_id = ?", (cat["id"],)).fetchall()
    assert len(links) == 2
