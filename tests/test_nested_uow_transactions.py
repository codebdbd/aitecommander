"""Integration test for nested transaction context and UoW consistency."""

import sqlite3
import unittest
from app.models.db import Database
from app.services.uow import unit_of_work


class TestNestedUoWTransactions(unittest.TestCase):
    """Verify shared transaction state across models and nested savepoint rollback."""

    def setUp(self) -> None:
        self.db = Database()

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
