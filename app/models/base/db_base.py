import logging
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from typing import Any, Literal, Optional, Union, overload

from app.models.base.db_connection_protocol import ConnectionManagerProtocol
from app.utils.db.synchronization import db_lock

# Logging setup
logger = logging.getLogger(__name__)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    """Safely convert sqlite3.Row to dict."""
    if row is None:
        return {}
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}
    return {}


class DatabaseError(Exception):
    """Base class for database errors"""

    pass


class ValidationError(DatabaseError):
    """Data validation error"""

    pass


# Whitelist допустимых таблиц для защиты от SQL-инъекций
ALLOWED_TABLES = {"sphere", "section", "category", "link"}
ALLOWED_PARENT_FIELDS = {"sphere_id", "section_id", "category_id"}

# Regex для валидации SQL идентификаторов (имена колонок)
IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class DatabaseBase:
    """Base class for DB models with unified connection and operations access."""

    def __init__(self, connection_manager: ConnectionManagerProtocol):
        """Initializes base class with connection manager (Database)."""
        self.connection_manager = connection_manager
        # Используем threading.local для автоматической очистки при завершении потока
        self._transaction_state = threading.local()

    @property
    def connection(self):
        """Returns active SQLite connection through manager."""
        return self.connection_manager.connection

    @property
    def _nesting_level(self) -> int:
        """Returns current transaction nesting level for this thread."""
        return getattr(self._transaction_state, "nesting_level", 0)

    @_nesting_level.setter
    def _nesting_level(self, value: int):
        """Sets transaction nesting level for this thread."""
        self._transaction_state.nesting_level = value

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

        IMPORTANT: Holds db_lock for the ENTIRE transaction to ensure isolation.
        Nested transactions use SAVEPOINT mechanism.

        Example:
            with self.transaction():
                # Outer transaction
                self._execute_with_error_handling("INSERT INTO sphere ...", ())

                with self.transaction():
                    # Nested transaction (SAVEPOINT)
                    self._execute_with_error_handling("INSERT INTO section ...", ())
                    # If this fails, only nested is rolled back

                # Outer continues here

        Notes:
        - `db_lock` is reentrant (RLock), so nested calls are safe.
        - Nested transactions are implemented via SAVEPOINT.
        - Only the outermost transaction commits to database.
        - All SQL operations should be within a transaction for data consistency.
        """
        conn = self.connection
        nesting_level = self._nesting_level

        if nesting_level > 0:
            # Вложенная транзакция — используем SAVEPOINT
            # UUID гарантирует уникальность без дополнительной блокировки
            sp_name = f"sp_{uuid.uuid4().hex[:8]}"

            # Явно держим db_lock для консистентности (RLock позволяет реентрантность)
            with db_lock:
                try:
                    conn.execute(f"SAVEPOINT {sp_name}")
                    self._nesting_level = nesting_level + 1
                    yield
                    conn.execute(f"RELEASE SAVEPOINT {sp_name}")
                except Exception:
                    try:
                        conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                        conn.execute(f"RELEASE SAVEPOINT {sp_name}")
                    except Exception as rollback_error:
                        logger.warning(
                            "Failed to rollback savepoint %s: %s",
                            sp_name,
                            rollback_error,
                        )
                    raise
                finally:
                    self._nesting_level = nesting_level
        else:
            # Внешняя транзакция — держим db_lock на весь блок для изоляции
            with db_lock:
                try:
                    conn.execute("BEGIN TRANSACTION")
                    self._nesting_level = 1
                    yield
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    self._nesting_level = 0

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

    def _validate_and_deduplicate_ids(
        self, ids: list[int], entity_name: str = "item"
    ) -> list[int]:
        """Validate, filter and deduplicate integer IDs.
        
        Args:
            ids: List of IDs to validate
            entity_name: Name of entity for logging (unused, kept for compatibility)
            
        Returns:
            List of unique valid positive integer IDs
        """
        if not ids:
            return []

        valid_ids = [
            int(x) for x in ids
            if isinstance(x, int) and not isinstance(x, bool) and x > 0
        ]

        unique_ids = list(dict.fromkeys(valid_ids))

        return unique_ids

    def _get_next_position(
        self,
        table_name: str,
        parent_field: Optional[str] = None,
        parent_id: Optional[int] = None,
    ) -> int:
        """Gets next position for element in table.

        IMPORTANT: Must be called within an active transaction to prevent race conditions.
        The transaction ensures atomicity between SELECT MAX and INSERT operations.
        """
        # Валидация table_name для защиты от SQL-инъекций
        if table_name not in ALLOWED_TABLES:
            raise ValidationError(f"Invalid table name: {table_name}")

        if parent_field and parent_field not in ALLOWED_PARENT_FIELDS:
            raise ValidationError(f"Invalid parent field: {parent_field}")

        try:
            if parent_field and parent_id is not None:
                # Безопасно: table_name и parent_field проверены через whitelist
                row = self._execute_with_error_handling(
                    f"SELECT COALESCE(MAX(position), -1) AS max_pos FROM {table_name} WHERE {parent_field} = ?",
                    (parent_id,),
                    fetch_method="one",
                )
            else:
                row = self._execute_with_error_handling(
                    f"SELECT COALESCE(MAX(position), -1) AS max_pos FROM {table_name}",
                    fetch_method="one",
                )

            # row гарантированно Row | None благодаря overload
            max_pos = row_to_dict(row).get("max_pos", -1)
            return max_pos + 1
        except Exception as e:
            logger.error("Error getting position for table %s: %s", table_name, e)
            raise DatabaseError(
                f"Failed to calculate position for {table_name}: {e}"
            ) from e

    @overload
    def _execute_with_error_handling(
        self,
        query: str,
        params: tuple[Any, ...] = ...,
        *,
        fetch_method: Literal["one"],
    ) -> sqlite3.Row | None:
        ...

    @overload
    def _execute_with_error_handling(
        self,
        query: str,
        params: tuple[Any, ...] = ...,
        *,
        fetch_method: Literal["all"],
    ) -> list[sqlite3.Row]:
        ...

    @overload
    def _execute_with_error_handling(
        self,
        query: str,
        params: tuple[Any, ...] = ...,
        *,
        fetch_method: None = ...,
    ) -> sqlite3.Cursor:
        ...

    def _execute_with_error_handling(
        self,
        query: str,
        params: tuple[Any, ...] = (),
        *,
        fetch_method: Optional[str] = None,
    ) -> Union[sqlite3.Cursor, sqlite3.Row, list[sqlite3.Row], None]:
        """Executes SQL query with error handling and locking.

        IMPORTANT:
        - Does NOT commit automatically. Caller must use transaction() or commit() explicitly.
        - For write operations (INSERT/UPDATE/DELETE), always use within transaction() context.
        - db_lock is held during query execution for thread safety.
        """
        try:
            with db_lock:
                cursor = self.connection.execute(query, params)
        except sqlite3.Error as e:
            logger.error("Error executing SQL query: %s, error: %s", query, e)
            raise DatabaseError(f"Database error: {e}") from e

        if fetch_method == "one":
            result = cursor.fetchone()
            return result  # type: ignore[return-value]
        elif fetch_method == "all":
            result = cursor.fetchall()
            return result  # type: ignore[return-value]
        return cursor

    def _execute_many_with_error_handling(
        self, query: str, seq_of_params: list[tuple[Any, ...]]
    ) -> sqlite3.Cursor:
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
        """Universal entity update method.

        IMPORTANT:
        - Does NOT commit automatically. Caller must use transaction() or commit() explicitly.
        - Should be called within transaction() context for data consistency.
        - Validates table name and column names to prevent SQL injection.
        """
        # Валидация table_name
        if table_name not in ALLOWED_TABLES:
            raise ValidationError(f"Invalid table name: {table_name}")

        fields = []
        params = []

        for key in valid_keys:
            if key in data:
                # Валидация имени колонки для дополнительной защиты
                if not IDENTIFIER_PATTERN.match(key):
                    raise ValidationError(
                        f"Invalid column name: {key}. Must match pattern: {IDENTIFIER_PATTERN.pattern}"
                    )
                fields.append(f"{key} = ?")
                params.append(data[key])

        if not fields:
            logger.debug("No fields to update for %s (ID: %s)", table_name, entity_id)
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

    def _reindex_positions(
        self, 
        table_name: str, 
        parent_column: Optional[str] = None, 
        parent_id: Optional[int] = None
    ) -> None:
        """Reindex position field for items sequentially from 0.
        
        Args:
            table_name: Name of table to reindex
            parent_column: Optional parent column name (e.g., 'sphere_id', 'section_id')
            parent_id: Optional parent ID value for filtering
            
        Example:
            >>> self._reindex_positions('section', 'sphere_id', 1)  # Reindex sections in sphere 1
            >>> self._reindex_positions('sphere')  # Reindex all spheres
        """
        # Validate table name
        if table_name not in {"sphere", "section", "category", "link"}:
            raise ValueError(f"Invalid table name: {table_name}")
        
        # Build query
        if parent_column and parent_id is not None:
            where_clause = f"WHERE {parent_column} = ?"
            params = (parent_id,)
        else:
            where_clause = ""
            params = ()
        
        # Get items in order
        rows = self._execute_with_error_handling(
            f"SELECT id FROM {table_name} {where_clause} ORDER BY position, id",
            params,
            fetch_method="all",
        )
        
        ids_in_order = [int(r["id"]) for r in (rows or [])]
        if not ids_in_order:
            return
        
        # Prepare batch updates
        updates = [(pos, cid) for pos, cid in enumerate(ids_in_order)]
        
        self._execute_many_with_error_handling(
            f"UPDATE {table_name} SET position = ? WHERE id = ?",
            updates,
        )
        
        logger.debug(
            "Reindexed %d items in %s%s",
            len(updates),
            table_name,
            f" (parent {parent_column}={parent_id})" if parent_column else "",
        )

    @staticmethod
    def _ensure_row_list(
        rows: Union[sqlite3.Cursor, sqlite3.Row, list[sqlite3.Row], None]
    ) -> list[sqlite3.Row]:
        """Normalize database fetch results to a list of rows."""
        if rows is None:
            return []
        if isinstance(rows, sqlite3.Cursor):
            return rows.fetchall()
        if isinstance(rows, sqlite3.Row):
            return [rows]
        if isinstance(rows, list):
            return rows
        raise TypeError(f"Unexpected type for rows: {type(rows)}")
