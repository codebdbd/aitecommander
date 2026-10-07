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

    def test_database_restore_worker_locked_wal_error_formatting(self) -> None:
        """Verify _build_locked_wal_error includes locking process info when present."""
        from unittest.mock import patch
        from app.services.database_restore_worker import DatabaseRestoreWorker

        worker = DatabaseRestoreWorker(MagicMock(), "dummy.db")
        with patch.object(
            worker,
            "_get_locking_processes_info",
            return_value=["python.exe (PID 9999)"],
        ):
            err = worker._build_locked_wal_error("links.db-wal")
            self.assertIn("links.db-wal [python.exe (PID 9999)]", str(err))

    def test_database_controller_conflict_resolution_retry(self) -> None:
        """Verify DatabaseController prompts user and retries restore when conflicting process is found."""
        from unittest.mock import patch
        from app.controllers.ui.dialogs.database_controller import DatabaseController

        db_mock = MagicMock()
        controller = DatabaseController(db_mock)
        controller._last_restore_backup_path = "backup.db"

        with (
            patch.object(
                controller.dialogs,
                "confirm_terminate_locking_process",
                return_value=True,
            ) as mock_confirm,
            patch.object(
                controller,
                "_terminate_process_and_retry_restore",
            ) as mock_terminate,
        ):
            error_msg = "Cannot restore database: WAL file links.db-wal [Python (PID 99999)] is locked."
            controller._on_restore_error(error_msg)

            mock_confirm.assert_called_once_with("Python (PID 99999)")
            mock_terminate.assert_called_once_with(99999)
