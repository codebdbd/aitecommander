import sqlite3
from typing import Any


def _row_value(row: sqlite3.Row | tuple, key: str, index: int) -> Any:
    if isinstance(row, sqlite3.Row):
        return row[key]
    return row[index]


def migrate(conn: sqlite3.Connection, logger: Any) -> None:
    """Normalize link positions to contiguous zero-based order per category."""
    categories = conn.execute("SELECT DISTINCT category_id FROM link").fetchall()
    updated = 0

    for category_row in categories:
        category_id = int(_row_value(category_row, "category_id", 0))
        rows = conn.execute(
            """
            SELECT id
            FROM link
            WHERE category_id = ?
            ORDER BY position ASC, name COLLATE NOCASE ASC, id ASC
            """,
            (category_id,),
        ).fetchall()

        for position, link_row in enumerate(rows):
            link_id = int(_row_value(link_row, "id", 0))
            conn.execute(
                "UPDATE link SET position = ? WHERE id = ?",
                (position, link_id),
            )
            updated += 1

    logger.info("Migration 0010: normalized positions for %d links", updated)
