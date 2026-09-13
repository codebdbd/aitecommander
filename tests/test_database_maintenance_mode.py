from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.core.database_manager import DatabaseManager
from app.controllers.ui.dialogs.database_controller import DatabaseController


class TestDatabaseMaintenanceMode(unittest.TestCase):
    def test_maintenance_scope_blocks_connections(self) -> None:
        self.assertFalse(DatabaseManager.is_in_maintenance())

        with DatabaseManager.maintenance_scope():
            self.assertTrue(DatabaseManager.is_in_maintenance())
            with self.assertRaises(RuntimeError) as ctx:
                DatabaseManager.get_connection()
            self.assertIn("maintenance mode", str(ctx.exception))

        self.assertFalse(DatabaseManager.is_in_maintenance())

    def test_database_controller_prevents_concurrent_restore(self) -> None:
        controller = DatabaseController(MagicMock())
        controller._is_restoring = True
        controller._emit_error = MagicMock()

        controller.handle_restore_database()

        controller._emit_error.assert_called_once()
        self.assertTrue(bool(controller._emit_error.call_args[0][0]))
