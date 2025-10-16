import sqlite3
from typing import Any


def migrate(conn: sqlite3.Connection, logger: Any) -> None:
    """
    Creates case-insensitive unique indexes for sphere/section/category.

    Important: If data contains case duplicates, index creation will fail
    with OperationalError. In this case migration is interrupted by exception, schema
    version will NOT be increased. After eliminating duplicates, re-run will succeed.
    """
    try:
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sphere_name_nocase
            ON sphere(name COLLATE NOCASE)
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_section_sphere_name_nocase
            ON section(sphere_id, name COLLATE NOCASE)
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_category_section_name_nocase
            ON category(section_id, name COLLATE NOCASE)
            """
        )
        logger.info(
            "Migration 0004: NOCASE indexes for sphere/section/category created (if missing)"
        )
    except sqlite3.OperationalError as e:
        logger.warning(
            "Migration 0004: failed to create NOCASE indexes (possible duplicates): %s",
            e,
        )
        raise
