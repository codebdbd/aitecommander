"""
CategoryModel - model for working with categories in database.
"""

import logging
from typing import Any, Optional

from ...utils.db.sql_helpers import build_in_clause_placeholders, build_placeholders
from ..base.db_base import DatabaseBase, ValidationError, row_to_dict
from ..types.category_types import BulkInsertResult, CategoryDict
from ..types.constants import CATEGORY_BULK_UUID_FIELD

logger = logging.getLogger(__name__)


class CategoryModel(DatabaseBase):
    """Model for working with categories."""

    SQLITE_PARAM_CHUNK_SIZE = 900

    def __init__(self, database):
        """Initialization of category model."""
        super().__init__(database)

    def _validate_and_deduplicate_ids(
        self, ids: list[int], entity_name: str = "item"
    ) -> list[int]:
        """Validate, filter and deduplicate integer IDs."""
        if not ids:
            return []

        valid_ids = [
            int(x) for x in ids
            if isinstance(x, int) and not isinstance(x, bool) and x > 0
        ]

        unique_ids = list(dict.fromkeys(valid_ids))

        if not unique_ids:
            logger.warning(
                "No valid %s IDs found in input list of length %d",
                entity_name, len(ids)
            )

        return unique_ids

    def get_categories(self, section_id: int) -> list[CategoryDict]:
        """Returns list of categories for specified section in dict format."""
        rows = self._execute_with_error_handling(
            "SELECT id, name, section_id, position, icon_path FROM category "
            "WHERE section_id = ? ORDER BY position",
            (section_id,),
            fetch_method="all",
        )
        return [row_to_dict(row) for row in rows] if rows else []

    def get_categories_for_sections(
        self, section_ids: list[int]
    ) -> list[CategoryDict]:
        """Returns categories for multiple sections in one query."""
        if not section_ids:
            return []

        validated_ids = self._validate_and_deduplicate_ids(section_ids, "section")
        if not validated_ids:
            return []

        placeholders = build_in_clause_placeholders(len(validated_ids))
        query = f"""
            SELECT id, name, section_id, position, icon_path 
            FROM category 
            WHERE section_id IN ({placeholders}) 
            ORDER BY section_id, position
        """
        rows_raw = self._execute_with_error_handling(
            query, tuple(validated_ids), fetch_method="all"
        )
        rows = self._ensure_row_list(rows_raw)
        return [row_to_dict(row) for row in rows] if rows else []

    def get_category_by_id(self, category_id: int) -> Optional[CategoryDict]:
        """Returns category by its ID in dict format."""
        row = self._execute_with_error_handling(
            "SELECT id, name, section_id, position, icon_path FROM category WHERE id = ?",
            (category_id,),
            fetch_method="one"
        )
        return row_to_dict(row) if row else None

    def get_categories_by_ids(self, category_ids: list[int]) -> list[CategoryDict]:
        """Returns categories for multiple IDs in one query, preserving input order."""
        if not category_ids:
            return []

        validated_ids = self._validate_and_deduplicate_ids(category_ids, "category")
        if not validated_ids:
            return []

        placeholders = build_in_clause_placeholders(len(validated_ids))
        query = f"""
            SELECT id, name, section_id, position, icon_path
            FROM category
            WHERE id IN ({placeholders})
        """
        rows_raw = self._execute_with_error_handling(
            query, tuple(validated_ids), fetch_method="all"
        )
        rows = self._ensure_row_list(rows_raw)

        # Build a map from id to category for quick lookup
        category_map = {int(row["id"]): row_to_dict(row) for row in rows}

        # Return categories in the order of the original input (preserving duplicates)
        result = []
        for cid in category_ids:
            if cid in category_map:
                result.append(category_map[cid])

        return result

    def get_category_hierarchy(self, category_id: int) -> Optional[dict[str, int]]:
        """Get category hierarchy (sphere -> section -> category)."""
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

    def insert_category(self, data: dict[str, Any]) -> Optional[int]:
        """Inserts new category and returns its ID. Returns None if duplicate found.
        
        NOTE: Must be called within a transaction context.
        """
        self._validate_required_fields(data, ["name", "section_id"], "category")

        cursor = self._execute_with_error_handling(
            "SELECT id FROM category WHERE section_id = ? AND name = ? COLLATE NOCASE",
            (data["section_id"], str(data["name"]).strip()),
            fetch_method="one",
        )
        if cursor is not None:
            logger.warning(
                "Category '%s' already exists in section %s",
                data["name"],
                data["section_id"],
            )
            return None

        position = self._get_next_position("category", "section_id", data["section_id"])
        insert_cursor = self._execute_with_error_handling(
            "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
            (data["name"], data["section_id"], data.get("icon_path", ""), position),
        )
        logger.info("Added new category: %s", data["name"])
        lastrowid = getattr(insert_cursor, "lastrowid", None)
        return int(lastrowid) if lastrowid is not None else None

    def _validate_and_prepare_items(
        self, items: list[dict[str, Any]]
    ) -> tuple[list[tuple[int, str, str]], bool]:
        """Validate input items and prepare normalized metadata."""
        prepared_items: list[tuple[int, str, str]] = []
        has_uuid_tokens = False

        for idx, it in enumerate(items):
            self._validate_required_fields(it or {}, ["name", "section_id"], "category")
            section_id_raw = it.get("section_id")
            try:
                if section_id_raw is None:
                    raise ValueError("section_id is missing")
                sid = int(section_id_raw)
            except (ValueError, TypeError) as e:
                raise ValidationError(
                    f"Incorrect section_id in batch element at index {idx}"
                ) from e
            raw_name = it.get("name")
            name_canon = str(raw_name).strip() if raw_name is not None else ""
            if not name_canon:
                raise ValidationError(
                    f"Empty category name at index {idx}"
                )
            name_norm = name_canon.lower()
            prepared_items.append((sid, name_canon, name_norm))

            if not has_uuid_tokens:
                token_raw = it.get(CATEGORY_BULK_UUID_FIELD)
                if token_raw is not None and str(token_raw).strip():
                    has_uuid_tokens = True

        return prepared_items, has_uuid_tokens

    def _group_by_section(
        self,
        items: list[dict[str, Any]],
        prepared_items: list[tuple[int, str, str]],
    ) -> dict[int, list[tuple[int, dict[str, Any]]]]:
        """Group items by section_id, preserving their indices."""
        by_section: dict[int, list[tuple[int, dict[str, Any]]]] = {}
        for idx, (it, (sid, _, _)) in enumerate(zip(items, prepared_items)):
            by_section.setdefault(sid, []).append((idx, it))
        return by_section

    def _load_max_positions(self, section_ids: list[int]) -> dict[int, Optional[int]]:
        """Load MAX(position) for all sections in one query."""
        max_pos_map: dict[int, Optional[int]] = {}
        if not section_ids:
            return max_pos_map

        placeholders = build_in_clause_placeholders(len(section_ids))
        query = (
            f"SELECT section_id, MAX(position) AS max_pos "
            f"FROM category WHERE section_id IN ({placeholders}) "
            f"GROUP BY section_id"
        )
        rows_raw = self._execute_with_error_handling(
            query, tuple(section_ids), fetch_method="all"
        )
        for row in self._ensure_row_list(rows_raw):
            row_dict = row_to_dict(row)
            max_pos_map[row_dict["section_id"]] = row_dict["max_pos"]
        return max_pos_map

    def _load_existing_names(self, section_ids: list[int]) -> dict[int, set[str]]:
        """Load existing category names for all sections in one query."""
        existing_names_by_section: dict[int, set[str]] = {}
        if not section_ids:
            return existing_names_by_section

        placeholders = build_in_clause_placeholders(len(section_ids))
        query_names = (
            f"SELECT section_id, LOWER(name) AS lname FROM category "
            f"WHERE section_id IN ({placeholders})"
        )
        rows_raw = self._execute_with_error_handling(
            query_names, tuple(section_ids), fetch_method="all"
        )
        for r in self._ensure_row_list(rows_raw):
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
        by_section: dict[int, list[tuple[int, dict[str, Any]]]],
        prepared_items: list[tuple[int, str, str]],
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

            for idx, it in group:
                sid, name_canon, name_norm = prepared_items[idx]
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
        by_section: dict[int, list[tuple[int, dict[str, Any]]]],
        prepared_items: list[tuple[int, str, str]],
    ) -> list[tuple[int, str]]:
        """Collect unique (section_id, name) pairs for DB query."""
        pairs: list[tuple] = []
        seen = set()
        for section_id, group in by_section.items():
            for idx, _ in group:
                _, nm_canon, _ = prepared_items[idx]
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

        placeholders = build_placeholders(len(pairs), "(?, ?)")
        flat_params: list[Any] = []
        for sid, nm in pairs:
            flat_params.extend([sid, nm])

        query = (
            "SELECT id, name, section_id, position, icon_path "
            "FROM category WHERE (section_id, name) IN (" + placeholders + ") "
            "ORDER BY section_id, position"
        )
        rows_raw = self._execute_with_error_handling(
            query, tuple(flat_params), fetch_method="all"
        )
        rows = self._ensure_row_list(rows_raw)
        return [row_to_dict(r) for r in rows]

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
            except (ValueError, TypeError, KeyError) as e:
                logger.debug("Failed to parse section_id from row: %s", e)
                section_id = None
            if section_id is None:
                continue
            name_value = str(r["name"]).strip().lower() if r["name"] is not None else ""
            if not name_value:
                logger.debug("Skipping category with empty name: id=%s", r.get("id"))
                continue
            rows_by_key[(section_id, name_value)] = r
        return rows_by_key

    def _attach_uuid_tokens(
        self,
        rows_by_key: dict[tuple[int, str], dict[str, Any]],
        items: list[dict[str, Any]],
        prepared_items: list[tuple[int, str, str]],
    ) -> list[dict[str, Any]]:
        """Attach UUID tokens to fetched categories."""
        result: list[dict[str, Any]] = []
        for idx, it in enumerate(items):
            section_id, _, name_norm = prepared_items[idx]
            if not name_norm:
                continue
            row = rows_by_key.get((section_id, name_norm))
            if not row:
                continue
            payload = dict(row)
            token_raw = it.get(CATEGORY_BULK_UUID_FIELD)
            token = str(token_raw).strip() if token_raw is not None else ""
            if token:
                payload[CATEGORY_BULK_UUID_FIELD] = token
            result.append(payload)
        return result

    def _fetch_inserted_categories(
        self,
        by_section: dict[int, list[tuple[int, dict[str, Any]]]],
        prepared_items: list[tuple[int, str, str]],
        has_uuid_tokens: bool,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Fetch inserted categories from DB and attach UUID tokens if needed."""
        pairs = self._collect_category_pairs(by_section, prepared_items)
        if not pairs:
            return []

        rows = self._query_categories_by_pairs(pairs)
        if not has_uuid_tokens:
            return rows

        rows_by_key = self._build_category_index(rows)
        return self._attach_uuid_tokens(rows_by_key, items, prepared_items)

    def insert_categories_bulk(
        self, items: list[dict[str, Any]]
    ) -> BulkInsertResult:
        """Bulk category insertion with atomic transaction. Duplicates are skipped and logged."""
        if not items:
            return BulkInsertResult(inserted=[], duplicates_skipped=0, total_items=0)

        prepared_items, has_uuid_tokens = self._validate_and_prepare_items(items)
        by_section = self._group_by_section(items, prepared_items)

        with self.transaction():
            section_ids = list(by_section.keys())
            max_pos_map = self._load_max_positions(section_ids)
            existing_names_by_section = self._load_existing_names(section_ids)

            batched_params = self._build_insert_batch(
                by_section, prepared_items, max_pos_map, existing_names_by_section
            )

            total_items = len(items)
            items_to_insert = len(batched_params)
            duplicates_skipped = total_items - items_to_insert

            if duplicates_skipped > 0:
                logger.info(
                    "Bulk insert: %d duplicates skipped out of %d items",
                    duplicates_skipped,
                    total_items,
                )

            cursor = self._execute_many_with_error_handling(
                "INSERT OR IGNORE INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
                batched_params,
            )

            rowcount = getattr(cursor, "rowcount", None)
            if rowcount is not None:
                if rowcount != items_to_insert:
                    logger.warning(
                        "Bulk insert: expected %d inserts, but rowcount=%d (possible DB-level duplicates)",
                        items_to_insert,
                        rowcount,
                    )
                elif rowcount > 0:
                    logger.debug("Successfully inserted %d categories", rowcount)

            inserted = self._fetch_inserted_categories(
                by_section, prepared_items, has_uuid_tokens, items
            )

            return BulkInsertResult(
                inserted=inserted,
                duplicates_skipped=duplicates_skipped,
                total_items=total_items,
            )

    def update_category(self, category_id: int, data: dict[str, Any]) -> None:
        """Updates existing category."""
        return self._update_entity(
            "category",
            category_id,
            data,
            ["name", "section_id", "icon_path", "position"],
        )

    def update_categories_bulk(self, updates: list[dict[str, Any]]) -> int:
        """Bulk update multiple categories in one transaction.
        
        Args:
            updates: List of dicts with 'id' and fields to update
            
        Returns:
            Number of categories updated
        """
        if not updates:
            return 0
        
        updated_count = 0
        with self.transaction():
            for item in updates:
                if not isinstance(item, dict) or "id" not in item:
                    logger.warning("update_categories_bulk: skipping invalid item %s", item)
                    continue
                
                category_id = item.get("id")
                if not isinstance(category_id, int) or category_id <= 0:
                    logger.warning("update_categories_bulk: invalid category_id %s", category_id)
                    continue
                
                try:
                    self.update_category(category_id, item)
                    updated_count += 1
                except Exception as exc:
                    logger.warning(
                        "update_categories_bulk: failed to update category %s: %s",
                        category_id,
                        exc,
                    )
        
        logger.info("Bulk updated %d categories", updated_count)
        return updated_count

    def delete_category(self, category_id: int) -> None:
        """Deletes category by its ID along with all its links (atomically)."""
        with self.transaction():
            self._execute_with_error_handling(
                "DELETE FROM link WHERE category_id=?", (category_id,)
            )
            self._execute_with_error_handling(
                "DELETE FROM category WHERE id=?", (category_id,)
            )
        logger.info("Deleted category with ID %s and all its links", category_id)

    def delete_categories_bulk(self, category_ids: list[int]) -> int:
        """Bulk deletion of multiple categories (and their links) in one transaction."""
        unique_ids = self._validate_and_deduplicate_ids(category_ids, "category")
        if not unique_ids:
            return 0

        CHUNK = self.SQLITE_PARAM_CHUNK_SIZE

        affected_sections: list[int] = []
        for i in range(0, len(unique_ids), CHUNK):
            chunk = unique_ids[i : i + CHUNK]
            placeholders = build_in_clause_placeholders(len(chunk))
            rows_raw = self._execute_with_error_handling(
                f"SELECT DISTINCT section_id FROM category WHERE id IN ({placeholders})",
                tuple(chunk),
                fetch_method="all",
            )
            for row in self._ensure_row_list(rows_raw):
                section_id = row["section_id"]
                if section_id is None:
                    continue
                affected_sections.append(int(section_id))

        deleted_categories = 0
        with self.transaction():
            for i in range(0, len(unique_ids), CHUNK):
                chunk = unique_ids[i : i + CHUNK]
                placeholders = build_in_clause_placeholders(len(chunk))
                self._execute_with_error_handling(
                    f"DELETE FROM link WHERE category_id IN ({placeholders})",
                    tuple(chunk),
                )
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
                        )
                    except (ValueError, TypeError, KeyError) as e:
                        logger.debug("Failed to parse pre_count: %s", e)
                        pre_count = 0

                cursor = self._execute_with_error_handling(
                    f"DELETE FROM category WHERE id IN ({placeholders})",
                    tuple(chunk),
                )
                rc = getattr(cursor, "rowcount", None)
                if rc is not None:
                    deleted_categories += int(rc)
                else:
                    logger.warning(
                        "delete_categories_bulk: cursor.rowcount not available; using pre-count (%s) for chunk %s",
                        pre_count,
                        chunk,
                    )
                    deleted_categories += pre_count

            try:
                self._reindex_positions_bulk(affected_sections)
            except Exception as e:
                logger.warning(
                    "Failed to reindex category positions after deletion: %s",
                    e,
                    exc_info=True,
                )

        logger.info(
            "Bulk deleted categories (count=%s), ids=%s",
            deleted_categories,
            unique_ids,
        )
        return deleted_categories

    def move_categories_to_section_bulk(
        self, category_ids: list[int], target_section_id: int, base_row: int = 0
    ) -> list[int]:
        """Atomically moves multiple categories to target section. Skips duplicates and logs."""
        if not category_ids or not isinstance(target_section_id, int) or target_section_id <= 0:
            return []

        target_exists = self._execute_with_error_handling(
            "SELECT COUNT(*) as cnt FROM section WHERE id = ?",
            (target_section_id,),
            fetch_method="one",
        )
        if not target_exists or row_to_dict(target_exists).get("cnt", 0) == 0:
            logger.warning(
                "Cannot move categories: target section %d does not exist",
                target_section_id,
            )
            return []

        unique_ids = self._validate_and_deduplicate_ids(category_ids, "category")
        if not unique_ids:
            return []

        placeholders = build_in_clause_placeholders(len(unique_ids))
        rows_raw = self._execute_with_error_handling(
            f"SELECT id, name, section_id, position FROM category WHERE id IN ({placeholders})",
            tuple(unique_ids),
            fetch_method="all",
        )
        rows = self._ensure_row_list(rows_raw)
        if not rows:
            return []

        data_by_id: dict[int, dict[str, Any]] = {int(r["id"]): dict(r) for r in rows}

        ordered_existing_ids = [cid for cid in unique_ids if cid in data_by_id]

        existing_names_rows = self._execute_with_error_handling(
            "SELECT LOWER(name) AS name FROM category WHERE section_id = ?",
            (target_section_id,),
            fetch_method="all",
        )
        existing_names = {
            str(r["name"]).strip().lower()
            for r in self._ensure_row_list(existing_names_rows)
        }

        to_move_ids = []
        skipped_duplicates = []

        for cid in ordered_existing_ids:
            cat_data = data_by_id[cid]
            name_lower = str(cat_data["name"]).strip().lower()
            if name_lower in existing_names:
                skipped_duplicates.append({
                    "id": cid,
                    "name": cat_data["name"],
                })
                continue
            to_move_ids.append(cid)

        if skipped_duplicates:
            logger.info(
                "Bulk move: skipped %d categories due to duplicates in target section %d: %s",
                len(skipped_duplicates),
                target_section_id,
                [s["name"] for s in skipped_duplicates],
            )

        if not to_move_ids:
            return []
        source_sections = [
            int(data_by_id[cid].get("section_id", 0) or 0) for cid in to_move_ids
        ]
        source_sections = [
            sid for sid in source_sections if sid and sid != target_section_id
        ]

        with self.transaction():
            updates = []
            pos = int(base_row) if isinstance(base_row, int) and base_row >= 0 else 0
            for cid in to_move_ids:
                updates.append((target_section_id, pos, cid))
                pos += 1
            self._execute_many_with_error_handling(
                "UPDATE category SET section_id = ?, position = ? WHERE id = ?",
                updates,
            )

            try:
                all_affected = source_sections + [target_section_id]
                self._reindex_positions_bulk(all_affected)
            except Exception as e:
                logger.warning(
                    "Failed to reindex positions after bulk move: %s",
                    e,
                    exc_info=True,
                )

        logger.info(
            f"Bulk category move (count={len(to_move_ids)}) to section {target_section_id}, ids={to_move_ids}"
        )
        return to_move_ids

    def _reindex_positions_bulk(self, section_ids: list[int]) -> None:
        """Reindex category positions for multiple sections.
        
        Note: For single section, prefer calling base _reindex_positions directly.
        """
        if not section_ids:
            return

        unique_sections = self._validate_and_deduplicate_ids(section_ids, "section")
        if not unique_sections:
            return
        
        # Reindex each section separately using base method
        for section_id in unique_sections:
            try:
                super()._reindex_positions("category", "section_id", section_id)
            except Exception as e:
                logger.warning(
                    "Failed to reindex categories for section %d: %s",
                    section_id,
                    e,
                )

    # Note: _reindex_positions() is now inherited from DatabaseBase

    def upsert_category(self, category_data: dict[str, Any]) -> int:
        """Inserts or updates category. If category with this id doesn't exist, inserts new with this id."""
        data = dict(category_data)
        if "name" in data and data["name"] is not None:
            try:
                data["name"] = str(data["name"]).strip()
            except (AttributeError, TypeError) as e:
                logger.warning("Failed to strip category name: %s", e)
                data["name"] = str(data.get("name", ""))

        if "id" in data and data["id"] is not None:
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

    def get_first_category_id(self) -> Optional[int]:
        """Returns first category in system."""
        result = self._execute_with_error_handling(
            "SELECT id FROM category ORDER BY id LIMIT 1", fetch_method="one"
        )
        if not result:
            return None
        from ..base.db_base import row_to_dict
        result_dict = row_to_dict(result)
        return result_dict.get("id")

    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: Optional[int] = None
    ) -> bool:
        """Checks for category duplicate in section."""
        query = "SELECT COUNT(*) as count FROM category WHERE section_id = ? AND name = ? COLLATE NOCASE"
        try:
            category_name = str(category_name).strip()
        except (AttributeError, TypeError) as e:
            logger.debug("Failed to strip category name: %s", e)
            category_name = str(category_name)
        params = [section_id, category_name]

        if exclude_id is not None:
            query += " AND id != ?"
            params.append(exclude_id)

        result_row = self._execute_with_error_handling(
            query,
            tuple(params),
            fetch_method="one",
        )
        result_dict = row_to_dict(result_row)
        return bool(result_dict.get("count", 0))
