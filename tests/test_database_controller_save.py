from __future__ import annotations

import shutil
import sqlite3
import unittest
from types import SimpleNamespace

from conftest import build_test_temp_path

from app.controllers.ui.dialogs.database_controller import DatabaseController


class TestDatabaseControllerSave(unittest.TestCase):
    def test_save_database_copy_creates_consistent_sqlite_backup(self, tmp_path=None) -> None:
        temp_path = build_test_temp_path("manual_tmp", "database_controller_save")
        shutil.rmtree(temp_path, ignore_errors=True)
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            source_db = temp_path / "source.db"
            dest_db = temp_path / "saved_copy.db"

            # Create source SQLite database with WAL enabled
            conn = sqlite3.connect(str(source_db))
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("CREATE TABLE test_items (id INTEGER PRIMARY KEY, val TEXT)")
            conn.execute("INSERT INTO test_items (val) VALUES ('item1'), ('item2')")
            conn.commit()

            # Mock db object with connection attribute
            fake_db = SimpleNamespace(connection=conn, db_path=str(source_db))
            controller = DatabaseController(fake_db)

            controller._save_database_copy(str(source_db), str(dest_db))

            # Verify saved copy exists and contains the committed WAL data
            self.assertTrue(dest_db.exists())
            check_conn = sqlite3.connect(str(dest_db))
            rows = check_conn.execute("SELECT val FROM test_items ORDER BY id").fetchall()
            check_conn.close()
            conn.close()

            self.assertEqual([r[0] for r in rows], ["item1", "item2"])
        finally:
            shutil.rmtree(temp_path, ignore_errors=True)
