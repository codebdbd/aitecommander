import sqlite3
from typing import Any


def migrate(conn: sqlite3.Connection, logger: Any) -> None:
    # Check if browser_key column already exists
    cols = conn.execute("PRAGMA table_info('link')").fetchall()
    names = {str(dict(r)["name"]) for r in cols}
    if "browser_key" in names:
        logger.debug("Migration 0002: browser_key already exists — skipping")
        return
    conn.execute("ALTER TABLE link ADD COLUMN browser_key TEXT DEFAULT NULL")
    logger.info("Migration 0002: added browser_key column to link")
