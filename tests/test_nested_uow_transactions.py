"""Integration test for nested transaction context and UoW consistency."""

import shutil
import unittest

from app.core.database_manager import DatabaseManager
from app.models.db import Database
from tests.conftest import build_test_temp_path


class TestNestedUoWTransactions(unittest.TestCase):
    """Verify shared transaction state across models and nested savepoint rollback."""

    def setUp(self) -> None:
        self._old_db_path = DatabaseManager._db_path
        self._old_global_pragmas_path = DatabaseManager._global_pragmas_applied_path
        self._temp_dir = build_test_temp_path("manual_tmp", f"nested_uow_{id(self)}")
        shutil.rmtree(self._temp_dir, ignore_errors=True)
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        DatabaseManager.close_all()
        DatabaseManager.configure(self._temp_dir / "nested_uow.db")
        self.db = Database()

    def tearDown(self) -> None:
        DatabaseManager.close_all()
        DatabaseManager._db_path = self._old_db_path
        DatabaseManager._global_pragmas_applied_path = self._old_global_pragmas_path
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def test_shared_transaction_state_across_models(self) -> None:
        """Verify that all model instances share the exact same _transaction_state object."""
        base_state = self.db._base._transaction_state
        self.assertIs(self.db.spheres._transaction_state, base_state)
        self.assertIs(self.db.sections._transaction_state, base_state)
        self.assertIs(self.db.categories._transaction_state, base_state)
        self.assertIs(self.db.links._transaction_state, base_state)

    def test_nested_transaction_savepoints(self) -> None:
        """Verify that nested transactions increment nesting level and use SAVEPOINTs without OperationalError."""
        state = self.db._base._transaction_state
        self.assertEqual(getattr(state, "nesting_level", 0), 0)

        with self.db._base.transaction():
            self.assertEqual(state.nesting_level, 1)
            with self.db.links.transaction():
                self.assertEqual(state.nesting_level, 2)
                with self.db.categories.transaction():
                    self.assertEqual(state.nesting_level, 3)
                self.assertEqual(state.nesting_level, 2)
            self.assertEqual(state.nesting_level, 1)

        self.assertEqual(getattr(state, "nesting_level", 0), 0)

    def test_nested_transaction_rollback_preserves_state(self) -> None:
        """Verify that an exception inside a nested transaction rolls back cleanly without breaking state."""
        state = self.db._base._transaction_state

        with self.assertRaises(RuntimeError):
            with self.db._base.transaction():
                self.assertEqual(state.nesting_level, 1)
                with self.db.links.transaction():
                    self.assertEqual(state.nesting_level, 2)
                    raise RuntimeError("Simulated nested failure")

        self.assertEqual(getattr(state, "nesting_level", 0), 0)
