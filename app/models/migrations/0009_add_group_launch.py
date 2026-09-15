import sqlite3
from typing import Any

def migrate(conn: sqlite3.Connection, logger: Any) -> None:
    """Add is_group_launch to link table."""
    cols = conn.execute("PRAGMA table_info('link')").fetchall()
    names = {
        str(r["name"] if isinstance(r, sqlite3.Row) or hasattr(r, "keys") else r[1])
        for r in cols
    }
    if "is_group_launch" not in names:
        conn.execute("ALTER TABLE link ADD COLUMN is_group_launch INTEGER NOT NULL DEFAULT 0")
        logger.info("Migration 0009: added is_group_launch column to link")

