"""
CategoryModel - model for working with categories in database.
"""

import logging
from typing import Any, Optional

from ..base.db_base import DatabaseBase, ValidationError, row_to_dict
from .constants import CATEGORY_BULK_UUID_FIELD

logger = logging.getLogger(__name__)


class CategoryModel(DatabaseBase):
    """Model for working with categories."""

    def __init__(self, database):
        """Initialization of category model."""
        super().__init__(database)

    def get_categories(self, section_id: int) -> list[dict[str, Any]]:
        """Returns list of categories for specified section in dict format."""
        rows = self._execute_with_error_handling(
            "SELECT id, name, section_id, position, icon_path FROM category "
            "WHERE section_id=? ORDER BY position",
            (section_id,),
            fetch_method="all",
        )
        return [row_to_dict(row) for row in rows] if rows else []

    def get_categories_for_sections(
        self, section_ids: list[int]
    ) -> list[dict[str, Any]]:
        """Returns categories for multiple sections in one query in dict format."""
        if not section_ids:
            return []

        placeholders = ",".join("?" * len(section_ids))
        query = f"""
            SELECT id, name, section_id, position, icon_path 
            FROM category 
            WHERE section_id IN ({placeholders}) 
            ORDER BY section_id, position
        """
        rows = self._execute_with_error_handling(query, section_ids, fetch_method="all")
        return [row_to_dict(row) for row in rows] if rows else []

    def get_category_by_id(self, category_id: int) -> Optional[dict[str, Any]]:
        """Returns category by its ID in dict format."""
        row = self._execute_with_error_handling(
            "SELECT * FROM category WHERE id= ?", (category_id,), fetch_method="one"
        )
        return row_to_dict(row) if row else None

    def get_category_hierarchy(self, category_id: int) -> Optional[dict[str, int]]:
        """Get category hierarchy (sphere -> section -> category).

        Args:
            category_id: Category ID

        Returns:
            Dict with sphere_id, section_id, category_id or None on error
        """
        result = self._execute_with_error_handling(
            """SELECT s.sphere_id, c.section_id 
               FROM category c 
               JOIN section s ON c.section_id = s.id 
               WHERE c.id = ?""",
            (category_id,),
            fetch_method="one",
        )

        if result:
            result_dict = row_to_dict(result)
            return {
                "sphere_id": result_dict["sphere_id"],
                "section_id": result_dict["section_id"],
                "category_id": category_id,
            }
        return None

    def insert_category(self, data: dict[str, Any]) -> Optional[int]:
        """Inserts new category and returns its ID.

        Args:
            data: Category data dictionary, must contain 'name' and 'section_id'

        Returns:
            int: ID of created category or None if category with same name already exists
        """
        self._validate_required_fields(data, ["name", "section_id"], "category")

        # Input normalization: remove extra spaces around name
        try:
            name_norm = str(data["name"]).strip()
        except Exception:
            name_norm = str(data["name"])  # just in case
        data = dict(data)
        data["name"] = name_norm

        # Check if category with this name already exists in this section
        cursor = self._execute_with_error_handling(
            "SELECT id FROM category WHERE section_id = ? AND name = ? COLLATE NOCASE",
            (data["section_id"], data["name"]),
            fetch_method="one",
        )
        if cursor is not None:
            # Category with this name already exists in this section
            logger.warning(
                "Category '%s' already exists in section %s",
                data["name"],
                data["section_id"],
            )
            return None

        position = self._get_next_position("category", "section_id", data["section_id"])
        cursor = self._execute_with_error_handling(
            "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
            (data["name"], data["section_id"], data.get("icon_path", ""), position),
        )
        logger.info("Добавлена новая категория: %s", data["name"])
        return cursor.lastrowid

    def _validate_and_prepare_items(
        self, items: list[dict[str, Any]]
    ) -> tuple[dict[int, tuple[int, str, str]], bool]:
        """Validate input items and prepare normalized metadata.

        Returns: (prepared_info, has_uuid_tokens)
        """
        prepared_info: dict[int, tuple[int, str, str]] = {}
        has_uuid_tokens = False

        for it in items:
            self._validate_required_fields(it or {}, ["name", "section_id"], "category")
            try:
                sid = int(it.get("section_id"))
            except Exception as e:
                raise ValidationError(
                    "Incorrect section_id in one of batch elements"
                ) from e
            raw_name = it.get("name")
            name_canon = str(raw_name).strip() if raw_name is not None else ""
            name_norm = name_canon.lower()
            prepared_info[id(it)] = (sid, name_canon, name_norm)

            if not has_uuid_tokens:
                token_raw = it.get(CATEGORY_BULK_UUID_FIELD)
                if token_raw is not None and str(token_raw).strip():
                    has_uuid_tokens = True

        return prepared_info, has_uuid_tokens

    def _group_by_section(
        self,
        items: list[dict[str, Any]],
        prepared_info: dict[int, tuple[int, str, str]],
    ) -> dict[int, list[dict[str, Any]]]:
        """Group items by section_id."""
        by_section: dict[int, list[dict[str, Any]]] = {}
        for it in items:
            info = prepared_info.get(id(it))
            if not info:
                continue
            sid, _, _ = info
            by_section.setdefault(sid, []).append(it)
        return by_section

    def _load_max_positions(self, section_ids: list[int]) -> dict[int, Optional[int]]:
        """Load MAX(position) for all sections in one query."""
        max_pos_map: dict[int, Optional[int]] = {}
        if not section_ids:
            return max_pos_map

        placeholders = ",".join(["?"] * len(section_ids))
        query = (
            f"SELECT section_id, MAX(position) AS max_pos "
            f"FROM category WHERE section_id IN ({placeholders}) "
            f"GROUP BY section_id"
        )
        rows = self._execute_with_error_handling(
            query, tuple(section_ids), fetch_method="all"
        )
        for row in rows or []:
            row_dict = row_to_dict(row)
            max_pos_map[row_dict["section_id"]] = row_dict["max_pos"]
        return max_pos_map

    def _load_existing_names(self, section_ids: list[int]) -> dict[int, set]:
        """Load existing category names for all sections in one query."""
        existing_names_by_section: dict[int, set] = {}
        if not section_ids:
            return existing_names_by_section

        placeholders = ",".join(["?"] * len(section_ids))
        query_names = (
            f"SELECT section_id, LOWER(name) AS lname FROM category "
            f"WHERE section_id IN ({placeholders})"
        )
        rows = self._execute_with_error_handling(
            query_names, tuple(section_ids), fetch_method="all"
        )
        for r in rows or []:
            sid = int(r["section_id"]) if r["section_id"] is not None else None
            if sid is None:
                continue
            nm = str(r["lname"]).strip().lower()
            if not nm:
                continue
            existing_names_by_section.setdefault(sid, set()).add(nm)
        return existing_names_by_section

    def _build_insert_batch(
        self,
        by_section: dict[int, list[dict[str, Any]]],
        prepared_info: dict[int, tuple[int, str, str]],
        max_pos_map: dict[int, Optional[int]],
        existing_names_by_section: dict[int, set],
    ) -> list[tuple]:
        """Build batch insert parameters, skipping duplicates."""
        batched_params: list[tuple] = []

        for section_id, group in by_section.items():
            max_pos = max_pos_map.get(section_id)
            start_pos = (max_pos + 1) if (max_pos is not None) else 0
            pos = start_pos
            existing_names = existing_names_by_section.get(section_id, set())
            seen_in_batch = set()

            for it in group:
                info = prepared_info.get(id(it))
                if not info:
                    continue
                _, name_canon, name_norm = info
                if not name_norm:
                    continue
                if name_norm in existing_names or name_norm in seen_in_batch:
                    continue
                seen_in_batch.add(name_norm)

                icon_path = it.get("icon_path", "")
                batched_params.append((name_canon, section_id, icon_path, pos))
                pos += 1

        return batched_params

    def _collect_category_pairs(
        self,
        by_section: dict[int, list[dict[str, Any]]],
        prepared_info: dict[int, tuple[int, str, str]],
    ) -> list[tuple[int, str]]:
        """Collect unique (section_id, name) pairs for DB query."""
        pairs: list[tuple] = []
        seen = set()
        for section_id, group in by_section.items():
            for g in group:
                info = prepared_info.get(id(g))
                if not info:
                    continue
                _, nm_canon, _ = info
                key = (section_id, nm_canon)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(key)
        return pairs

    def _query_categories_by_pairs(
        self, pairs: list[tuple[int, str]]
    ) -> list[dict[str, Any]]:
        """Query categories from DB by (section_id, name) pairs."""
        if not pairs:
            return []

        placeholders = ",".join(["(?, ?)"] * len(pairs))
        flat_params: list[Any] = []
        for sid, nm in pairs:
            flat_params.extend([sid, nm])

        query = (
            "SELECT id, name, section_id, position, icon_path "
            "FROM category WHERE (section_id, name) IN (" + placeholders + ") "
            "ORDER BY section_id, position"
        )
        rows = self._execute_with_error_handling(
            query, tuple(flat_params), fetch_method="all"
        )
        return [dict(r) for r in (rows or [])]

    def _build_category_index(
        self, rows: list[dict[str, Any]]
    ) -> dict[tuple[int, str], dict[str, Any]]:
        """Build index of categories by (section_id, lowercase_name)."""
        rows_by_key: dict[tuple[int, str], dict[str, Any]] = {}
        for r in rows:
            try:
                section_id = (
                    int(r["section_id"]) if r["section_id"] is not None else None
                )
            except Exception:
                section_id = None
            if section_id is None:
                continue
            name_value = str(r["name"]).strip().lower() if r["name"] is not None else ""
            rows_by_key[(section_id, name_value)] = r
        return rows_by_key

    def _attach_uuid_tokens(
        self,
        rows_by_key: dict[tuple[int, str], dict[str, Any]],
        items: list[dict[str, Any]],
        prepared_info: dict[int, tuple[int, str, str]],
    ) -> list[dict[str, Any]]:
        """Attach UUID tokens to fetched categories."""
        result: list[dict[str, Any]] = []
        for it in items:
            info = prepared_info.get(id(it))
            if not info:
                continue
            section_id, _, name_norm = info
            if not name_norm:
                continue
            row = rows_by_key.get((section_id, name_norm))
            if not row:
                continue
            payload = row_to_dict(row)
            token_raw = it.get(CATEGORY_BULK_UUID_FIELD)
            token = str(token_raw).strip() if token_raw is not None else ""
            if token:
                payload[CATEGORY_BULK_UUID_FIELD] = token
            result.append(payload)
        return result

    def _fetch_inserted_categories(
        self,
        by_section: dict[int, list[dict[str, Any]]],
        prepared_info: dict[int, tuple[int, str, str]],
        has_uuid_tokens: bool,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Fetch inserted categories from DB and attach UUID tokens if needed."""
        pairs = self._collect_category_pairs(by_section, prepared_info)
        if not pairs:
            return []

        rows = self._query_categories_by_pairs(pairs)
        if not has_uuid_tokens:
            return rows

        rows_by_key = self._build_category_index(rows)
        return self._attach_uuid_tokens(rows_by_key, items, prepared_info)

    def insert_categories_bulk(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Bulk category insertion with atomic transaction.

        - Expects list of dictionaries with keys at least: 'name', 'section_id'.
        - Additionally supports 'icon_path'.
        - Duplicates (UNIQUE(section_id, name)) are silently ignored (INSERT OR IGNORE).
        - Positions calculated efficiently: sequentially for each section_id group
          from current MAX(position) + 1.

        Returns list of categories (dict) for all passed names by sections
        after operation (both new and existing), so calling side can
        synchronize UI. Order in result: by section_id, then by position.
        """
        if not items:
            return []

        prepared_info, has_uuid_tokens = self._validate_and_prepare_items(items)
        by_section = self._group_by_section(items, prepared_info)

        try:
            with self.transaction():
                section_ids = list(by_section.keys())
                max_pos_map = self._load_max_positions(section_ids)
                existing_names_by_section = self._load_existing_names(section_ids)

                batched_params = self._build_insert_batch(
                    by_section, prepared_info, max_pos_map, existing_names_by_section
                )

                # Insert with single executemany
                self._execute_many_with_error_handling(
                    "INSERT OR IGNORE INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
                    batched_params,
                )

                return self._fetch_inserted_categories(
                    by_section, prepared_info, has_uuid_tokens, items
                )
        except Exception:
            raise

    def update_category(self, category_id: int, data: dict[str, Any]):
        """Updates existing category."""
        return self._update_entity(
            "category",
            category_id,
            data,
            ["name", "section_id", "icon_path", "position"],
        )

    def delete_category(self, category_id: int):
        """Deletes category by its ID along with all its links (atomically)."""
        with self.transaction():
            # First delete all category links
            self._execute_with_error_handling(
                "DELETE FROM link WHERE category_id=?", (category_id,)
            )
            # Then delete the category itself
            self._execute_with_error_handling(
                "DELETE FROM category WHERE id=?", (category_id,)
            )
        logger.info("Deleted category with ID %s and all its links", category_id)

    def delete_categories_bulk(self, category_ids: list[int]) -> int:
        """Bulk deletion of multiple categories (and their links) in one transaction.

        Returns number of deleted categories. Ignores invalid IDs.
        """
        if not category_ids:
            return 0

        # Keep only valid positive integer IDs (excluding bool) and remove duplicates
        ids = [
            int(x)
            for x in category_ids
            if isinstance(x, int) and not isinstance(x, bool) and x > 0
        ]
        # Deduplication preserving first occurrence order
        unique_ids = list(dict.fromkeys(ids))
        if not unique_ids:
            return 0

        # Chunking to comply with SQLite parameter limit (~999)
        CHUNK = 900

        # 0) Collect affected sections in chunks
        affected_sections: list[int] = []
        for i in range(0, len(unique_ids), CHUNK):
            chunk = unique_ids[i : i + CHUNK]
            placeholders = ",".join(["?"] * len(chunk))
            rows = self._execute_with_error_handling(
                f"SELECT DISTINCT section_id FROM category WHERE id IN ({placeholders})",
                tuple(chunk),
                fetch_method="all",
            )
            affected_sections.extend(int(r["section_id"]) for r in (rows or []))

        deleted_categories = 0
        with self.transaction():
            # 1) Delete links and categories in chunks to not exceed parameter limit
            for i in range(0, len(unique_ids), CHUNK):
                chunk = unique_ids[i : i + CHUNK]
                placeholders = ",".join(["?"] * len(chunk))
                # Delete links for chunk categories
                self._execute_with_error_handling(
                    f"DELETE FROM link WHERE category_id IN ({placeholders})",
                    tuple(chunk),
                )
                # Pre-count category records in chunk,
                # to have exact value in case cursor.rowcount is missing
                pre_count_row = self._execute_with_error_handling(
                    f"SELECT COUNT(*) as cnt FROM category WHERE id IN ({placeholders})",
                    tuple(chunk),
                    fetch_method="one",
                )
                if pre_count_row is None:
                    pre_count = 0
                else:
                    try:
                        pre_count = int(
                            row_to_dict(pre_count_row)["cnt"]
                        )  # sqlite3.Row converted to dict
                    except Exception:
                        pre_count = 0

                # Delete the categories themselves
                cursor = self._execute_with_error_handling(
                    f"DELETE FROM category WHERE id IN ({placeholders})",
                    tuple(chunk),
                )
                try:
                    # Prefer to use actual rowcount if available
                    rc = cursor.rowcount
                    deleted_categories += int(rc)
                except AttributeError:
                    # Log missing rowcount and use pre-count
                    logger.warning(
                        "delete_categories_bulk: cursor.rowcount not available; using pre-count (%s) for chunk %s",
                        pre_count,
                        chunk,
                    )
                    deleted_categories += pre_count

            # 2) Reindex positions in affected sections to remove "gaps"
            try:
                # Deduplication and filter valid ids
                uniq_sections = list(
                    dict.fromkeys(
                        [s for s in affected_sections if isinstance(s, int) and s > 0]
                    )
                )
                for sid in uniq_sections:
                    self._reindex_positions(sid)
            except Exception:
                # Don't interrupt deletion, but log at top level
                logger.warning("Failed to reindex category positions after deletion")

        logger.info(
            "Bulk deleted categories (count=%s), ids=%s",
            deleted_categories,
            unique_ids,
        )
        return deleted_categories

    def move_categories_to_section_bulk(
        self, category_ids: list[int], target_section_id: int, base_row: int = 0
    ) -> list[int]:
        """Atomically moves multiple categories to target section in one transaction.

        - Skips categories that would cause name duplicate in target section
          (UNIQUE(section_id, name)).
        - Positions for moved categories assigned sequentially starting from base_row.
        - Reindexes positions in affected source sections and target section.

        Returns list of actually moved ids in application order.
        """
        # Input data validation
        if (
            not category_ids
            or not isinstance(target_section_id, int)
            or target_section_id <= 0
        ):
            return []

        # Keep only valid positive integer IDs (excluding bool) and remove duplicates (preserving order)
        ids = [
            int(x)
            for x in category_ids
            if isinstance(x, int) and not isinstance(x, bool) and x > 0
        ]
        unique_ids = list(dict.fromkeys(ids))
        if not unique_ids:
            return []

        # Get category data (id, name, section_id, position), filter existing
        placeholders = ",".join(["?"] * len(unique_ids))
        rows = self._execute_with_error_handling(
            f"SELECT id, name, section_id, position FROM category WHERE id IN ({placeholders})",
            tuple(unique_ids),
            fetch_method="all",
        )
        if not rows:
            return []

        # Dictionary by id
        data_by_id: dict[int, dict] = {int(r["id"]): dict(r) for r in rows}

        # Preserve user-defined order (sequence unique_ids)
        ordered_existing_ids = [cid for cid in unique_ids if cid in data_by_id]

        # Names already occupied in target section
        existing_names_rows = self._execute_with_error_handling(
            "SELECT LOWER(name) AS name FROM category WHERE section_id = ?",
            (target_section_id,),
            fetch_method="all",
        )
        existing_names = {
            str(r["name"]).strip().lower() for r in (existing_names_rows or [])
        }

        # Filter by name duplicates (in target section)
        to_move_ids: list[int] = []
        for cid in ordered_existing_ids:
            nm = str(data_by_id[cid].get("name", "")).strip().lower()
            # If duplicate already exists in target — skip
            if nm in existing_names:
                continue
            to_move_ids.append(cid)
            existing_names.add(nm)  # reserve name to exclude repeats within set

        if not to_move_ids:
            return []

        # Collect source sections for reindexing after move
        source_sections = [
            int(data_by_id[cid].get("section_id", 0) or 0) for cid in to_move_ids
        ]
        source_sections = [
            sid for sid in source_sections if sid and sid != target_section_id
        ]
        uniq_source_sections = list(dict.fromkeys(source_sections))

        # Apply updates in one transaction
        with self.transaction():
            # Update section_id and temporary positions for moved categories
            updates = []
            pos = int(base_row) if isinstance(base_row, int) and base_row >= 0 else 0
            for cid in to_move_ids:
                updates.append((target_section_id, pos, cid))
                pos += 1
            self._execute_many_with_error_handling(
                "UPDATE category SET section_id = ?, position = ? WHERE id = ?",
                updates,
            )

            # Reindex source sections (close gaps)
            try:
                for sid in uniq_source_sections:
                    self._reindex_positions(sid)
            except Exception:
                logger.warning(
                    "Failed to reindex source sections after move",
                    exc_info=False,
                )

            # Reindex target section to synchronize positions
            try:
                self._reindex_positions(target_section_id)
            except Exception:
                logger.warning(
                    "Failed to reindex target section after move",
                    exc_info=False,
                )

        logger.info(
            f"Bulk category move (count={len(to_move_ids)}) to section {target_section_id}, ids={to_move_ids}"
        )
        return to_move_ids

    def _reindex_positions(self, section_id: int) -> None:
        """Reindex position field for all section categories sequentially from 0.

        Executed without own begin/commit, assuming external transaction context.
        """
        # Get category ids in required order
        rows = self._execute_with_error_handling(
            "SELECT id FROM category WHERE section_id = ? ORDER BY position, id",
            (section_id,),
            fetch_method="all",
        )
        ids_in_order = [int(r["id"]) for r in (rows or [])]
        if not ids_in_order:
            return
        # Prepare batch of position updates 0..n-1
        updates = [(pos, cid) for pos, cid in enumerate(ids_in_order)]
        self._execute_many_with_error_handling(
            "UPDATE category SET position = ? WHERE id = ?",
            updates,
        )

    def upsert_category(self, category_data: dict[str, Any]) -> int:
        """Inserts or updates category. If category with this id doesn't exist, inserts new with this id."""
        # Canonicalize name: remove spaces around
        data = dict(category_data)  # don't mutate incoming dict
        if "name" in data:
            try:
                data["name"] = str(data["name"]).strip()
            except Exception:
                data["name"] = str(data["name"])

        if "id" in data and data["id"]:
            # Execute atomically under transaction and unified locking mechanism
            with self.transaction():
                cursor = self._execute_with_error_handling(
                    "UPDATE category SET name=?, section_id=?, icon_path=?, position=? WHERE id= ?",
                    (
                        data["name"],
                        data["section_id"],
                        data.get("icon_path", ""),
                        data.get("position", 0),
                        data["id"],
                    ),
                )
                if int(getattr(cursor, "rowcount", 0) or 0) == 0:
                    # No record existed, do insertion with required id
                    self._execute_with_error_handling(
                        "INSERT INTO category (id, name, section_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                        (
                            data["id"],
                            data["name"],
                            data["section_id"],
                            data.get("icon_path", ""),
                            data.get("position", 0),
                        ),
                    )
            return data["id"]
        else:
            category_id = self.insert_category(data)
            if category_id is None:
                raise ValueError(
                    f"Category with name '{data['name']}' already exists in this section"
                )
            return category_id

    def get_first_category_id(self):
        """Returns first category in system."""
        result = self._execute_with_error_handling(
            "SELECT id FROM category ORDER BY id LIMIT 1", fetch_method="one"
        )
        return result["id"] if result else None

    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: Optional[int] = None
    ):
        """Checks for category duplicate in section."""
        # Check for duplicate ignoring case
        query = "SELECT COUNT(*) as count FROM category WHERE section_id = ? AND name = ? COLLATE NOCASE"
        # Normalize input for predictable behavior
        try:
            category_name = str(category_name).strip()
        except Exception:
            category_name = str(category_name)
        params = [section_id, category_name]

        if exclude_id is not None:
            query += " AND id != ?"
            params.append(exclude_id)

        result = self._execute_with_error_handling(query, params, fetch_method="one")
        return result["count"] > 0
