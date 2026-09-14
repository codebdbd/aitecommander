"""Integration test for database restore lifecycle and dependency wiring."""

import unittest
from unittest.mock import MagicMock

from app.controllers.system.window_setup.wiring import DatabaseEventHandler


class TestDatabaseRestoreLifecycle(unittest.TestCase):
    """Verify that DB restoration updates bulk dependencies and clears the undo stack."""

    def test_handle_database_restored_clears_undo_stack(self) -> None:
        """Verify window.undo_stack.clear is called on restore."""
        window = MagicMock()
        new_db = MagicMock()
        window.undo_stack = MagicMock()

        DatabaseEventHandler.handle_database_restored(window, new_db)

        window.undo_stack.clear.assert_called_once()

    def test_handle_database_connected_clears_undo_stack(self) -> None:
        """Verify window.undo_stack.clear is called on connect."""
        window = MagicMock()
        new_db = MagicMock()
        window.undo_stack = MagicMock()

        DatabaseEventHandler.handle_database_connected(window, new_db)

        window.undo_stack.clear.assert_called_once()

    def test_update_business_logic_wires_bulk_service_db(self) -> None:
        """Verify that structure_service._bulk.db receives new_db reference."""
        window = MagicMock()
        new_db = MagicMock()
        sb = MagicMock()
        window.structure_business = sb
        sb.structure_service = MagicMock()
        sb.structure_service._bulk = MagicMock()

        DatabaseEventHandler._update_business_logic(window, new_db)

        self.assertIs(sb.structure_service._bulk.db, new_db)
        self.assertIs(sb.structure_service.db, new_db)
