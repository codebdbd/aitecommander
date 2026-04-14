import datetime
import logging
import sqlite3
import time
from typing import Any, Optional

from ...utils.db.sql_helpers import build_in_clause_placeholders
from ..base.db_base import (
    DatabaseBase,
    DatabaseError,
    ValidationError,
    db_lock,
    row_to_dict,
)
from ..types.link_type import LinkType
from ..types.link_types import LinkDict
from ..utils.link_bulk_upsert_service import LinkBulkUpsertService
from ..utils.link_validators import normalize_link_fields, validate_link_data

logger = logging.getLogger(__name__)


ALLOWED_LINK_COLUMNS = {
    "id",
    "category_id",
    "name",
    "url",
    "type",
    "notes",
    "is_favorite",
    "last_used",
    "icon_path",
    "args",
    "browser_key",
    "position",
}

LINK_ALL_COLUMNS = ", ".join(sorted(ALLOWED_LINK_COLUMNS))


class LinkModel(DatabaseBase):
    """Model for working with links in database."""

    def __init__(self, connection_manager):
        """Initialize LinkModel with connection manager."""
        super().__init__(connection_manager)

    def get_links(
        self,
        category_id: int,
        *,
        fields: Optional[list[str]] = None,
        all_fields: bool = False,
    ) -> list[LinkDict]:
        """Return list of links for specified category."""
        try:
            if all_fields:
                select_clause = f"SELECT {LINK_ALL_COLUMNS}"
            else:
                default_fields = [
                    "id",
                    "category_id",
                    "name",
                    "url",
                    "type",
                    "notes",
                    "is_favorite",
                    "last_used",
                    "icon_path",
                    "args",
                    "browser_key",
                    "position",
                ]
                use_fields_raw = list(fields or default_fields)
                use_fields = [
                    f
                    for f in use_fields_raw
                    if isinstance(f, str) and f in ALLOWED_LINK_COLUMNS
                ]
                # Log ignored fields
                ignored = [
                    f
                    for f in use_fields_raw
                    if not (isinstance(f, str) and f in ALLOWED_LINK_COLUMNS)
                ]
                if ignored:
                    logger.warning(
                        "get_links: ignored invalid fields %s; allowed=%s",
                        ignored,
                        sorted(ALLOWED_LINK_COLUMNS),
                    )
                if not use_fields:
                    use_fields = list(default_fields)
                select_clause = (
                    f"SELECT {', '.join(use_fields)}" if use_fields else "SELECT *"
                )

            rows = self._execute_with_error_handling(
                f"{select_clause} FROM link WHERE category_id=? ORDER BY position ASC",
                (category_id,),
                fetch_method="all",
            )
            return [row_to_dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error(
                "Error getting links for category %s: %s",
                category_id,
                e,
                exc_info=True,
            )
            raise

    def get_links_for_categories(
        self, category_ids: list[int]
    ) -> dict[int, list[dict[str, Any]]]:
        """Fetch links for multiple categories in batched queries."""
        if not category_ids:
            return {}
        try:
            ids = [
                int(cid)
                for cid in category_ids
                if isinstance(cid, int) and not isinstance(cid, bool) and cid > 0
            ]
        except Exception:
            ids = []
        if not ids:
            return {}

        CHUNK = 900
        result: dict[int, list[dict[str, Any]]] = {cid: [] for cid in ids}
        select_clause = (
            "SELECT id, category_id, name, url, type, notes, "
            "is_favorite, last_used, icon_path, args, browser_key, position "
            "FROM link WHERE category_id IN ({placeholders}) "
            "ORDER BY category_id, position"
        )

        for i in range(0, len(ids), CHUNK):
            chunk = ids[i : i + CHUNK]
            placeholders = build_in_clause_placeholders(len(chunk))
            rows = self._execute_with_error_handling(
                select_clause.format(placeholders=placeholders),
                tuple(chunk),
                fetch_method="all",
            )
            for row in rows or []:
                try:
                    row_dict = row_to_dict(row)
                    cid = int(row_dict["category_id"])
                except Exception:
                    continue
                result.setdefault(cid, []).append(row_dict)

        return {cid: rows for cid, rows in result.items() if rows}

    def count_links_by_category(self, category_id: int) -> int:
        """Return number of links for specified category."""
        try:
            result = self._execute_with_error_handling(
                "SELECT COUNT(*) AS cnt FROM link WHERE category_id=?",
                (category_id,),
                fetch_method="one",
            )
            if result is None:
                return 0
            assert result is None or isinstance(result, sqlite3.Row)  # type: ignore[unreachable]
            cnt_data = row_to_dict(result)
            return int(cnt_data.get("cnt", 0)) if cnt_data.get("cnt") is not None else 0
        except Exception as e:
            logger.error(
                "Error counting links for category %s: %s",
                category_id,
                e,
                exc_info=True,
            )
            return 0

    def count_links_by_categories(self, category_ids: list[int]) -> dict[int, int]:
        """Return dictionary {category_id: count} for set of categories."""
        if not category_ids:
            return {}
        try:
            # Remove duplicates and incorrect values
            ids = [int(cid) for cid in category_ids if isinstance(cid, int) and cid > 0]
            if not ids:
                return {}

            # Chunking for SQLite parameter limit (~999)
            CHUNK = 900
            result: dict[int, int] = {}
            for i in range(0, len(ids), CHUNK):
                chunk = ids[i : i + CHUNK]
                placeholders = build_in_clause_placeholders(len(chunk))
                rows = self._execute_with_error_handling(
                    f"SELECT category_id AS category_id, COUNT(*) AS cnt FROM link WHERE category_id IN ({placeholders}) GROUP BY category_id",
                    tuple(chunk),
                    fetch_method="all",
                )
                for r in rows or []:
                    try:
                        r_dict = row_to_dict(r)
                        cat_id = int(
                            r_dict["category_id"]
                        )  # sqlite3.Row converted to dict
                        cnt = int(r_dict["cnt"])  # aggregated alias
                        result[cat_id] = result.get(cat_id, 0) + cnt
                    except Exception:
                        continue
            return result
        except Exception as e:
            logger.error(
                "Error batch counting links for categories %s: %s",
                category_ids,
                e,
                exc_info=True,
            )
            return {}

    def upsert_link(self, link: dict[str, Any]) -> int:
        """Insert or update link record. Return record ID."""
        self._validate_required_fields(link, ["category_id"], "link")
        
        # Use centralized validation
        validate_link_data(link)

        all_possible_fields = [
            "id",
            "category_id",
            "name",
            "url",
            "type",
            "notes",
            "is_favorite",
            "last_used",
            "icon_path",
            "args",
            "position",
            "browser_key",
        ]

        data = {field: link.get(field) for field in all_possible_fields}
        data["is_favorite"] = int(data.get("is_favorite", 0) or 0)
        data["icon_path"] = data.get("icon_path", "") or ""
        try:
            data["type"] = LinkType.from_value(data.get("type", "web")).value
        except Exception:
            data["type"] = LinkType.WEB.value

        logger.debug(
            "Upsert link: %s, browser_key=%s",
            data.get("name", "Untitled"),
            data.get("browser_key"),
        )
        logger.debug("Upsert link: full data=%s", data)

        try:
            if data["id"]:
                if data["position"] is None:
                    data["position"] = 0

                update_fields = [f for f in all_possible_fields if f != "id"]
                update_placeholders = ", ".join([f"{f}=?" for f in update_fields])
                update_values = [data[f] for f in update_fields]

                cursor = self._execute_with_error_handling(
                    f"UPDATE link SET {update_placeholders} WHERE id=?",
                    tuple(update_values + [data["id"]]),
                )

                if isinstance(cursor, sqlite3.Cursor) and cursor.rowcount == 0:
                    insert_fields = all_possible_fields
                    insert_placeholders = ", ".join(["?"] * len(insert_fields))
                    insert_values = [data[f] for f in insert_fields]

                    self._execute_with_error_handling(
                        f"INSERT INTO link ({', '.join(insert_fields)}) VALUES ({insert_placeholders})",
                        tuple(insert_values),
                    )

                logger.debug(
                    "Updated link with ID %s, browser_key=%s",
                    data["id"],
                    data.get("browser_key"),
                )
                return data["id"]
            else:
                data["position"] = self._get_next_position(
                    "link", "category_id", data["category_id"]
                )

                existing = self.get_link_by_name_url_args(
                    int(data["category_id"] or 0),
                    str(data.get("name", "")),
                    str(data.get("url", "")),
                    str(data.get("args", "")),
                )
                if existing:
                    return int(existing.get("id", 0))

                columns = [f for f in all_possible_fields if f != "id"]
                placeholders = ", ".join(["?"] * len(columns))
                values = [data[c] for c in columns]

                cursor = self._execute_with_error_handling(
                    f"INSERT INTO link ({', '.join(columns)}) VALUES ({placeholders})",
                    tuple(values),
                )

                new_id = 0
                if isinstance(cursor, sqlite3.Cursor):
                    new_id = cursor.lastrowid or 0
                logger.info(
                    "Added new link: %s, browser_key=%s",
                    data.get("name", "Untitled"),
                    data.get("browser_key"),
                )
                logger.debug(
                    "Added new link with ID %s, full data=%s",
                    new_id,
                    data,
                )
                return new_id
        except sqlite3.IntegrityError as e:
            try:
                cat_id = link.get("category_id")
                name = link.get("name", "")
                url = link.get("url", "")
                args = link.get("args", "")
                row = self._execute_with_error_handling(
                    "SELECT id FROM link WHERE category_id=? AND name=? AND url=? AND args=?",
                    (cat_id, name, url, args),
                    fetch_method="one",
                )
                if row:
                    try:
                        assert row is None or isinstance(row, sqlite3.Row)  # type: ignore[unreachable]
                        rec_id = int(row_to_dict(row).get("id", 0))
                        if rec_id:
                            return rec_id
                    except (KeyError, TypeError, ValueError) as conv_err:
                        logger.debug("upsert_link: ID conversion error: %s", conv_err)
            except Exception as ee:
                logger.debug(
                    "upsert_link: failed to recover existing row after IntegrityError: %s",
                    ee,
                    exc_info=True,
                )
            raise DatabaseError(f"UNIQUE constraint failed: {e}") from e

    def get_link_by_unique_fields(
        self,
        category_id: int,
        url: str,
        args: str = "",
        link_type: str = "web",
        name: str = "",
    ):
        """Find link by unique fields (category_id, url, args, type, name)."""
        try:
            row = self._execute_with_error_handling(
                f"SELECT {LINK_ALL_COLUMNS} FROM link WHERE category_id=? AND url=? AND args=? AND type=? AND name=?",
                (category_id, url, args, link_type, name),
                fetch_method="one",
            )
            if row:
                assert row is None or isinstance(row, sqlite3.Row)  # type: ignore[unreachable]
                return row_to_dict(row)
            return None
        except Exception as e:
            logger.error("Error finding link by unique fields: %s", e, exc_info=True)
            return None

    def get_link_by_name_url_args(
        self, category_id: int, name: str, url: str, args: str = ""
    ) -> Optional[dict[str, Any]]:
        """Find link by (name, url, args) within category."""
        try:
            row = self._execute_with_error_handling(
                f"SELECT {LINK_ALL_COLUMNS} FROM link WHERE category_id=? AND name=? AND url=? AND args=?",
                (category_id, name, url, args),
                fetch_method="one",
            )
            if row:
                assert row is None or isinstance(row, sqlite3.Row)  # type: ignore[unreachable]
                return row_to_dict(row)
            return None
        except Exception as e:
            logger.error("Error finding link by (name,url,args): %s", e, exc_info=True)
            return None


    def delete_link(self, link_id: int):
        """Delete link by ID."""
        try:
            self._execute_with_error_handling(
                "DELETE FROM link WHERE id= ?", (link_id,)
            )

            logger.info("Deleted link with ID %s", link_id)
        except Exception as e:
            logger.error("Error deleting link: %s", e, exc_info=True)
            raise DatabaseError(f"Failed to delete link: {e}") from e

    def update_link_last_used(self, link_id: int):
        """Update last used time for link."""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._execute_with_error_handling(
            "UPDATE link SET last_used = ? WHERE id = ?", (now, link_id)
        )

    def count_favorites(self) -> int:
        """Return number of favorite links."""
        row = self._execute_with_error_handling(
            "SELECT COUNT(*) AS cnt FROM link WHERE is_favorite=1",
            fetch_method="one",
        )
        assert row is None or isinstance(row, sqlite3.Row)  # type: ignore[unreachable]
        return int(row_to_dict(row)["cnt"]) if row else 0

    def clear_favorites(self):
        """Reset favorite flag for all links."""
        try:
            self._execute_with_error_handling(
                "UPDATE link SET is_favorite=0 WHERE is_favorite=1"
            )

            logger.info("Cleared all favorite links")
        except Exception as e:
            logger.error("Error clearing favorites: %s", e)
            raise DatabaseError(f"Failed to clear favorites: {e}") from e

    def search_links(self, query: str):
        """Search links where name, URL or notes contain query substring."""
        if not query:
            return []

        search_term = f"%{query}%"
        try:
            rows = self._execute_with_error_handling(
                "SELECT l.*, cat.name as category_name, sect.name as section_name, sph.name as sphere_name "
                "FROM link l "
                "JOIN category cat ON l.category_id = cat.id "
                "JOIN section sect ON cat.section_id = sect.id "
                "JOIN sphere sph ON sect.sphere_id = sph.id "
                "WHERE l.name LIKE ? COLLATE NOCASE "
                "OR l.url LIKE ? COLLATE NOCASE "
                "OR l.notes LIKE ? COLLATE NOCASE "
                "OR l.args LIKE ? COLLATE NOCASE "
                "ORDER BY l.name COLLATE NOCASE",
                (search_term, search_term, search_term, search_term),
                fetch_method="all",
            )
            return [row_to_dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error("Error searching links: %s", e)
            raise

    def get_links_by_args_pattern(self, pattern: str) -> list[dict[str, Any]]:
        """Return 'web' type links where args LIKE pattern."""
        try:
            rows = self._execute_with_error_handling(
                f"SELECT {LINK_ALL_COLUMNS} FROM link WHERE type = 'web' AND args LIKE ?",
                (pattern,),
                fetch_method="all",
            )
            return [row_to_dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error("Error selecting links by args pattern: %s", e)
            raise

    def update_link_notes(self, link_id: int, new_notes: str) -> None:
        """Update notes field for specified link."""
        try:
            self._execute_with_error_handling(
                "UPDATE link SET notes = ? WHERE id = ?",
                (new_notes, link_id),
            )

        except Exception as e:
            logger.error("Error updating notes for link %s: %s", link_id, e)
            raise

    def get_links_args_nonempty(self) -> list[dict[str, Any]]:
        """Return rows with non-empty args."""
        try:
            rows = self._execute_with_error_handling(
                "SELECT args FROM link WHERE args IS NOT NULL AND TRIM(args) != ''",
                fetch_method="all",
            )
            return [row_to_dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error("Error getting non-empty args: %s", e)
            raise

    def get_recent_links(self, limit: int = 10) -> list[LinkDict]:
        """Get recent links."""
        try:
            rows = self._execute_with_error_handling(
                f"""SELECT {LINK_ALL_COLUMNS} FROM link 
                   WHERE last_used IS NOT NULL 
                   ORDER BY last_used DESC 
                   LIMIT ?""",
                (limit,),
                fetch_method="all",
            )
            return [row_to_dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error("Error getting recent links: %s", e, exc_info=True)
            raise

    def get_favorite_links(self, limit: int | None = None) -> list[LinkDict]:
        """Get favorite links."""
        started_ts = time.perf_counter()
        try:
            conn_started_ts = time.perf_counter()
            conn = self.connection
            conn_ms = (time.perf_counter() - conn_started_ts) * 1000.0
            lock_wait_ms = 0.0
            sql_exec_ms = 0.0
            if isinstance(limit, int) and limit > 0:
                lock_started_ts = time.perf_counter()
                with db_lock:
                    lock_wait_ms = (time.perf_counter() - lock_started_ts) * 1000.0
                    sql_started_ts = time.perf_counter()
                    rows = conn.execute(
                        f"SELECT {LINK_ALL_COLUMNS} FROM link WHERE is_favorite=? ORDER BY position LIMIT ?",
                        (1, int(limit)),
                    ).fetchall()
                    sql_exec_ms = (time.perf_counter() - sql_started_ts) * 1000.0
            else:
                lock_started_ts = time.perf_counter()
                with db_lock:
                    lock_wait_ms = (time.perf_counter() - lock_started_ts) * 1000.0
                    sql_started_ts = time.perf_counter()
                    rows = conn.execute(
                        f"SELECT {LINK_ALL_COLUMNS} FROM link WHERE is_favorite=? ORDER BY position",
                        (1,),
                    ).fetchall()
                    sql_exec_ms = (time.perf_counter() - sql_started_ts) * 1000.0
            query_ms = lock_wait_ms + sql_exec_ms
            map_started_ts = time.perf_counter()
            mapped = [row_to_dict(row) for row in rows] if rows else []
            map_ms = (time.perf_counter() - map_started_ts) * 1000.0
            total_ms = (time.perf_counter() - started_ts) * 1000.0
            logger.info(
                "[Perf] get_favorite_links limit=%s rows=%s conn=%.2f ms lock_wait=%.2f ms sql_exec=%.2f ms query=%.2f ms map=%.2f ms total=%.2f ms",
                int(limit) if isinstance(limit, int) and limit > 0 else None,
                len(mapped),
                conn_ms,
                lock_wait_ms,
                sql_exec_ms,
                query_ms,
                map_ms,
                total_ms,
            )
            return mapped
        except Exception as e:
            logger.error("Error getting favorite links: %s", e, exc_info=True)
            raise

    def get_link_by_id(self, link_id: int) -> Optional[LinkDict]:
        """Get link by ID."""
        try:
            row = self._execute_with_error_handling(
                f"SELECT {LINK_ALL_COLUMNS} FROM link WHERE id = ?", (link_id,), fetch_method="one"
            )
            assert row is None or isinstance(row, sqlite3.Row)  # type: ignore[unreachable]
            return row_to_dict(row) if row else None
        except Exception as e:
            logger.error("Error getting link %s: %s", link_id, e, exc_info=True)
            raise

    def update_link_order(self, link_ids: list[int]) -> bool:
        """Update link order."""
        try:
            with self.transaction():
                for i, link_id in enumerate(link_ids):
                    self._execute_with_error_handling(
                        "UPDATE link SET position = ? WHERE id = ?", (i, link_id)
                    )
            return True
        except Exception as e:
            logger.error("Error updating link order: %s", e, exc_info=True)
            return False

    def batch_update_links(self, links_data: list[dict[str, Any]]) -> bool:
        """Batch update links in transaction."""
        if not links_data:
            return True

        # Prepare parameters for executemany: only valid records with id
        params: list[tuple] = []
        for link_data in links_data:
            link_id = link_data.get("id")
            if not isinstance(link_id, int) or link_id <= 0:
                continue
            params.append(
                (
                    link_data.get("position"),
                    link_data.get("category_id"),
                    link_id,
                )
            )

        if not params:
            return True

        sql = "UPDATE link SET position = ?, category_id = ? WHERE id = ?"

        try:
            with self.transaction():
                cursor = self._execute_many_with_error_handling(sql, params)
                # rowcount may be -1 for some drivers; wrap safely
                try:
                    affected = int(getattr(cursor, "rowcount", 0) or 0)
                except Exception:
                    affected = 0
                # Optionally: if affected less than passed, can log
                if affected < len(params):
                    logger.debug(
                        "batch_update_links: updated %s rows out of %s",
                        affected,
                        len(params),
                    )
            return True
        except Exception as e:
            logger.error("Error batch updating links: %s", e, exc_info=True)
            raise

    def get_next_position(self, category_id: int) -> int:
        """Get next position for new link in category."""
        try:
            result = self._execute_with_error_handling(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM link WHERE category_id = ?",
                (category_id,),
                fetch_method="one",
            )
            assert result is None or isinstance(result, sqlite3.Row)  # type: ignore[unreachable]
            return int(row_to_dict(result)["next_pos"]) if result else 0
        except (ValueError, TypeError, KeyError) as e:
            logger.error(
                "Error getting next position for category %s: %s",
                category_id,
                e,
                exc_info=True,
            )
            return 0

    def batch_upsert_links(self, links_data: list[dict[str, Any]]) -> list[int]:
        """Batch create/update links in one transaction."""
        if not links_data:
            return []

        created_ids: list[int] = []
        try:
            with self.transaction():
                created_ids.extend(self._upsert_links_no_tx(links_data))
            return created_ids
        except sqlite3.IntegrityError as e:
            # If something went wrong with uniqueness — propagate as DatabaseError
            raise DatabaseError(
                f"UNIQUE constraint failed during batch_upsert_links: {e}"
            ) from e
        except Exception as e:
            logger.error("Error batch saving links: %s", e)
            raise

    def _normalize_and_group_links(
        self, links_data: list[dict[str, Any]], all_fields: list[str]
    ) -> dict[int, list[dict[str, Any]]]:
        """Normalize input and group records by category_id."""
        by_cat: dict[int, list[dict[str, Any]]] = {}
        for raw in links_data:
            self._validate_required_fields(raw, ["category_id"], "link")
            
            # Use centralized validation
            validate_link_data(raw)
            
            # Use centralized normalization
            data = normalize_link_fields(raw, all_fields)

            raw.clear()
            raw.update(data)

            category_raw = data.get("category_id")
            if category_raw is None:
                raise ValidationError("Missing category_id for link batch item")
            try:
                category_id = int(category_raw)
            except (TypeError, ValueError) as exc:
                raise ValidationError("Invalid category_id for link batch item") from exc

            by_cat.setdefault(category_id, []).append(raw)
        return by_cat

    # Note: Old helper methods (_fetch_existing_maps, _assign_positions_for_items,
    # _build_update_params, _execute_updates_collect_missing, _insert_records_with_id,
    # _insert_records_no_id) have been moved to LinkBulkUpsertService for better separation
    # of concerns and testability.

    def _upsert_links_no_tx(self, links_data: list[dict[str, Any]]) -> list[int]:
        """Internal helper: upsert links without opening transaction.
        
        Uses LinkBulkUpsertService to simplify complex bulk upsert logic.
        """
        if not links_data:
            return []

        all_fields = [
            "id", "category_id", "name", "url", "type", "notes",
            "is_favorite", "last_used", "icon_path", "args", "position", "browser_key",
        ]

        # Normalize and group by category
        by_cat = self._normalize_and_group_links(links_data, all_fields)

        # Use service to handle upserts per category
        service = LinkBulkUpsertService(self.connection)
        created_ids: list[int] = []
        
        for category_id, items in by_cat.items():
            category_created_ids = service.upsert_links_for_category(
                category_id, items, all_fields
            )
            created_ids.extend(category_created_ids)

        return created_ids

    def move_links_bulk(self, link_ids: list[int], target_category_id: int) -> int:
        """Bulk move links to another category in one transaction.
        
        Args:
            link_ids: List of link IDs to move
            target_category_id: Target category ID
            
        Returns:
            Number of links moved
        """
        if not link_ids or not isinstance(target_category_id, int) or target_category_id <= 0:
            return 0
        
        unique_ids = self._validate_and_deduplicate_ids(link_ids, "link")
        if not unique_ids:
            return 0
        
        placeholders = build_in_clause_placeholders(len(unique_ids))
        try:
            with self.transaction():
                cursor = self._execute_with_error_handling(
                    f"UPDATE link SET category_id = ? WHERE id IN ({placeholders})",
                    (target_category_id, *unique_ids),
                )
                try:
                    moved = int(getattr(cursor, "rowcount", 0) or 0)
                except (ValueError, TypeError, AttributeError):
                    moved = 0
            logger.info("Bulk moved %d links to category %d", moved, target_category_id)
            return moved
        except Exception as e:
            logger.error("Error bulk moving links: %s", e)
            raise DatabaseError(f"Failed to perform bulk move: {e}") from e

    def batch_delete_links(self, link_ids: list[int]) -> int:
        """Batch delete links by ID list. Return number of deleted records."""
        if not link_ids:
            return 0

        unique_ids = self._validate_and_deduplicate_ids(link_ids, "link")
        if not unique_ids:
            return 0

        placeholders = build_in_clause_placeholders(len(unique_ids))
        try:
            with self.transaction():
                cursor = self._execute_with_error_handling(
                    f"DELETE FROM link WHERE id IN ({placeholders})",
                    tuple(unique_ids),
                )
                try:
                    deleted = int(getattr(cursor, "rowcount", 0) or 0)
                except (ValueError, TypeError, AttributeError):
                    deleted = 0
            return deleted
        except Exception as e:
            logger.error("Error batch deleting links: %s", e)
            raise DatabaseError(f"Failed to perform batch deletion: {e}") from e
