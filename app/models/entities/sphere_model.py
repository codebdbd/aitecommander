import logging
import sqlite3
from typing import Any, Dict, List, Optional

from app.utils.ui.icon.icon_resolver import resolve_icon_for_link

from ..base.db_base import DatabaseBase, DatabaseError

# Logging setup
logger = logging.getLogger(__name__)

# Centralized icon resolution


class SphereModel(DatabaseBase):
    """Model for working with spheres"""

    def get_spheres(self) -> List[Dict[str, Any]]:
        """Returns list of all spheres in dict format."""
        rows = self._execute_with_error_handling(
            "SELECT id, name, position, icon_path FROM sphere ORDER BY position",
            fetch_method="all",
        )
        return [dict(row) for row in rows] if rows else []

    def get_sphere_by_id(self, sphere_id: int) -> Optional[Dict[str, Any]]:
        """Returns sphere by its ID in dict format."""
        row = self._execute_with_error_handling(
            "SELECT id, name, position, icon_path FROM sphere WHERE id = ?",
            (sphere_id,),
            fetch_method="one",
        )
        return dict(row) if row else None

    def insert_sphere(self, data: Dict[str, Any]) -> int:
        """Inserts new sphere and returns its ID."""
        self._validate_required_fields(data, ["name"], "sphere")

        position = self._get_next_position("sphere")
        cursor = self._execute_with_error_handling(
            "INSERT INTO sphere (name, icon_path, position) VALUES (?, ?, ?)",
            (data["name"], data.get("icon_path", ""), position),
        )
        logger.info("Added new sphere: %s", data["name"])
        return cursor.lastrowid

    def update_sphere(self, sphere_id: int, data: Dict[str, Any]):
        """Updates existing sphere."""
        valid_keys = ["name", "icon_path", "position"]
        self._update_entity("sphere", sphere_id, data, valid_keys)

    def upsert_sphere(self, sphere_data: Dict[str, Any]) -> int:
        """Inserts or updates sphere."""
        if "id" in sphere_data and sphere_data["id"]:
            self.update_sphere(sphere_data["id"], sphere_data)
            return sphere_data["id"]
        else:
            return self.insert_sphere(sphere_data)

    def get_sphere_name(self, sphere_id: int) -> str:
        """Returns sphere name by its ID."""
        row = self._execute_with_error_handling(
            "SELECT name FROM sphere WHERE id=?",
            (sphere_id,),
            fetch_method="one"
        )
        return dict(row)["name"] if row else ""

    def initialize_default_spheres(self):
        """Initializes initial data for sphere table if it's empty.

        Includes adding compatible icon_path column (if missing) and
        inserting standard set of values. Commit performed at end
        of operation. Repeated calls safe: if data already exists, only log.
        """
        try:
            cursor = self.connection.execute("SELECT COUNT(*) FROM sphere")
            count = cursor.fetchone()[0]

            if count == 0:
                # Compatibility: add icon_path column if missing
                try:
                    self.connection.execute(
                        "ALTER TABLE sphere ADD COLUMN icon_path TEXT DEFAULT ''"
                    )
                except sqlite3.OperationalError:
                    # Column already exists — not an error
                    pass

                default = [
                    ("AI", 0, resolve_icon_for_link({"type": "ai", "icon_path": ""})),
                    (
                        "Work",
                        1,
                        resolve_icon_for_link({"type": "work", "icon_path": ""}),
                    ),
                    (
                        "Study",
                        2,
                        resolve_icon_for_link({"type": "study", "icon_path": ""}),
                    ),
                    (
                        "Personal",
                        3,
                        resolve_icon_for_link({"type": "personal", "icon_path": ""}),
                    ),
                ]
                self._execute_many_with_error_handling(
                    "INSERT INTO sphere(name, position, icon_path) VALUES(?,?,?)",
                    default,
                )
                self.commit()
                logger.info("Initial sphere data added")
            else:
                logger.info("Initial sphere data already exists")
        except Exception as e:
            logger.error("Error initializing initial sphere data: %s", e)
            raise DatabaseError(
                f"Failed to initialize initial sphere data: {e}"
            )
