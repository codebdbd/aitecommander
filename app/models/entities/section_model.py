import logging
import sqlite3
from typing import Any, Optional

from ...utils.db.sql_helpers import build_in_clause_placeholders
from ..base.db_base import DatabaseBase, row_to_dict

# Logging setup
logger = logging.getLogger(__name__)


class SectionModel(DatabaseBase):
    """Model for working with sections"""

    SQLITE_PARAM_CHUNK_SIZE = 900

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

    def get_sections(self, sphere_id: int) -> list[dict[str, Any]]:
        """Returns list of sections for specified sphere in dict format."""
        rows = self._execute_with_error_handling(
            "SELECT id, name, sphere_id, position, icon_path FROM section "
            "WHERE sphere_id=? ORDER BY position",
            (sphere_id,),
            fetch_method="all",
        )
        if rows is None:
            return []
        return [row_to_dict(row) for row in rows if row is not None]

    def get_section_by_id(self, section_id: int) -> Optional[dict[str, Any]]:
        """Returns section by its ID in dict format."""
        row = self._execute_with_error_handling(
            "SELECT * FROM section WHERE id=?", (section_id,), fetch_method="one"
        )
        assert row is None or isinstance(row, sqlite3.Row)  # type: ignore[unreachable]
        return row_to_dict(row) if row else None

    def insert_section(self, data: dict[str, Any]) -> Optional[int]:
        """Inserts new section and returns its ID. Returns None if duplicate found.
        
        NOTE: Must be called within a transaction context.
        """
        self._validate_required_fields(data, ["name", "sphere_id"], "section")

        # Check for duplicate before insert
        if self.has_duplicate_section(data["sphere_id"], data["name"]):
            logger.warning(
                "Section '%s' already exists in sphere %s",
                data["name"],
                data["sphere_id"],
            )
            return None

        position = self._get_next_position("section", "sphere_id", data["sphere_id"])
        cursor = self._execute_with_error_handling(
            "INSERT INTO section (name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?)",
            (data["name"], data["sphere_id"], data.get("icon_path", ""), position),
        )
        logger.info("Added new section: %s", data["name"])
        if isinstance(cursor, sqlite3.Cursor):
            lastrowid = cursor.lastrowid
            return int(lastrowid) if lastrowid else None
        return None

    def update_section(self, section_id: int, data: dict[str, Any]):
        """Updates existing section."""
        valid_keys = ["name", "sphere_id", "icon_path", "position"]
        self._update_entity("section", section_id, data, valid_keys)

    def delete_section(self, section_id: int):
        """Deletes section by its ID and reindexes positions of remaining in same sphere."""
        # Determine section's sphere before deletion
        row = self._execute_with_error_handling(
            "SELECT sphere_id FROM section WHERE id=?",
            (section_id,),
            fetch_method="one",
        )
        if row is None:
            return
        assert row is None or isinstance(row, sqlite3.Row)  # type: ignore[unreachable]
        sphere_data = row_to_dict(row)
        sphere_id = (
            int(sphere_data["sphere_id"])
            if sphere_data.get("sphere_id") is not None
            else None
        )

        self._execute_with_error_handling(
            "DELETE FROM section WHERE id=?", (section_id,)
        )
        logger.info("Deleted section with ID %s", section_id)

        # Reindex positions of remaining sections in same sphere
        if isinstance(sphere_id, int):
            try:
                self._reindex_positions("section", "sphere_id", sphere_id)
            except Exception:
                # Don't interrupt deletion, but log warning
                logger.warning(
                    "Failed to reindex section positions after deletion", exc_info=False
                )

    # Note: _reindex_positions() is now inherited from DatabaseBase

    def delete_sections_bulk(self, section_ids: list[int]) -> int:
        """Bulk delete sections and reindex positions per affected sphere."""
        unique_ids = self._validate_and_deduplicate_ids(section_ids, "section")
        if not unique_ids:
            return 0

        CHUNK = self.SQLITE_PARAM_CHUNK_SIZE
        affected_spheres: set[int] = set()
        for i in range(0, len(unique_ids), CHUNK):
            chunk = unique_ids[i : i + CHUNK]
            placeholders = build_in_clause_placeholders(len(chunk))
            rows_raw = self._execute_with_error_handling(
                f"SELECT DISTINCT sphere_id FROM section WHERE id IN ({placeholders})",
                tuple(chunk),
                fetch_method="all",
            )
            for row in self._ensure_row_list(rows_raw):
                sphere_id = row["sphere_id"]
                if sphere_id is None:
                    continue
                affected_spheres.add(int(sphere_id))

        deleted_sections = 0
        with self.transaction():
            for i in range(0, len(unique_ids), CHUNK):
                chunk = unique_ids[i : i + CHUNK]
                placeholders = build_in_clause_placeholders(len(chunk))
                pre_count_row = self._execute_with_error_handling(
                    f"SELECT COUNT(*) as cnt FROM section WHERE id IN ({placeholders})",
                    tuple(chunk),
                    fetch_method="one",
                )
                if pre_count_row is None:
                    pre_count = 0
                else:
                    try:
                        pre_count = int(row_to_dict(pre_count_row)["cnt"])
                    except (ValueError, TypeError, KeyError) as exc:
                        logger.debug("Failed to parse pre_count: %s", exc)
                        pre_count = 0

                cursor = self._execute_with_error_handling(
                    f"DELETE FROM section WHERE id IN ({placeholders})",
                    tuple(chunk),
                )
                rc = getattr(cursor, "rowcount", None)
                if rc is not None:
                    deleted_sections += int(rc)
                else:
                    logger.warning(
                        "delete_sections_bulk: cursor.rowcount not available; using pre-count (%s) for chunk %s",
                        pre_count,
                        chunk,
                    )
                    deleted_sections += pre_count

            for sphere_id in affected_spheres:
                try:
                    self._reindex_positions("section", "sphere_id", int(sphere_id))
                except Exception:
                    logger.warning(
                        "Failed to reindex section positions after bulk deletion",
                        exc_info=False,
                    )

        logger.info(
            "Bulk deleted sections (count=%s), ids=%s",
            deleted_sections,
            unique_ids,
        )
        return deleted_sections

    def upsert_section(self, section_data: dict[str, Any]) -> int:
        """Inserts or updates section. If section with this id doesn't exist, inserts new with this id."""
        if "id" in section_data and section_data["id"]:
            cursor = self._execute_with_error_handling(
                "UPDATE section SET name=?, sphere_id=?, icon_path=?, position=? WHERE id=?",
                (
                    section_data["name"],
                    section_data["sphere_id"],
                    section_data.get("icon_path", ""),
                    section_data.get("position", 0),
                    section_data["id"],
                ),
            )
            if isinstance(cursor, sqlite3.Cursor) and cursor.rowcount == 0:
                # No record existed, do insertion with required id
                self._execute_with_error_handling(
                    "INSERT INTO section (id, name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                    (
                        section_data["id"],
                        section_data["name"],
                        section_data["sphere_id"],
                        section_data.get("icon_path", ""),
                        section_data.get("position", 0),
                    ),
                )
            return section_data["id"]
        else:
            return self.insert_section(section_data)

    def get_sphere_id_by_section(self, section_id: int) -> Optional[int]:
        """Returns sphere_id for given section."""
        row = self.get_section_by_id(section_id)
        return row["sphere_id"] if row else None

    def has_duplicate_section(
        self, sphere_id: int, section_name: str, exclude_id: Optional[int] = None
    ) -> bool:
        """Checks for section duplicate in sphere.
        
        Args:
            sphere_id: Sphere ID to check within
            section_name: Section name to check
            exclude_id: Optional section ID to exclude from check (for updates)
            
        Returns:
            True if duplicate exists, False otherwise
        """
        query = "SELECT COUNT(*) as count FROM section WHERE sphere_id = ? AND name = ? COLLATE NOCASE"
        try:
            section_name = str(section_name).strip()
        except Exception:
            section_name = str(section_name)
        params = [sphere_id, section_name]

        if exclude_id is not None:
            query += " AND id != ?"
            params.append(exclude_id)

        result_row = self._execute_with_error_handling(
            query,
            tuple(params),
            fetch_method="one",
        )
        if result_row:
            count = result_row["count"] if isinstance(result_row, sqlite3.Row) else result_row.get("count", 0)
            return int(count) > 0
        return False
