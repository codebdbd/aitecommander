import sqlite3
from typing import Any


def migrate(conn: sqlite3.Connection, logger: Any) -> None:
    """Add Chrome profile rotation support to the link table.

    New columns:
    - chrome_rotation  (INTEGER 0/1): whether rotation is enabled for this link
    - rotation_index   (INTEGER):     current position in the rotation cycle
    - rotation_profiles (TEXT/JSON):  JSON array of profile dicts for rotation
    """
    cols = conn.execute("PRAGMA table_info('link')").fetchall()
    names = {
        str(r["name"] if isinstance(r, sqlite3.Row) or hasattr(r, "keys") else r[1])
        for r in cols
    }

    if "chrome_rotation" not in names:
        conn.execute(
            "ALTER TABLE link ADD COLUMN chrome_rotation INTEGER NOT NULL DEFAULT 0"
        )
        logger.info("Migration 0008: added chrome_rotation column to link")

    if "rotation_index" not in names:
        conn.execute(
            "ALTER TABLE link ADD COLUMN rotation_index INTEGER NOT NULL DEFAULT 0"
        )
        logger.info("Migration 0008: added rotation_index column to link")

    if "rotation_profiles" not in names:
        conn.execute(
            "ALTER TABLE link ADD COLUMN rotation_profiles TEXT DEFAULT NULL"
        )
        logger.info("Migration 0008: added rotation_profiles column to link")
