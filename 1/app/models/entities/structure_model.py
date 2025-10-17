# app/models/structure_model.py

"""Model for working with structure (spheres, sections, categories)."""

import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from app.models.db import Database

logger = logging.getLogger(__name__)


class StructureModel:
    """Model for working with structure."""

    def __init__(self, db: "Database", logger: Optional[logging.Logger] = None):
        self.db = db
        self.logger = logger or globals().get("logger") or logging.getLogger(__name__)

    def _commit_if_in_tx(self) -> None:
        """Commits transaction if it's active on connection.

        Moving duplicate logic to single place reduces behavior divergence risk.
        In case of error we log and don't propagate further to not mask
        original model-level operation.
        """
        try:
            conn = self.db.connection
            if getattr(conn, "in_transaction", False):
                self.db.commit()
        except Exception as e:
            self.logger.error("Error committing transaction: %s", e, exc_info=True)

    def get_spheres(self) -> list[dict[str, Any]]:
        """Returns list of all spheres."""
        return self.db.spheres.get_spheres() or []

    def get_sphere_by_id(self, sphere_id: int) -> Optional[dict[str, Any]]:
        """Returns sphere by its ID."""
        return self.db.spheres.get_sphere_by_id(sphere_id)

    def upsert_sphere(self, data: dict[str, Any]) -> int:
        """Inserts or updates sphere. Returns record ID."""
        sid = self.db.spheres.upsert_sphere(data)
        self._commit_if_in_tx()
        return sid

    def create_sphere(self, data: dict[str, Any]) -> Optional[int]:
        """Creates new sphere (wrapper for upsert_sphere)."""
        try:
            return self.upsert_sphere(data)
        except Exception as e:
            self.logger.error("Error creating sphere: %s", e, exc_info=True)
            return None

    def update_sphere(self, sphere_id: int, data: dict[str, Any]) -> bool:
        """Updates sphere by ID (wrapper for upsert_sphere)."""
        try:
            payload = dict(data) if data else {}
            payload["id"] = sphere_id
            self.upsert_sphere(payload)
            return True
        except Exception as e:
            self.logger.error(
                "Error updating sphere %s: %s", sphere_id, e, exc_info=True
            )
            return False

    def get_sections(self, sphere_id: int) -> list[dict[str, Any]]:
        """Returns list of sections for specified sphere."""
        return self.db.sections.get_sections(sphere_id) or []

    def get_section_by_id(self, section_id: int) -> Optional[dict[str, Any]]:
        """Returns section by its ID."""
        return self.db.sections.get_section_by_id(section_id)

    def get_categories(self, section_id: int) -> list[dict[str, Any]]:
        """Returns list of categories for specified section."""
        return self.db.categories.get_categories(section_id) or []

    def get_category_by_id(self, category_id: int) -> Optional[dict[str, Any]]:
        """Returns category by its ID."""
        return self.db.categories.get_category_by_id(category_id)

    def get_category_hierarchy(self, category_id: int) -> Optional[dict[str, Any]]:
        """Returns category hierarchy (sphere_id, section_id)."""
        hierarchy_data = self.db.categories.get_category_hierarchy(category_id)
        if not hierarchy_data:
            return None

        try:
            # Expect only dict from CategoryModel.get_category_hierarchy
            if not isinstance(hierarchy_data, dict):
                self.logger.warning(
                    "Incorrect hierarchy format for category %s: %s",
                    category_id,
                    type(hierarchy_data),
                )
                return None

            # Try to read standard keys
            sphere_id = hierarchy_data.get("sphere_id")
            section_id = hierarchy_data.get("section_id")
            # Possible alternative keys (for old calls)
            if sphere_id is None:
                sphere_id = hierarchy_data.get("sphereId")
            if section_id is None:
                section_id = hierarchy_data.get("sectionId")

            # Basic type/value check
            if sphere_id is None or section_id is None:
                self.logger.warning(
                    "Missing sphere_id/section_id keys in category hierarchy %s: %s",
                    category_id,
                    hierarchy_data,
                )
                return None

            return {"sphere_id": sphere_id, "section_id": section_id}
        except Exception as e:
            self.logger.error(
                "Error processing category hierarchy %s: %s",
                category_id,
                e,
                exc_info=True,
            )
            return None

    def upsert_section(self, data: dict[str, Any]) -> int:
        """Inserts or updates section. Returns record ID."""
        sid = self.db.sections.upsert_section(data)
        self._commit_if_in_tx()
        return sid

    def upsert_category(self, data: dict[str, Any]) -> int:
        """Inserts or updates category. Returns record ID."""
        cid = self.db.categories.upsert_category(data)
        self._commit_if_in_tx()
        return cid

    # ---------------------------------------------------------------------
    # Wrappers for business logic compatibility (expected methods)
    # ---------------------------------------------------------------------
    def create_section(self, data: dict[str, Any]) -> Optional[int]:
        """Creates new section (wrapper for upsert_section)."""
        try:
            return self.upsert_section(data)
        except Exception as e:
            self.logger.error("Error creating section: %s", e, exc_info=True)
            return None

    def update_section(self, section_id: int, data: dict[str, Any]) -> bool:
        """Updates section by ID (wrapper for upsert_section)."""
        try:
            payload = dict(data) if data else {}
            payload["id"] = section_id
            self.upsert_section(payload)
            return True
        except Exception as e:
            self.logger.error(
                "Error updating section %s: %s", section_id, e, exc_info=True
            )
            return False

    def update_category(self, category_id: int, data: dict[str, Any]) -> bool:
        """Updates category by ID (wrapper for upsert_category)."""
        try:
            payload = dict(data) if data else {}
            payload["id"] = category_id
            self.upsert_category(payload)
            return True
        except Exception as e:
            self.logger.error(
                "Error updating category %s: %s", category_id, e, exc_info=True
            )
            return False

    def get_section_data(self, section_id: int) -> Optional[dict[str, Any]]:
        """Returns section data (alias for get_section_by_id)."""
        return self.get_section_by_id(section_id)

    def get_category_data(self, category_id: int) -> Optional[dict[str, Any]]:
        """Returns category data (alias for get_category_by_id)."""
        return self.get_category_by_id(category_id)

    def delete_section(self, section_id: int) -> bool:
        """Deletes section by its ID."""
        try:
            self.db.sections.delete_section(section_id)
            self._commit_if_in_tx()
            return True
        except Exception as e:
            self.logger.error(
                "Error deleting section %s: %s", section_id, e, exc_info=True
            )
            return False

    def delete_category(self, category_id: int) -> bool:
        """Deletes category by its ID."""
        try:
            self.db.categories.delete_category(category_id)
            self._commit_if_in_tx()
            return True
        except Exception as e:
            self.logger.error(
                "Error deleting category %s: %s", category_id, e, exc_info=True
            )
            return False

    def get_first_category_id(self) -> Optional[int]:
        """Gets ID of first category in system."""
        try:
            result = self.db.categories.get_first_category_id()
            return result if result else None
        except Exception as e:
            self.logger.error("Error getting first category: %s", e, exc_info=True)
            return None

    def get_categories_batch(self, section_ids: list[int]) -> list[dict[str, Any]]:
        """Gets categories for multiple sections with one optimized query."""
        if not section_ids:
            return []

        try:
            # Use optimized DB method instead of N+1 queries
            categories_raw = self.db.categories.get_categories_for_sections(section_ids)
            return categories_raw or []
        except Exception as e:
            self.logger.error(
                "Error getting categories for sections %s: %s",
                section_ids,
                e,
                exc_info=True,
            )
            return []

    def count_nested_objects_for_section(self, section_id: int) -> tuple[int, int]:
        """Counts categories and links in section."""
        categories_data = self.db.categories.get_categories(section_id)
        cats_count = len(categories_data) if categories_data else 0

        links_count = 0
        if categories_data:
            for category_row in categories_data:
                # Direct access to id field: get_categories returns list of dict
                category_id = category_row["id"]
                # Optimized: use efficient count instead of loading all link rows
                links_count += self.db.links.count_links_by_category(category_id)

        return cats_count, links_count

    def update_item_positions(self, table_name: str, ids_in_order: list[int]) -> None:
        """Updates item positions in specified table."""
        self.db.update_item_positions(table_name, ids_in_order)

    def create_category(self, category_data: dict[str, Any]) -> Optional[int]:
        """Creates new category."""
        try:
            cat_id = self.db.categories.insert_category(category_data)
            # Explicit commit if category is created outside external transaction
            self._commit_if_in_tx()
            return cat_id
        except Exception as e:
            self.logger.error("Error creating category: %s", e, exc_info=True)
            return None

    def create_categories_bulk(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Bulk category creation (atomically).

        Delegates to `CategoryModel.insert_categories_bulk` and returns list
        of actual category records after operation (both new and existing
        from name set), for UI/cache synchronization.
        """
        try:
            return self.db.categories.insert_categories_bulk(items or []) or []
        except Exception as e:
            self.logger.error("Error bulk creating categories: %s", e, exc_info=True)
            return []

    def create_link(self, link_data: dict[str, Any]) -> Optional[int]:
        """Creates or updates link (wrapper for upsert_link).

        Returns record ID. For new records link model performs
        silent duplicate check by (category_id, name, url, args) and
        returns existing record ID without error if duplicate found.
        """
        try:
            # Direct creation through DB to avoid circular dependencies
            link_id = self.db.links.upsert_link(link_data)
            # Explicit commit if operation is performed within active transaction
            self._commit_if_in_tx()
            return link_id
        except Exception as e:
            self.logger.error("Error creating link: %s", e, exc_info=True)
            return None

    def get_links(self, category_id: int) -> list[dict[str, Any]]:
        """Gets list of links for specified category."""
        try:
            links_raw = self.db.links.get_links(category_id)
            return links_raw or []
        except Exception as e:
            self.logger.error(
                "Error getting links for category %s: %s",
                category_id,
                e,
                exc_info=True,
            )
            return []

    def count_links_by_category(self, category_id: int) -> int:
        """Returns number of links for specified category (efficient count)."""
        try:
            return self.db.links.count_links_by_category(category_id)
        except Exception as e:
            self.logger.error(
                "Error counting links for category %s: %s",
                category_id,
                e,
                exc_info=True,
            )
            return 0

    def count_links_by_categories(self, category_ids: list[int]) -> dict[int, int]:
        """Batch link count for multiple categories in one query.

        Returns dictionary {category_id: count}. In case of error returns empty dictionary.
        """
        try:
            return self.db.links.count_links_by_categories(category_ids or [])
        except Exception as e:
            self.logger.error(
                "Error batch counting links for categories %s: %s",
                category_ids,
                e,
                exc_info=True,
            )
            return {}

    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: Optional[int] = None
    ) -> bool:
        """Checks for category duplicate in section."""
        try:
            return self.db.categories.has_duplicate_category(
                section_id, category_name, exclude_id
            )
        except Exception as e:
            self.logger.error(
                "Error checking category duplicate '%s' in section %s: %s",
                category_name,
                section_id,
                e,
                exc_info=True,
            )
            raise
