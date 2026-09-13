from __future__ import annotations

import sqlite3
from typing import Any


def _resolve_conflicts(conn: sqlite3.Connection, logger: Any) -> None:
    """Find and resolve duplicate (category_id, name, url, args) before recreating table.

    If two or more links share (category_id, name, url, args) (e.g. they had different types),
    rename subsequent duplicates to '{name} ({type})' or '{name} ({type} {counter})'
    so that no rows or metadata are lost during migration.
    """
    conflicts = conn.execute(
        """
        SELECT category_id, name, url, args, COUNT(*) as cnt
        FROM link
        GROUP BY category_id, name, url, args
        HAVING cnt > 1
        """
    ).fetchall()

    if not conflicts:
        return

    logger.warning("Migration 0003: found %d duplicate link groups, resolving...", len(conflicts))

    for group in conflicts:
        try:
            cat_id = group["category_id"]
            name = group["name"]
            url = group["url"]
            args = group["args"]
        except Exception:
            cat_id, name, url, args = group[0], group[1], group[2], group[3]

        rows = conn.execute(
            """
            SELECT id, name, type FROM link
            WHERE category_id = ? AND name = ? AND url = ? AND args = ?
            ORDER BY id ASC
            """,
            (cat_id, name, url, args),
        ).fetchall()

        # Keep first link as-is, rename subsequent duplicates
        for i, row in enumerate(rows[1:], start=1):
            try:
                row_id = row["id"]
                row_type = row["type"]
            except Exception:
                row_id, row_type = row[0], row[2]

            candidate_name = f"{name} ({row_type})"
            counter = 1
            while True:
                existing = conn.execute(
                    """
                    SELECT id FROM link
                    WHERE category_id = ? AND name = ? AND url = ? AND args = ? AND id != ?
                    """,
                    (cat_id, candidate_name, url, args, row_id),
                ).fetchone()
                if not existing:
                    break
                counter += 1
                candidate_name = f"{name} ({row_type} {counter})"

            conn.execute(
                "UPDATE link SET name = ? WHERE id = ?",
                (candidate_name, row_id),
            )
            logger.warning(
                "Migration 0003: resolved duplicate link id=%s: renamed '%s' -> '%s'",
                row_id,
                name,
                candidate_name,
            )


def migrate(conn: sqlite3.Connection, logger: Any) -> None:
    """Recreate link table with UNIQUE(category_id, name, url, args),

    if old unique index found on (category_id, url, args, type).
    Preserves all rows and resolves duplicate conflicts safely without data loss.
    """
    # Check current unique indexes of link table
    idx_list = conn.execute("PRAGMA index_list('link')").fetchall()
    need_migrate = False
    for idx in idx_list:
        # row: seq, name, unique, origin, partial
        try:
            unique = int(dict(idx).get("unique", 0))
            name = dict(idx).get("name")
        except Exception:
            unique = idx[2]
            name = idx[1]
        if unique == 1:
            cols = conn.execute(f"PRAGMA index_info('{name}')").fetchall()
            col_names = []
            for c in cols:
                try:
                    col_names.append(dict(c).get("name"))
                except Exception:
                    col_names.append(c[2])
            if col_names == ["category_id", "url", "args", "type"]:
                need_migrate = True
                break

    if not need_migrate:
        logger.debug("Migration 0003: link recreation not required — skipping")
        return

    logger.info(
        "Migration 0003: recreating link with UNIQUE(category_id,name,url,args)"
    )
    in_tx = conn.in_transaction
    if not in_tx:
        conn.execute("BEGIN TRANSACTION")
    try:
        total_before = conn.execute("SELECT COUNT(*) FROM link").fetchone()[0]

        _resolve_conflicts(conn, logger)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS link_new (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id  INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE,
                name         TEXT    NOT NULL,
                url          TEXT    NOT NULL,
                type         TEXT    NOT NULL CHECK(type IN ('web','file','program','script','folder')),
                notes        TEXT    DEFAULT '',
                is_favorite  INTEGER NOT NULL CHECK(is_favorite IN (0,1)) DEFAULT 0,
                last_used    TEXT    DEFAULT NULL,
                icon_path    TEXT    NOT NULL DEFAULT 'default.ico',
                args         TEXT    DEFAULT '',
                browser_key  TEXT    DEFAULT NULL,
                position     INTEGER NOT NULL DEFAULT 0,
                UNIQUE(category_id, name, url, args)
            )
            """
        )

        # Strict INSERT: do not use INSERT OR IGNORE to prevent silent row drops
        conn.execute(
            """
            INSERT INTO link_new 
                (id, category_id, name, url, type, notes, is_favorite, last_used, icon_path, args, browser_key, position)
            SELECT id, category_id, name, url, type, notes, is_favorite, last_used, icon_path, args, browser_key, position
            FROM link
            """
        )

        total_after = conn.execute("SELECT COUNT(*) FROM link_new").fetchone()[0]
        if total_after != total_before:
            raise RuntimeError(
                f"Migration 0003 row count mismatch: expected {total_before}, got {total_after}"
            )

        conn.execute("DROP TABLE link")
        conn.execute("ALTER TABLE link_new RENAME TO link")

        if not in_tx:
            conn.commit()
        logger.info(
            "Migration 0003: link table successfully recreated (%d rows preserved)",
            total_after,
        )
    except Exception as e:
        if not in_tx:
            conn.rollback()
        logger.exception("Migration 0003 error (link recreation): %s", e)
        raise
