"""
Migration 0007: Replace default.ico with type-specific icons.

This migration replaces all occurrences of 'default.ico' in the link table
with the appropriate icon based on the link type:
- web -> web_icon.png
- file -> documents_icon.png
- folder -> folder_icon.png
- program -> program_icon.png
- script -> script_icon.png
"""

import sqlite3
from typing import Any


# Mapping of link types to their default icons
LINK_TYPE_ICONS = {
    "web": "web_icon.png",
    "file": "documents_icon.png",
    "folder": "folder_icon.png",
    "program": "program_icon.png",
    "script": "script_icon.png",
}


def migrate(conn: sqlite3.Connection, logger: Any) -> None:
    """Replace default.ico with type-specific icons."""
    try:
        # Update each link type separately
        for link_type, icon_path in LINK_TYPE_ICONS.items():
            cursor = conn.execute(
                "UPDATE link SET icon_path = ? WHERE type = ? AND icon_path = 'default.ico'",
                (icon_path, link_type),
            )
            if cursor.rowcount > 0:
                logger.info(
                    "Migration 0007: updated %d %s links to use %s",
                    cursor.rowcount,
                    link_type,
                    icon_path,
                )

        # Also update any remaining links with empty icon_path
        cursor = conn.execute(
            "UPDATE link SET icon_path = 'web_icon.png' WHERE (icon_path = '' OR icon_path IS NULL) AND type = 'web'"
        )
        if cursor.rowcount > 0:
            logger.info(
                "Migration 0007: updated %d web links with empty icon_path",
                cursor.rowcount,
            )

        # Note: SQLite doesn't support ALTER COLUMN, so we can't change the default.
        # The schema.sql file has been updated for new databases.

    except sqlite3.OperationalError as e:
        logger.error("Migration 0007 failed: %s", e)
        raise


def rollback(conn: sqlite3.Connection, logger: Any) -> None:
    """Rollback is not supported for this migration."""
    logger.warning("Migration 0007 rollback: not supported, manual intervention required")
