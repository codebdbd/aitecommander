"""
Migration 0005: Adding indexes to improve query performance.

Creates indexes on frequently queried columns to speed up:
- Loading links by category
- Favorite filtering
- Recent links sorting
- Structure search
- Type and argument filtering
"""

import sqlite3
from typing import Any


def migrate(conn: sqlite3.Connection, logger: Any) -> None:
    """Creates indexes to improve query performance."""

    # Indexes for link table
    indexes = [
        # Most critical: loading links by category
        # Used in: get_links(), get_links_count(), batch operations
        (
            "idx_link_category_id",
            "CREATE INDEX IF NOT EXISTS idx_link_category_id ON link(category_id)",
        ),
        # For fast favorite filtering
        # Used in: get_favorite_links(), count_favorites(), clear_favorites()
        (
            "idx_link_is_favorite",
            "CREATE INDEX IF NOT EXISTS idx_link_is_favorite ON link(is_favorite) WHERE is_favorite = 1",
        ),
        # For sorting recent links (partial index for NOT NULL)
        # Used in: get_recent_links()
        (
            "idx_link_last_used",
            "CREATE INDEX IF NOT EXISTS idx_link_last_used ON link(last_used DESC) WHERE last_used IS NOT NULL",
        ),
        # Composite index for loading category links with position sorting
        # Covers most frequent query: SELECT ... WHERE category_id = ? ORDER BY position
        (
            "idx_link_category_position",
            "CREATE INDEX IF NOT EXISTS idx_link_category_position ON link(category_id, position)",
        ),
        # For duplicate search and uniqueness check
        # Used in: find_duplicate(), get_link_by_unique_key()
        (
            "idx_link_category_name_url_args",
            "CREATE INDEX IF NOT EXISTS idx_link_category_name_url_args ON link(category_id, name, url, args)",
        ),
        # For link type filtering
        # Used in: get_links_by_args_pattern() (type = 'web')
        ("idx_link_type", "CREATE INDEX IF NOT EXISTS idx_link_type ON link(type)"),
        # Indexes for section table
        # Used in: get_sections_by_sphere(), get_section_order()
        (
            "idx_section_sphere_id",
            "CREATE INDEX IF NOT EXISTS idx_section_sphere_id ON section(sphere_id)",
        ),
        # Composite index for loading sphere sections with sorting
        (
            "idx_section_sphere_position",
            "CREATE INDEX IF NOT EXISTS idx_section_sphere_position ON section(sphere_id, position)",
        ),
        # Indexes for category table
        # Used in: get_categories_by_section(), get_categories_by_sections()
        (
            "idx_category_section_id",
            "CREATE INDEX IF NOT EXISTS idx_category_section_id ON category(section_id)",
        ),
        # Composite index for loading section categories with sorting
        (
            "idx_category_section_position",
            "CREATE INDEX IF NOT EXISTS idx_category_section_position ON category(section_id, position)",
        ),
    ]

    created_count = 0
    for index_name, sql in indexes:
        try:
            conn.execute(sql)
            created_count += 1
            logger.debug(f"Migration 0005: created index {index_name}")
        except sqlite3.OperationalError as e:
            logger.warning(f"Migration 0005: failed to create index {index_name}: {e}")
            # Continue creating other indexes, even if one failed

    logger.info(
        f"Migration 0005: created {created_count}/{len(indexes)} performance indexes"
    )

    # Analyze tables to update optimizer statistics
    try:
        conn.execute("ANALYZE")
        logger.info("Migration 0005: DB statistics updated (ANALYZE)")
    except sqlite3.OperationalError as e:
        logger.warning(f"Migration 0005: failed to execute ANALYZE: {e}")


def rollback(conn: sqlite3.Connection, logger: Any) -> None:
    """Rolls back migration by deleting created indexes."""

    indexes_to_drop = [
        "idx_link_category_id",
        "idx_link_is_favorite",
        "idx_link_last_used",
        "idx_link_category_position",
        "idx_link_category_name_url_args",
        "idx_link_type",
        "idx_section_sphere_id",
        "idx_section_sphere_position",
        "idx_category_section_id",
        "idx_category_section_position",
    ]

    dropped_count = 0
    for index_name in indexes_to_drop:
        try:
            conn.execute(f"DROP INDEX IF EXISTS {index_name}")
            dropped_count += 1
            logger.debug(f"Rollback 0005: deleted index {index_name}")
        except sqlite3.OperationalError as e:
            logger.warning(f"Rollback 0005: failed to delete index {index_name}: {e}")

    logger.info(
        f"Rollback 0005: deleted {dropped_count}/{len(indexes_to_drop)} indexes"
    )
