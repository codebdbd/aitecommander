import logging
import sqlite3
from typing import Any, Optional

from ..base.db_base import DatabaseBase, row_to_dict

# Logging setup
logger = logging.getLogger(__name__)


class SectionModel(DatabaseBase):
    """Model for working with sections"""

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

    def insert_section(self, data: dict[str, Any]) -> int:
        """Inserts new section and returns its ID."""
        self._validate_required_fields(data, ["name", "sphere_id"], "section")

        position = self._get_next_position("section", "sphere_id", data["sphere_id"])
        cursor = self._execute_with_error_handling(
            "INSERT INTO section (name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?)",
            (data["name"], data["sphere_id"], data.get("icon_path", ""), position),
        )
        logger.info("Added new section: %s", data["name"])
        if isinstance(cursor, sqlite3.Cursor):
            return cursor.lastrowid or 0
        return 0

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
                self._reindex_positions(sphere_id)
            except Exception:
                # Don't interrupt deletion, but log warning
                logger.warning(
                    "Failed to reindex section positions after deletion", exc_info=False
                )

    def _reindex_positions(self, sphere_id: int) -> None:
        """Reindex position field for all sphere sections sequentially from 0.

        Executed without own begin/commit, assuming external transaction context.
        """
        # Get section ids in required order
        rows = self._execute_with_error_handling(
            "SELECT id FROM section WHERE sphere_id = ? ORDER BY position, id",
            (sphere_id,),
            fetch_method="all",
        )
        ids_in_order = [int(r["id"]) for r in (rows or [])]
        if not ids_in_order:
            return
        # Prepare batch of position updates 0..n-1
        updates = [(pos, cid) for pos, cid in enumerate(ids_in_order)]
        self._execute_many_with_error_handling(
            "UPDATE section SET position = ? WHERE id = ?",
            updates,
        )

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
