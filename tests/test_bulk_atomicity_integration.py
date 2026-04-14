"""Integration test for transactional rollback in bulk category move."""

from __future__ import annotations

import sqlite3
import unittest

from app.models.entities.category_model import CategoryModel


class _ConnectionManager:
    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row


class TestBulkAtomicityIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.cm = _ConnectionManager()
        conn = self.cm.connection
        conn.executescript(
            """
            CREATE TABLE section (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                sphere_id INTEGER NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                icon_path TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE category (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                section_id INTEGER NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                icon_path TEXT NOT NULL DEFAULT ''
            );
            """
        )
        conn.executemany(
            "INSERT INTO section (id, name, sphere_id, position, icon_path) VALUES (?, ?, ?, ?, ?)",
            [
                (1, "S1", 1, 0, ""),
                (2, "S2", 1, 1, ""),
            ],
        )
        conn.executemany(
            "INSERT INTO category (id, name, section_id, position, icon_path) VALUES (?, ?, ?, ?, ?)",
            [
                (10, "A", 1, 0, ""),
                (11, "B", 1, 1, ""),
            ],
        )
        conn.commit()

    def tearDown(self) -> None:
        self.cm.connection.close()

    def test_bulk_move_rolls_back_on_failure_after_sql_execution(self) -> None:
        model = CategoryModel(self.cm)
        original_exec_many = model._execute_many_with_error_handling

        def _flaky_exec_many(query, params):
            cursor = original_exec_many(query, params)
            raise RuntimeError("forced failure after SQL write")
            return cursor

        model._execute_many_with_error_handling = _flaky_exec_many  # type: ignore[method-assign]

        with self.assertRaises(RuntimeError):
            model.move_categories_to_section_bulk([10, 11], target_section_id=2, base_row=0)

        rows = self.cm.connection.execute(
            "SELECT id, section_id, position FROM category ORDER BY id"
        ).fetchall()
        self.assertEqual([(r["id"], r["section_id"], r["position"]) for r in rows], [(10, 1, 0), (11, 1, 1)])


if __name__ == "__main__":
    unittest.main()
