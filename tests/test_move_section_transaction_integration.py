"""Integration tests verifying that moving sections between spheres immediately back and forth
does not fail with 'cannot start a transaction within a transaction'.
"""

from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import Mock

from app.models.entities.section_model import SectionModel
from app.utils.ui.dnd.section_command import MoveSectionToSphereCommand


class _ConnectionManager:
    """Mock connection manager matching Database interface."""

    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self._transaction_state = None


class TestMoveSectionTransactionIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.cm = _ConnectionManager()
        self.conn = self.cm.connection
        self.conn.executescript(
            """
            CREATE TABLE sphere (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                icon_path TEXT NOT NULL DEFAULT ''
            );
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
            CREATE TABLE link (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                icon_path TEXT NOT NULL DEFAULT ''
            );
            """
        )
        self.conn.executemany(
            "INSERT INTO sphere (id, name, position) VALUES (?, ?, ?)",
            [(1, "Sphere 1", 0), (2, "Sphere 2", 1)],
        )
        self.conn.executemany(
            "INSERT INTO section (id, name, sphere_id, position, icon_path) VALUES (?, ?, ?, ?, ?)",
            [
                (10, "Section A", 1, 0, ""),
                (11, "Section B", 1, 1, ""),
                (20, "Section X", 2, 0, ""),
            ],
        )
        self.conn.commit()

        # Build mock Database that delegates to SectionModel and Base
        self.section_model = SectionModel(self.cm)
        self.cm._base = self.section_model

        self.mock_db = Mock()
        self.mock_db.connection = self.conn
        self.mock_db.transaction = self.section_model.transaction
        self.mock_db.sections = self.section_model
        self.mock_db.spheres = Mock()
        self.mock_db.categories = Mock()
        self.mock_db.categories.get_categories.return_value = []
        self.mock_db.links = Mock()

    def tearDown(self) -> None:
        self.conn.close()

    def test_reindex_positions_commits_and_clears_in_transaction(self) -> None:
        """Verify _reindex_positions does not leave connection in an uncommitted transaction."""
        self.assertFalse(self.conn.in_transaction)

        # Call _reindex_positions
        self.section_model._reindex_positions("section", "sphere_id", 1)

        # in_transaction MUST be False after reindexing
        self.assertFalse(
            self.conn.in_transaction,
            "Connection was left in open transaction after _reindex_positions",
        )

        # Immediate subsequent transaction should succeed without error
        with self.section_model.transaction():
            self.conn.execute(
                "UPDATE section SET name = 'Updated' WHERE id = 10"
            )

        self.assertFalse(self.conn.in_transaction)

    def test_transaction_recovers_if_in_transaction_was_already_set(self) -> None:
        """Verify DatabaseBase.transaction commits pending transaction instead of crashing."""
        # Intentionally execute DML without committing to simulate dirty state
        self.conn.execute("UPDATE section SET position = 99 WHERE id = 10")
        self.assertTrue(self.conn.in_transaction)

        # Starting a transaction should NOT crash with "cannot start a transaction within a transaction"
        with self.section_model.transaction():
            self.conn.execute("UPDATE section SET position = 42 WHERE id = 10")

        self.assertFalse(self.conn.in_transaction)
        row = self.conn.execute("SELECT position FROM section WHERE id = 10").fetchone()
        self.assertEqual(row["position"], 42)

    def test_immediate_move_section_and_move_back_scenario(self) -> None:
        """Simulate user dragging a section to another sphere and immediately dragging it back."""
        # Setup mock structure_business
        sb = Mock()
        sb.structure_service = Mock()
        sb.structure_service.db = self.mock_db

        def mock_get_section_data(section_id: int):
            row = self.conn.execute(
                "SELECT id, name, sphere_id, position, icon_path FROM section WHERE id = ?",
                (section_id,),
            ).fetchone()
            return dict(row) if row else None

        def mock_get_sections(sphere_id: int):
            rows = self.conn.execute(
                "SELECT id, name, sphere_id, position, icon_path FROM section WHERE id = ?",
                (sphere_id,),
            ).fetchall()
            return [dict(r) for r in rows]

        def mock_has_duplicate_section(sphere_id: int, name: str, exclude_id: int = None):
            return False

        def mock_update_section(section_id: int, data: dict):
            with self.section_model.transaction():
                self.conn.execute(
                    "UPDATE section SET name = ?, sphere_id = ?, position = ?, icon_path = ? WHERE id = ?",
                    (
                        data["name"],
                        data["sphere_id"],
                        data.get("position", 0),
                        data.get("icon_path", ""),
                        section_id,
                    ),
                )
            return {"id": section_id, **data}

        sb.get_section_data.side_effect = mock_get_section_data
        sb.get_sections.side_effect = mock_get_sections
        sb.has_duplicate_section.side_effect = mock_has_duplicate_section
        sb.update_section.side_effect = mock_update_section
        sb.cache_service = Mock()

        main_window = Mock()
        main_window.structure_business = sb
        main_window.structure = Mock()

        # Step 1: Move Section 10 from Sphere 1 to Sphere 2
        cmd1 = MoveSectionToSphereCommand(10, 2, main_window)
        success1 = cmd1._execute_operation()
        self.assertTrue(success1)
        self.assertFalse(
            self.conn.in_transaction,
            "Connection left in transaction after first move",
        )

        row_after_move = self.conn.execute(
            "SELECT sphere_id FROM section WHERE id = 10"
        ).fetchone()
        self.assertEqual(row_after_move["sphere_id"], 2)

        # Step 2: User IMMEDIATELY moves Section 10 back from Sphere 2 to Sphere 1
        # Before the fix, this raised "sqlite3.OperationalError: cannot start a transaction within a transaction"
        cmd2 = MoveSectionToSphereCommand(10, 1, main_window)
        success2 = cmd2._execute_operation()
        self.assertTrue(success2)
        self.assertFalse(
            self.conn.in_transaction,
            "Connection left in transaction after move back",
        )

        row_after_move_back = self.conn.execute(
            "SELECT sphere_id FROM section WHERE id = 10"
        ).fetchone()
        self.assertEqual(row_after_move_back["sphere_id"], 1)

        # Step 3: Immediately move again
        cmd3 = MoveSectionToSphereCommand(10, 2, main_window)
        success3 = cmd3._execute_operation()
        self.assertTrue(success3)
        self.assertFalse(self.conn.in_transaction)
