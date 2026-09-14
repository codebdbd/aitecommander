from __future__ import annotations

import shutil
import sqlite3
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from conftest import build_test_temp_path

from app.controllers.ui.dialogs.database_controller import DatabaseController
from app.core.database_manager import DatabaseManager
from app.utils.db.synchronization import db_lock


class TestDatabaseMaintenanceMode(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = build_test_temp_path("manual_tmp", f"database_maintenance_{id(self)}")
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(self.temp_dir) / "test.db"
        DatabaseManager.configure(self.db_path)

    def tearDown(self) -> None:
        DatabaseManager.close_all()
        DatabaseManager.configure(None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_maintenance_scope_blocks_connections(self) -> None:
        self.assertFalse(DatabaseManager.is_in_maintenance())

        with DatabaseManager.maintenance_scope():
            self.assertTrue(DatabaseManager.is_in_maintenance())
            with self.assertRaises(RuntimeError) as ctx:
                DatabaseManager.get_connection()
            self.assertIn("maintenance mode", str(ctx.exception))

        self.assertFalse(DatabaseManager.is_in_maintenance())

    def test_maintenance_scope_waits_for_active_transaction(self) -> None:
        """Verify that maintenance_scope waits for in-flight transaction to finish."""
        tx_started = threading.Event()
        tx_completed = False

        def worker_tx():
            nonlocal tx_completed
            with DatabaseManager.transaction():
                tx_started.set()
                time.sleep(0.15)
                tx_completed = True

        thread = threading.Thread(target=worker_tx)
        thread.start()

        self.assertTrue(tx_started.wait(timeout=2.0))

        # Entering maintenance must wait for worker_tx to finish
        with DatabaseManager.maintenance_scope(timeout=5.0):
            self.assertTrue(
                tx_completed,
                "maintenance_scope did not wait for active transaction to complete",
            )

        thread.join(timeout=2.0)
        self.assertFalse(thread.is_alive())

    def test_maintenance_scope_times_out_on_hung_transaction(self) -> None:
        """Verify that maintenance_scope times out if a transaction never finishes."""
        acquired_event = threading.Event()
        release_event = threading.Event()

        def hung_worker():
            with db_lock:
                acquired_event.set()
                release_event.wait(timeout=2.0)

        thread = threading.Thread(target=hung_worker)
        thread.start()

        self.assertTrue(acquired_event.wait(timeout=2.0))
        try:
            with self.assertRaises(TimeoutError):
                with DatabaseManager.maintenance_scope(timeout=0.1):
                    pass
        finally:
            release_event.set()
            thread.join(timeout=2.0)

    def test_close_all_rolls_back_uncommitted_work_without_committing(self) -> None:
        """Verify that close_all rolls back uncommitted changes instead of committing them."""
        # Initialize schema with a simple table
        conn = DatabaseManager.get_connection()
        conn.execute("CREATE TABLE test_items (id INTEGER PRIMARY KEY, name TEXT)")
        conn.commit()

        # Start an explicit uncommitted transaction on the connection
        conn.execute("BEGIN")
        conn.execute("INSERT INTO test_items (name) VALUES ('uncommitted_item')")
        self.assertTrue(conn.in_transaction)

        # Call close_all - this should roll back, not commit
        DatabaseManager.close_all()

        # Reopen and check that uncommitted_item was NOT saved
        verify_conn = sqlite3.connect(self.db_path)
        rows = verify_conn.execute(
            "SELECT * FROM test_items WHERE name = 'uncommitted_item'"
        ).fetchall()
        verify_conn.close()

        self.assertEqual(len(rows), 0, "Uncommitted work was committed by close_all!")

    def test_database_controller_prevents_concurrent_restore(self) -> None:
        controller = DatabaseController(MagicMock())
        controller._is_restoring = True
        controller._emit_error = MagicMock()

        controller.handle_restore_database()

        controller._emit_error.assert_called_once()
        self.assertTrue(bool(controller._emit_error.call_args[0][0]))
