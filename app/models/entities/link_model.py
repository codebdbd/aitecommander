import datetime
import logging
import sqlite3
from typing import Any, Optional

from ..base.db_base import DatabaseBase, DatabaseError, ValidationError, row_to_dict
from ..types.link_type import LinkType

logger = logging.getLogger(__name__)


# Whitelist of allowed columns for link selection (single source of truth)
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


class LinkModel(DatabaseBase):
    """Unified model for working with links in database.

    Combines low-level DB operations and high-level methods
    for convenient link management.
    """

    def __init__(self, connection_manager):
        """Initializes LinkModel with connection manager."""
        super().__init__(connection_manager)

    def get_links(
        self,
        category_id: int,
        *,
        fields: Optional[list[str]] = None,
        all_fields: bool = False,
    ) -> list[dict[str, Any]]:
        """Returns list of links for specified category.

        Parameters:
        - fields: optional list of fields to select. Ignored if all_fields is specified.
        - all_fields: if True — selects all columns (equivalent to former get_links_for_category()).

        By default selects stable subset of columns for UI:
        [id, category_id, name, url, type, notes, is_favorite, last_used, icon_path, args, browser_key, position].
        """
        try:
            if all_fields:
                select_clause = "SELECT *"
            else:
                # If specific field list passed — use it, otherwise default subset as before
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
                # Filter user fields by whitelist
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
                # Fallback to default set when empty list after filtering
                if not use_fields:
                    use_fields = list(default_fields)
                # Simple fallback to * only if for some reason default is empty
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
        """Fetch links for multiple categories in a single set of batched queries."""
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
            placeholders = ",".join(["?"] * len(chunk))
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

    def get_all_links(self) -> list[dict[str, Any]]:
        """Return all links ordered by category and position."""
        try:
            rows = self._execute_with_error_handling(
                "SELECT id, category_id, name, url, type, notes, "
                "is_favorite, last_used, icon_path, args, browser_key, position "
                "FROM link ORDER BY category_id, position",
                fetch_method="all",
            )
            return [row_to_dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error("Error getting all links: %s", e, exc_info=True)
            raise

    def count_links_by_category(self, category_id: int) -> int:
        """Returns number of links for specified category (efficient count)."""
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
        """Returns dictionary {category_id: count} for set of categories in one query.

        Safely handles empty list, returning empty dictionary. In case of error
        returns empty dictionary and logs problem, maintaining UI stability.
        """
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
                placeholders = ",".join(["?"] * len(chunk))
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
        """Inserts or updates link record. Returns record ID.

        Transactions are not completed inside method. Commit/rollback performed
        by calling side (service/business layer) to enable grouping
        multiple operations into one atomic transaction.
        """
        self._validate_required_fields(link, ["category_id"], "link")

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

        # Create data copy considering all possible fields
        data = {field: link.get(field) for field in all_possible_fields}
        data["is_favorite"] = int(data.get("is_favorite", 0) or 0)
        # icon_path NOT NULL in schema: normalize to empty string if missing/None
        data["icon_path"] = data.get("icon_path", "") or ""
        # Link type normalization: Enum/string -> string value ('web', 'file', ...)
        try:
            data["type"] = LinkType.from_value(data.get("type", "web")).value
        except Exception:
            # Safe fallback
            data["type"] = LinkType.WEB.value

        logger.debug(
            "Upsert link: %s, browser_key=%s",
            data.get("name", "Untitled"),
            data.get("browser_key"),
        )
        logger.debug("Upsert link: full data=%s", data)

        try:
            if data["id"]:
                # Update or restore
                if data["position"] is None:
                    data["position"] = 0

                # Prepare data for update
                update_fields = [f for f in all_possible_fields if f != "id"]
                update_placeholders = ", ".join([f"{f}=?" for f in update_fields])
                update_values = [data[f] for f in update_fields]

                cursor = self._execute_with_error_handling(
                    f"UPDATE link SET {update_placeholders} WHERE id=?",
                    tuple(update_values + [data["id"]]),
                )

                # If record was not updated, insert new with specified ID
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
                # New record
                data["position"] = self._get_next_position(
                    "link", "category_id", data["category_id"]
                )

                # Silent duplicate handling on demand:
                # Duplicate = matching Name (name), Path (url) and Argument (args) within category
                existing = self.get_link_by_name_url_args(
                    int(data["category_id"] or 0),
                    str(data.get("name", "")),
                    str(data.get("url", "")),
                    str(data.get("args", "")),
                )
                if existing:
                    # Silently return existing ID without errors/warnings
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
            # Silently ignore duplicates by new uniqueness (category_id,name,url,args):
            # try to find existing record and return its ID
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
            # If not found — propagate as DatabaseError, but without extra noise
            raise DatabaseError(f"UNIQUE constraint failed: {e}") from e

    def get_link_by_unique_fields(
        self,
        category_id: int,
        url: str,
        args: str = "",
        link_type: str = "web",
        name: str = "",
    ):
        """Finds link by unique fields (category_id, url, args, type, name).

        Note: identical URLs are considered duplicates only if args, type and link name also match.
        """
        try:
            row = self._execute_with_error_handling(
                "SELECT * FROM link WHERE category_id=? AND url=? AND args=? AND type=? AND name=?",
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
        """Find link by triple (Name, Path, Argument) within category.

        User requirement: duplicate is matching name, url, args within category_id,
        type is ignored for this check.
        """
        try:
            row = self._execute_with_error_handling(
                "SELECT * FROM link WHERE category_id=? AND name=? AND url=? AND args=?",
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
        """Deletes link by its ID."""
        try:
            self._execute_with_error_handling(
                "DELETE FROM link WHERE id= ?", (link_id,)
            )

            logger.info("Deleted link with ID %s", link_id)
        except Exception as e:
            logger.error("Error deleting link: %s", e, exc_info=True)
            raise DatabaseError(f"Failed to delete link: {e}") from e

    def update_link_last_used(self, link_id: int):
        """Updates last used time for link."""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._execute_with_error_handling(
            "UPDATE link SET last_used = ? WHERE id = ?", (now, link_id)
        )

    def count_favorites(self) -> int:
        """Returns number of favorite links."""
        row = self._execute_with_error_handling(
            "SELECT COUNT(*) AS cnt FROM link WHERE is_favorite=1",
            fetch_method="one",
        )
        assert row is None or isinstance(row, sqlite3.Row)  # type: ignore[unreachable]
        return int(row_to_dict(row)["cnt"]) if row else 0

    def clear_favorites(self):
        """Resets favorite flag for all links."""
        try:
            self._execute_with_error_handling(
                "UPDATE link SET is_favorite=0 WHERE is_favorite=1"
            )

            logger.info("Cleared all favorite links")
        except Exception as e:
            logger.error("Error clearing favorites: %s", e)
            raise DatabaseError(f"Failed to clear favorites: {e}") from e

    def search_links(self, query: str):
        """Searches links throughout tree where name, URL or notes contain query substring."""
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
        """Returns 'web' type links where args LIKE pattern.

        Example pattern: '--profile-directory=%'
        """
        try:
            rows = self._execute_with_error_handling(
                "SELECT * FROM link WHERE type = 'web' AND args LIKE ?",
                (pattern,),
                fetch_method="all",
            )
            return [row_to_dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error("Error selecting links by args pattern: %s", e)
            raise

    def update_link_notes(self, link_id: int, new_notes: str) -> None:
        """Updates notes field for specified link."""
        try:
            self._execute_with_error_handling(
                "UPDATE link SET notes = ? WHERE id = ?",
                (new_notes, link_id),
            )

        except Exception as e:
            logger.error("Error updating notes for link %s: %s", link_id, e)
            raise

    def get_links_args_nonempty(self) -> list[dict[str, Any]]:
        """Returns rows with non-empty args (args column only)."""
        try:
            rows = self._execute_with_error_handling(
                "SELECT args FROM link WHERE args IS NOT NULL AND TRIM(args) != ''",
                fetch_method="all",
            )
            return [row_to_dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error("Error getting non-empty args: %s", e)
            raise

    # === High-level methods for convenience ===

    def get_recent_links(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent links."""
        try:
            rows = self._execute_with_error_handling(
                """SELECT * FROM link 
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

    def get_favorite_links(self) -> list[dict[str, Any]]:
        """Get favorite links."""
        try:
            rows = self._execute_with_error_handling(
                "SELECT * FROM link WHERE is_favorite=? ORDER BY position",
                (1,),
                fetch_method="all",
            )
            return [row_to_dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error("Error getting favorite links: %s", e, exc_info=True)
            raise

    def get_link_by_id(self, link_id: int) -> Optional[dict[str, Any]]:
        """Get link by ID."""
        try:
            row = self._execute_with_error_handling(
                "SELECT * FROM link WHERE id = ?", (link_id,), fetch_method="one"
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
                "SELECT COALESCE(MAX(position), 0) + 1 AS next_pos FROM link WHERE category_id = ?",
                (category_id,),
                fetch_method="one",
            )
            assert result is None or isinstance(result, sqlite3.Row)  # type: ignore[unreachable]
            return int(row_to_dict(result)["next_pos"]) if result else 1
        except Exception as e:
            logger.error(
                "Error getting next position for category %s: %s",
                category_id,
                e,
                exc_info=True,
            )
            return 1

    # get_links_for_category was merged with get_links (all_fields=True parameter)

    def batch_upsert_links(self, links_data: list[dict[str, Any]]) -> list[int]:
        """Batch create/update links in one transaction.

        - Does not commit after each record — transaction will complete with single commit.
        - Updates input dictionaries (links_data) with assigned IDs for new records.
        - Returns list of IDs created within this operation (new records only).
        """
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

    # === Dedicated steps for batch upsert (without transaction) ===

    def _normalize_and_group_links(
        self, links_data: list[dict[str, Any]], all_fields: list[str]
    ) -> dict[int, list[dict[str, Any]]]:
        """Normalizes input and groups records by `category_id`.

        - Validates required fields.
        - Fills default values and converts types.
        - Updates input elements in-place.
        - Returns dictionary {category_id: [items...]}
        """
        by_cat: dict[int, list[dict[str, Any]]] = {}
        for raw in links_data:
            self._validate_required_fields(raw, ["category_id"], "link")
            data = {field: raw.get(field) for field in all_fields}
            data["name"] = data.get("name", "") or ""
            data["url"] = data.get("url", "") or ""
            data["args"] = data.get("args", "") or ""
            # Normalize type to string (in case Enum was passed)
            try:
                data["type"] = LinkType.from_value(data.get("type", "web")).value
            except Exception:
                data["type"] = LinkType.WEB.value
            data["notes"] = data.get("notes", "") or ""
            data["is_favorite"] = int(data.get("is_favorite", 0) or 0)
            data["icon_path"] = data.get("icon_path", "default.ico") or "default.ico"
            # position and browser_key remain as is (can be None)

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

    def _fetch_existing_maps(
        self, category_id: int
    ) -> tuple[
        dict[tuple[str, str, str], dict[str, Any]],
        dict[int, dict[str, Any]],
        int,
    ]:
        """Gets existing links and max(position) for category.

        Returns tuple (existing_by_key, existing_by_id, max_pos).
        key = (name, url, args)
        """
        rows_result = self._execute_with_error_handling(
            "SELECT id, name, url, args, position FROM link WHERE category_id=?",
            (category_id,),
            fetch_method="all",
        )
        rows = self._ensure_row_list(rows_result)
        existing_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
        existing_by_id: dict[int, dict[str, Any]] = {}
        max_pos = -1
        for row in rows:
            rid = row["id"]
            rname = row["name"]
            rurl = row["url"]
            rargs = row["args"]
            rpos = row["position"]
            existing_by_id[int(rid)] = {
                "id": int(rid),
                "name": rname or "",
                "url": rurl or "",
                "args": rargs or "",
                "position": rpos if rpos is not None else -1,
            }
            existing_by_key[(rname or "", rurl or "", rargs or "")] = existing_by_id[
                int(rid)
            ]
            if rpos is not None:
                try:
                    if int(rpos) > max_pos:
                        max_pos = int(rpos)
                except Exception:
                    pass
        return existing_by_key, existing_by_id, max_pos

    def _assign_positions_for_items(
        self, items: list[dict[str, Any]], start_pos: int
    ) -> None:
        """Assigns position to items that don't have it set."""
        next_pos = start_pos
        for item in items:
            if item.get("position") is None:
                item["position"] = next_pos
                next_pos += 1

    def _build_update_params(
        self,
        items: list[dict[str, Any]],
        existing_by_key: dict[tuple[str, str, str], dict[str, Any]],
    ) -> tuple[list[tuple[Any, ...]], list[dict[str, Any]]]:
        """Forms parameters for UPDATE and list of inserts without id."""
        updates: list[tuple[Any, ...]] = []
        inserts_no_id: list[dict[str, Any]] = []
        for item in items:
            key = (item.get("name", ""), item.get("url", ""), item.get("args", ""))
            iid = item.get("id")
            if iid:
                updates.append(
                    (
                        item.get("category_id"),
                        item.get("name"),
                        item.get("url"),
                        item.get("type"),
                        item.get("notes"),
                        int(item.get("is_favorite", 0) or 0),
                        item.get("last_used"),
                        item.get("icon_path"),
                        item.get("args"),
                        item.get("browser_key"),
                        item.get("position", 0)
                        if item.get("position") is not None
                        else 0,
                        int(iid),
                    )
                )
            else:
                ex = existing_by_key.get(key)
                if ex:
                    item["id"] = ex["id"]
                    updates.append(
                        (
                            item.get("category_id"),
                            item.get("name"),
                            item.get("url"),
                            item.get("type"),
                            item.get("notes"),
                            int(item.get("is_favorite", 0) or 0),
                            item.get("last_used"),
                            item.get("icon_path"),
                            item.get("args"),
                            item.get("browser_key"),
                            item.get("position", 0)
                            if item.get("position") is not None
                            else 0,
                            ex["id"],
                        )
                    )
                else:
                    inserts_no_id.append(item)
        return updates, inserts_no_id

    def _execute_updates_collect_missing(
        self, updates: list[tuple[Any, ...]]
    ) -> list[dict[str, Any]]:
        """Выполняет пакетные UPDATE и собирает записи для последующей вставки с фиксированным id.

        Возвращает список словарей для вставки с заданным `id` (inserts_with_id).
        """
        inserts_with_id: list[dict[str, Any]] = []
        if not updates:
            return inserts_with_id

        update_sql = (
            "UPDATE link SET category_id=?, name=?, url=?, type=?, notes=?, "
            "is_favorite=?, last_used=?, icon_path=?, args=?, browser_key=?, position=? WHERE id=?"
        )
        try:
            self.connection.executemany(update_sql, updates)
        except sqlite3.IntegrityError as e:
            raise DatabaseError(
                f"UNIQUE constraint failed during batch update: {e}"
            ) from e

        update_ids = [int(p[-1]) for p in updates]
        if update_ids:
            placeholders = ",".join(["?"] * len(update_ids))
            existed_rows = self._execute_with_error_handling(
                f"SELECT id FROM link WHERE id IN ({placeholders})",
                tuple(update_ids),
                fetch_method="all",
            )
            existed_ids = {
                int(r[0] if isinstance(r, tuple) else r["id"])
                for r in (existed_rows or [])
            }
            missing_ids = [iid for iid in update_ids if iid not in existed_ids]

            if missing_ids:
                params_by_id = {int(p[-1]): p for p in updates}
                for iid in missing_ids:
                    params = params_by_id.get(int(iid))
                    if not params:
                        continue
                    inserts_with_id.append(
                        {
                            "id": int(iid),
                            "category_id": params[0],
                            "name": params[1],
                            "url": params[2],
                            "type": params[3],
                            "notes": params[4],
                            "is_favorite": params[5],
                            "last_used": params[6],
                            "icon_path": params[7],
                            "args": params[8],
                            "browser_key": params[9],
                            "position": params[10],
                        }
                    )
        return inserts_with_id

    def _insert_records_with_id(
        self,
        inserts_with_id: list[dict[str, Any]],
        all_fields: list[str],
        created_ids: list[int],
    ) -> None:
        """Вставляет записи с фиксированным id (executemany) и добавляет их в created_ids."""
        if not inserts_with_id:
            return
        insert_fields = all_fields
        placeholders = ", ".join(["?"] * len(insert_fields))
        params_with_id = [
            tuple(rec.get(f) for f in insert_fields) for rec in inserts_with_id
        ]
        try:
            # Используем защищённый executemany с удержанием db_lock
            self._execute_many_with_error_handling(
                f"INSERT INTO link ({', '.join(insert_fields)}) VALUES ({placeholders})",
                params_with_id,
            )
        except sqlite3.IntegrityError as e:
            raise DatabaseError(f"Integrity error on inserts_with_id: {e}") from e
        for rec in inserts_with_id:
            try:
                iid = int(rec.get("id") or 0)
                if iid:
                    created_ids.append(iid)
            except Exception:
                pass

    def _insert_records_no_id(
        self,
        inserts_no_id: list[dict[str, Any]],
        all_fields: list[str],
        existing_by_key: dict[tuple[str, str, str], dict[str, Any]],
        created_ids: list[int],
    ) -> None:
        """Поштучно вставляет записи без id, обновляет входные элементы и created_ids.

        Следует согласованному хотфиксу: без временной таблицы, поштучные INSERT.
        """
        if not inserts_no_id:
            return
        columns = [f for f in all_fields if f != "id"]
        placeholders = ", ".join(["?"] * len(columns))
        insert_sql = f"INSERT INTO link ({', '.join(columns)}) VALUES ({placeholders})"
        for rec in inserts_no_id:
            params = tuple(rec.get(c) for c in columns)
            try:
                cur = self._execute_with_error_handling(insert_sql, params)
                try:
                    new_id = int(getattr(cur, "lastrowid", 0) or 0)
                except Exception:
                    new_id = 0
                if new_id:
                    rec["id"] = new_id
                    key_simple = (
                        rec.get("name", ""),
                        rec.get("url", ""),
                        rec.get("args", ""),
                    )
                    if key_simple not in existing_by_key:
                        created_ids.append(new_id)
                        existing_by_key[key_simple] = {
                            "id": new_id,
                            "position": rec.get("position", 0),
                        }
            except sqlite3.IntegrityError:
                row = self._execute_with_error_handling(
                    "SELECT id FROM link WHERE category_id=? AND name=? AND url=? AND args=?",
                    (
                        rec.get("category_id"),
                        rec.get("name", ""),
                        rec.get("url", ""),
                        rec.get("args", ""),
                    ),
                    fetch_method="one",
                )
                if row:
                    assert row is None or isinstance(row, sqlite3.Row)  # type: ignore[unreachable]
                    rec["id"] = (
                        row[0] if isinstance(row, tuple) else row_to_dict(row)["id"]
                    )

    def _upsert_links_no_tx(self, links_data: list[dict[str, Any]]) -> list[int]:
        """Внутренний хелпер: апсерт ссылок без открытия транзакции и без commit().

        - Идентичная логика batch_upsert_links, но предполагает внешнюю транзакцию.
        - Обновляет входные словари `links_data` установленными ID для новых записей.
        - Возвращает список созданных ID.
        """
        if not links_data:
            return []

        created_ids: list[int] = []

        # Поля должны оставаться синхронными с upsert_link
        all_fields = [
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

        # 1) Нормализация и группировка
        by_cat = self._normalize_and_group_links(links_data, all_fields)

        # 2..6) Для каждой категории отрабатываем шаги отдельно
        for category_id, items in by_cat.items():
            existing_by_key, _existing_by_id, max_pos = self._fetch_existing_maps(
                category_id
            )

            # 3) Назначаем позиции, если не заданы
            self._assign_positions_for_items(items, max_pos + 1)

            # 4) Формируем обновления и вставки без id
            updates, inserts_no_id = self._build_update_params(items, existing_by_key)

            # 5) Выполняем обновления и собираем вставки с фиксированным id
            inserts_with_id = self._execute_updates_collect_missing(updates)

            # 6a) Выполняем вставки с фиксированным id
            self._insert_records_with_id(inserts_with_id, all_fields, created_ids)

            # 6b) Поштучные INSERT без id (согласованный хотфикс)
            self._insert_records_no_id(
                inserts_no_id, all_fields, existing_by_key, created_ids
            )

        return created_ids

    def batch_delete_links(self, link_ids: list[int]) -> int:
        """Пакетное удаление ссылок по списку ID в одной транзакции.

        Возвращает количество фактически удалённых записей.
        """
        if not link_ids:
            return 0

        # Фильтрация валидных положительных целых и дедупликация (с сохранением порядка)
        valid_ids = [int(x) for x in link_ids if isinstance(x, int) and x > 0]
        unique_ids = list(dict.fromkeys(valid_ids))
        if not unique_ids:
            return 0

        placeholders = ",".join(["?"] * len(unique_ids))
        try:
            with self.transaction():
                cursor = self._execute_with_error_handling(
                    f"DELETE FROM link WHERE id IN ({placeholders})",
                    tuple(unique_ids),
                )
                try:
                    deleted = int(getattr(cursor, "rowcount", 0) or 0)
                except Exception:
                    deleted = 0
            return deleted
        except Exception as e:
            logger.error("Error batch deleting links: %s", e)
            raise DatabaseError(f"Failed to perform batch deletion: {e}") from e
