"""
Migration 0006: index for fast favorite list ordering.

`get_favorite_links()` filters by `is_favorite=1` and sorts by `position`.
This partial composite index avoids large in-memory sorts on big datasets.
"""

import sqlite3
from typing import Any


def migrate(conn: sqlite3.Connection, logger: Any) -> None:
    """Create partial composite index for favorites ordered by position."""
    sql = (
        "CREATE INDEX IF NOT EXISTS idx_link_favorite_position "
        "ON link(is_favorite, position) "
        "WHERE is_favorite = 1"
    )
    try:
        conn.execute(sql)
        logger.info("Migration 0006: created index idx_link_favorite_position")
    except sqlite3.OperationalError as e:
        logger.error(
            "Migration 0006: failed to create idx_link_favorite_position: %s",
            e,
        )
        raise

    try:
        conn.execute("ANALYZE")
    except sqlite3.OperationalError as e:
        logger.warning("Migration 0006: ANALYZE failed: %s", e)


def rollback(conn: sqlite3.Connection, logger: Any) -> None:
    """Drop index created by migration 0006."""
    try:
        conn.execute("DROP INDEX IF EXISTS idx_link_favorite_position")
        logger.info("Rollback 0006: dropped idx_link_favorite_position")
    except sqlite3.OperationalError as e:
        logger.warning(
            "Rollback 0006: failed to drop idx_link_favorite_position: %s",
            e,
        )
