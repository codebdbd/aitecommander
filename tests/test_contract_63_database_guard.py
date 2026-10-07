"""Tests for Contract §63: Database Single-Instance Guard & Restore Conflict Resolution."""

import unittest
from unittest.mock import MagicMock, patch

from app.controllers.ui.dialogs.database_controller import DatabaseController
from app.services.database_restore_worker import DatabaseRestoreWorker
from app.startup.initializer import StartupMode
from app.startup.runtime import ExitCode, StartupOptions, run


class TestContract63DatabaseGuard(unittest.TestCase):
    """Verify guarantees of Contract §63."""

    def test_pragma_execution_order_in_restore_worker(self) -> None:
        """Rule §63.Restore.1: wal_checkpoint(TRUNCATE) must be called BEFORE journal_mode = DELETE."""
        worker = DatabaseRestoreWorker(MagicMock(), "test.db")
        conn_mock = MagicMock()
        executed_statements = []

        def track_execute(sql: str, *args, **kwargs):
            executed_statements.append(sql.strip())
            return MagicMock()

        conn_mock.execute.side_effect = track_execute

        with patch.object(worker, "_open_sqlite_connection", return_value=conn_mock):
            worker._switch_journal_mode_for_restore("test.db")

        self.assertIn("PRAGMA wal_checkpoint(TRUNCATE)", executed_statements)
        self.assertIn("PRAGMA journal_mode = DELETE", executed_statements)

        checkpoint_idx = executed_statements.index("PRAGMA wal_checkpoint(TRUNCATE)")
        delete_mode_idx = executed_statements.index("PRAGMA journal_mode = DELETE")

        self.assertLess(
            checkpoint_idx,
            delete_mode_idx,
            "wal_checkpoint(TRUNCATE) must precede journal_mode = DELETE",
        )

    def test_restore_retry_count_prevents_infinite_loop(self) -> None:
        """Rule §63.Restore.3: Retry limit must prevent infinite dialog loops on persistent locks."""
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
            patch.object(controller, "_emit_error") as mock_emit_error,
        ):
            error_msg = "Cannot restore database: WAL file links.db-wal [Python (PID 12345)] is locked."

            # First error: prompts user and initiates retry
            controller._on_restore_error(error_msg)
            self.assertEqual(controller._restore_retry_count, 1)
            mock_confirm.assert_called_once()
            mock_terminate.assert_called_once()

            # Second error for the same restore: must NOT prompt again, must emit error
            controller._on_restore_error(error_msg)
            self.assertEqual(controller._restore_retry_count, 0)
            self.assertEqual(mock_confirm.call_count, 1)
            mock_emit_error.assert_called_once()

    def test_headless_exits_immediately_without_tasks(self) -> None:
        """Rule §63.Headless.2: Headless mode without tasks must exit cleanly without hanging."""
        opts = StartupOptions(mode=StartupMode.HEADLESS, auto_quit=False)

        with (
            patch("app.startup.runtime.parse_arguments") as mock_parse,
            patch("app.startup.runtime.SingleInstanceGuard") as mock_guard_cls,
            patch("app.startup.runtime.ApplicationInitializer") as mock_init_cls,
            patch("app.startup.runtime._initialize_database_and_profiles"),
            patch("app.startup.runtime._create_qt_application") as mock_app_cls,
        ):
            mock_args = MagicMock()
            mock_args.file = None
            mock_args.no_gui = True
            mock_args.log_level = "INFO"
            mock_args.verbose = False
            mock_args.quiet = False
            mock_args.debug = False
            mock_parse.return_value = mock_args

            guard_inst = MagicMock()
            guard_inst.acquire.return_value = True
            mock_guard_cls.return_value = guard_inst

            init_inst = MagicMock()
            init_inst.initialize_all.return_value = True
            mock_init_cls.return_value = init_inst

            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app

            exit_code = run(opts)

            self.assertEqual(exit_code, ExitCode.SUCCESS)
            mock_app.exec.assert_not_called()

    def test_single_instance_guard_blocks_concurrent_headless_instance(self) -> None:
        """Rule §63.Headless.1: Second instance must exit cleanly with SUCCESS if guard is held."""
        opts = StartupOptions(mode=StartupMode.HEADLESS, auto_quit=False)

        with (
            patch("app.startup.runtime.parse_arguments") as mock_parse,
            patch("app.startup.runtime.SingleInstanceGuard") as mock_guard_cls,
            patch("app.startup.runtime._create_qt_application") as mock_app_cls,
        ):
            mock_args = MagicMock()
            mock_args.file = None
            mock_args.log_level = "INFO"
            mock_args.verbose = False
            mock_args.quiet = False
            mock_args.debug = False
            mock_parse.return_value = mock_args

            guard_inst = MagicMock()
            # Guard reports another instance already holds the socket
            guard_inst.acquire.return_value = False
            mock_guard_cls.return_value = guard_inst

            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app

            exit_code = run(opts)

            self.assertEqual(exit_code, ExitCode.SUCCESS)
            mock_app.exec.assert_not_called()
