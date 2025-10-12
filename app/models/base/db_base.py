import logging
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Union

from app.utils.db.synchronization import db_lock

# Logging setup
logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Base class for database errors"""

    pass


class ValidationError(DatabaseError):
    """Data validation error"""

    pass


class DatabaseBase:
    """Base class for DB models with unified connection and operations access."""

    def __init__(self, connection_manager):
        """Initializes base class with connection manager (Database)."""
        self.connection_manager = connection_manager
        # Counter for generating unique SAVEPOINT names within process/thread
        self._savepoint_counter = 0

    @property
    def connection(self):
        """Returns active SQLite connection through manager."""
        return self.connection_manager.connection

    def commit(self) -> None:
        """Commits current transaction."""
        try:
            with db_lock:
                self.connection.commit()
        except sqlite3.Error as e:
            logger.error("Commit error: %s", e)
            raise DatabaseError(f"Commit error: {e}") from e

    def rollback(self) -> None:
        """Rolls back current transaction."""
        try:
            with db_lock:
                self.connection.rollback()
        except sqlite3.Error as e:
            logger.error("Rollback error: %s", e)
            raise DatabaseError(f"Rollback error: {e}") from e

    @contextmanager
    def transaction(self):
        """Transaction context manager with automatic commit/rollback.

        Now global `db_lock` is held for the ENTIRE duration
        of the transaction block (including `with ...:` body), which ensures
        exclusive DB access and excludes interference from other threads
        between BEGIN/COMMIT/ROLLBACK.

        Notes:
        - `db_lock` is reentrant (RLock), so nested calls that
          also use `db_lock` are safe and don't cause deadlocks.
        - Inside the block, don't open nested transactions at SQLite level,
          use one common block or SAVEPOINT when needed.
        """
        with db_lock:
            conn = self.connection
            # If already inside transaction — create nested via SAVEPOINT
            if getattr(conn, "in_transaction", False):
                sp_name = f"sp_{threading.get_ident()}_{self._savepoint_counter}"
                self._savepoint_counter += 1
                try:
                    conn.execute(f"SAVEPOINT {sp_name}")
                    yield
                    conn.execute(f"RELEASE SAVEPOINT {sp_name}")
                except Exception:
                    try:
                        # Rollback only to nested transaction boundary
                        conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                        conn.execute(f"RELEASE SAVEPOINT {sp_name}")
                    except Exception:
                        # Ignore secondary rollback errors to not hide primary error
                        pass
                    raise
            else:
                # External (top-level) transaction
                try:
                    conn.execute("BEGIN TRANSACTION")
                    yield
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

    def _validate_required_fields(
        self, data: dict[str, Any], required_fields: list[str], entity_name: str = ""
    ):
        """Validates required fields"""
        # Deferred import to prevent circular imports
        from app.utils.validators import validate_required_fields

        if not validate_required_fields(data, required_fields, entity_name):
            raise ValidationError(
                f"Missing required fields for {entity_name}: {[field for field in required_fields if field not in data]}"
            )

    def _get_next_position(
        self, table_name: str, parent_field: str = None, parent_id: int = None
    ) -> int:
        """Gets next position for element in table."""
        try:
            if parent_field and parent_id is not None:
                row = self._execute_with_error_handling(
                    f"SELECT MAX(position) AS max_pos FROM {table_name} WHERE {parent_field} = ?",
                    (parent_id,),
                    fetch_method="one",
                )
            else:
                row = self._execute_with_error_handling(
                    f"SELECT MAX(position) AS max_pos FROM {table_name}",
                    fetch_method="one",
                )

            max_pos = None if row is None else dict(row).get("max_pos")
            return (max_pos + 1) if max_pos is not None else 0
        except Exception as e:
            logger.error("Error getting position for table %s: %s", table_name, e)
            # Propagate as DatabaseError to not hide DB and element order issues
            raise DatabaseError(
                f"Failed to calculate position for {table_name}: {e}"
            ) from e

    def _execute_with_error_handling(
        self, query: str, params: tuple = (), fetch_method: str = None
    ) -> Union[sqlite3.Cursor, sqlite3.Row, list[sqlite3.Row], None]:
        """Executes SQL query with error handling and locking."""
        try:
            with db_lock:
                cursor = self.connection.execute(query, params)
        except sqlite3.Error as e:
            logger.error("Error executing SQL query: %s, error: %s", query, e)
            raise DatabaseError(f"Database error: {e}") from e

        if fetch_method == "one":
            return cursor.fetchone()
        elif fetch_method == "all":
            return cursor.fetchall()
        return cursor

    def _execute_many_with_error_handling(self, query: str, seq_of_params: list[tuple]):
        """
        Executes SQL executemany query with error handling and locking.

        Note: Commit is not performed automatically, as in
        `_execute_with_error_handling`. Calling side should decide
        when to commit transaction or use `self.transaction()`.
        """
        try:
            with db_lock:
                cursor = self.connection.executemany(query, seq_of_params)
            return cursor
        except sqlite3.Error as e:
            logger.error(
                "Error executing SQL executemany: %s, batch count=%s, error: %s",
                query,
                len(seq_of_params),
                e,
            )
            raise DatabaseError(f"Database error (executemany): {e}") from e

    def _update_entity(
        self,
        table_name: str,
        entity_id: int,
        data: dict[str, Any],
        valid_keys: list[str],
    ):
        """Universal entity update method."""
        fields = []
        params = []

        for key in valid_keys:
            if key in data:
                fields.append(f"{key} = ?")
                params.append(data[key])

        if not fields:
            return

        query = f"UPDATE {table_name} SET {', '.join(fields)} WHERE id=?"
        params.append(entity_id)

        try:
            with db_lock:
                self.connection.execute(query, tuple(params))
            logger.debug("Updated %s with ID %s", table_name, entity_id)
        except Exception as e:
            logger.error("Error updating %s: %s", table_name, e)
            raise DatabaseError(f"Failed to update {table_name}: {e}") from e
