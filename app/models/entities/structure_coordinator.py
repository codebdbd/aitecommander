# app/models/entities/structure_coordinator.py

"""
Structure Coordinator - manages write operations with transaction handling.

This coordinator provides a unified interface for structure modification operations
(create, update, delete) with proper transaction management, error handling, and logging.

For READ operations, use db.spheres/sections/categories directly:
    - db.spheres.get_spheres()
    - db.sections.get_sections(sphere_id)
    - db.categories.get_categories(section_id)

For WRITE operations, use this coordinator:
    - coordinator.upsert_sphere(data)
    - coordinator.create_section(data)
    - coordinator.delete_category(category_id)
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from app.models.db import Database

logger = logging.getLogger(__name__)


class StructureCoordinator:
    """Coordinator for structure write operations with transaction management.
    
    Responsibilities:
    - Transaction management for atomic operations
    - Error handling and logging
    - Business rules validation
    - Coordinating complex multi-model operations
    
    Architecture:
    - READ operations: Use db.* directly (no coordinator needed)
    - WRITE operations: Use coordinator (ensures consistency)
    
    Example:
        # Read (direct access)
        spheres = db.spheres.get_spheres()
        
        # Write (through coordinator)
        sphere_id = coordinator.upsert_sphere({"name": "Work"})
    """

    def __init__(self, db: "Database", logger: Optional[logging.Logger] = None):
        """Initialize coordinator with database connection.
        
        Args:
            db: Database instance
            logger: Optional logger instance
        """
        self.db = db
        self.logger = logger or globals().get("logger") or logging.getLogger(__name__)

    # ========================================================================
    # SPHERE OPERATIONS
    # ========================================================================

    def upsert_sphere(self, data: dict[str, Any]) -> int:
        """Insert or update sphere with transaction handling.
        
        Args:
            data: Sphere data (id, name, icon_path, position)
            
        Returns:
            Sphere ID
        """
        return self.db.spheres.upsert_sphere(data)

    def create_sphere(self, data: dict[str, Any]) -> Optional[int]:
        """Create new sphere with error handling.
        
        Args:
            data: Sphere data (name, icon_path, position)
            
        Returns:
            Sphere ID on success, None on error
        """
        try:
            return self.upsert_sphere(data)
        except Exception as e:
            self.logger.error("Error creating sphere: %s", e, exc_info=True)
            return None

    def update_sphere(self, sphere_id: int, data: dict[str, Any]) -> bool:
        """Update sphere by ID.
        
        Args:
            sphere_id: Sphere ID
            data: Updated sphere data
            
        Returns:
            True on success, False on error
        """
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

    # ========================================================================
    # SECTION OPERATIONS
    # ========================================================================

    def upsert_section(self, data: dict[str, Any]) -> int:
        """Insert or update section with transaction handling.
        
        Args:
            data: Section data (id, name, sphere_id, icon_path, position)
            
        Returns:
            Section ID
        """
        with self.db.transaction():
            return self.db.sections.upsert_section(data)

    def create_section(self, data: dict[str, Any]) -> Optional[int]:
        """Create new section with error handling.
        
        Args:
            data: Section data (name, sphere_id, icon_path, position)
            
        Returns:
            Section ID on success, None on error
            
        Note:
            Logs ValueError (duplicate) as warning, other errors as error.
        """
        try:
            return self.upsert_section(data)
        except ValueError as e:
            self.logger.warning("Duplicate section rejected: %s", e)
            return None
        except Exception as e:
            self.logger.error("Error creating section: %s", e, exc_info=True)
            return None

    def update_section(self, section_id: int, data: dict[str, Any]) -> bool:
        """Update section by ID.
        
        Args:
            section_id: Section ID
            data: Updated section data
            
        Returns:
            True on success, False on error
        """
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

    def delete_section(self, section_id: int) -> bool:
        """Delete section by ID.
        
        Args:
            section_id: Section ID
            
        Returns:
            True on success, False on error
        """
        try:
            self.db.sections.delete_section(section_id)
            return True
        except Exception as e:
            self.logger.error(
                "Error deleting section %s: %s", section_id, e, exc_info=True
            )
            return False

    # ========================================================================
    # CATEGORY OPERATIONS
    # ========================================================================

    def upsert_category(self, data: dict[str, Any]) -> int:
        """Insert or update category with transaction handling.
        
        Args:
            data: Category data (id, name, section_id, icon_path, position)
            
        Returns:
            Category ID
        """
        return self.db.categories.upsert_category(data)

    def create_category(self, data: dict[str, Any]) -> Optional[int]:
        """Create new category with error handling.
        
        Args:
            data: Category data (name, section_id, icon_path, position)
            
        Returns:
            Category ID on success, None on error
        """
        try:
            with self.db.transaction():
                cat_id = self.db.categories.insert_category(data)
                return cat_id
        except Exception as e:
            self.logger.error("Error creating category: %s", e, exc_info=True)
            return None

    def create_categories_bulk(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Bulk category creation (atomically).
        
        Delegates to CategoryModel.insert_categories_bulk and returns list
        of actual category records after operation (both new and existing
        from name set), for UI/cache synchronization.
        """
        try:
            result = self.db.categories.insert_categories_bulk(items or [])
            # Extract 'inserted' list from BulkInsertResult
            if isinstance(result, dict) and "inserted" in result:
                return result["inserted"] or []
            return []
        except Exception as e:
            self.logger.error("Error bulk creating categories: %s", e, exc_info=True)
            return []

    def get_categories_batch(self, section_ids: list[int]) -> list[dict[str, Any]]:
        """Get categories for multiple sections with one optimized query."""
        if not section_ids:
            return []

        try:
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
        """Count categories and links in section."""
        categories_data = self.db.categories.get_categories(section_id)
        cats_count = len(categories_data) if categories_data else 0

        links_count = 0
        if categories_data:
            for category_row in categories_data:
                category_id = category_row["id"]
                links_count += self.db.links.count_links_by_category(category_id)

        return cats_count, links_count

    def update_category(self, category_id: int, data: dict[str, Any]) -> bool:
        """Update category by ID.
        
        Args:
            category_id: Category ID
            data: Updated category data
            
        Returns:
            True on success, False on error
        """
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

    def delete_category(self, category_id: int) -> bool:
        """Delete category by ID.
        
        Args:
            category_id: Category ID
            
        Returns:
            True on success, False on error
        """
        try:
            self.db.categories.delete_category(category_id)
            return True
        except Exception as e:
            self.logger.error(
                "Error deleting category %s: %s", category_id, e, exc_info=True
            )
            return False

    # ========================================================================
    # COMPLEX OPERATIONS
    # ========================================================================

    def get_category_hierarchy(self, category_id: int) -> Optional[dict[str, Any]]:
        """Get category hierarchy with validation and normalization.
        
        This method adds validation logic on top of the basic model method.
        
        Args:
            category_id: Category ID
            
        Returns:
            Dictionary with sphere_id and section_id, or None if not found
        """
        hierarchy_data = self.db.categories.get_category_hierarchy(category_id)
        if not hierarchy_data:
            return None

        try:
            if not isinstance(hierarchy_data, dict):
                self.logger.warning(
                    "Incorrect hierarchy format for category %s: %s",
                    category_id,
                    type(hierarchy_data),
                )
                return None

            sphere_id = hierarchy_data.get("sphere_id")
            section_id = hierarchy_data.get("section_id")
            
            # Support legacy keys
            if sphere_id is None:
                sphere_id = hierarchy_data.get("sphereId")
            if section_id is None:
                section_id = hierarchy_data.get("sectionId")

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

    def get_first_category_id(self) -> Optional[int]:
        """Get ID of first category in system.
        
        Returns:
            First category ID or None if no categories exist
        """
        try:
            spheres = self.db.spheres.get_spheres()
            if not spheres:
                return None

            for sphere in spheres:
                sphere_id = sphere.get("id")
                if not sphere_id:
                    continue

                sections = self.db.sections.get_sections(sphere_id)
                if not sections:
                    continue

                for section in sections:
                    section_id = section.get("id")
                    if not section_id:
                        continue

                    categories = self.db.categories.get_categories(section_id)
                    if categories:
                        return categories[0].get("id")

            return None
        except Exception as e:
            self.logger.error("Error getting first category: %s", e, exc_info=True)
            return None

    # ========================================================================
    # LINK OPERATIONS
    # ========================================================================

    def create_link(self, link_data: dict[str, Any]) -> Optional[int]:
        """Create or update link with error handling.
        
        Args:
            link_data: Link data (category_id, name, url, type, etc.)
            
        Returns:
            Link ID on success, None on error
        """
        try:
            link_id = self.db.links.upsert_link(link_data)
            return link_id
        except Exception as e:
            self.logger.error("Error creating link: %s", e, exc_info=True)
            return None

    def get_links(self, category_id: int) -> list[dict[str, Any]]:
        """Get links for category with error handling.
        
        Args:
            category_id: Category ID
            
        Returns:
            List of links
        """
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
        """Return number of links for specified category (efficient count)."""
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

    # ========================================================================
    # VALIDATION OPERATIONS
    # ========================================================================

    def has_duplicate_section(
        self, sphere_id: int, section_name: str, exclude_id: Optional[int] = None
    ) -> bool:
        """Check for section duplicate in sphere.
        
        Args:
            sphere_id: Sphere ID to check within
            section_name: Section name to check
            exclude_id: Optional section ID to exclude from check (for updates)
            
        Returns:
            True if duplicate exists, False otherwise
        """
        try:
            return self.db.sections.has_duplicate_section(
                sphere_id, section_name, exclude_id
            )
        except Exception as e:
            self.logger.error(
                "Error checking section duplicate '%s' in sphere %s: %s",
                section_name,
                sphere_id,
                e,
                exc_info=True,
            )
            raise

    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: Optional[int] = None
    ) -> bool:
        """Check for category duplicate in section.
        
        Args:
            section_id: Section ID to check within
            category_name: Category name to check
            exclude_id: Optional category ID to exclude from check (for updates)
            
        Returns:
            True if duplicate exists, False otherwise
        """
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

    # ========================================================================
    # POSITIONING OPERATIONS
    # ========================================================================

    def update_item_positions(
        self, table_name: str, ids_in_order: list[int]
    ) -> None:
        """Update positions for multiple items atomically.
        
        Args:
            table_name: Table name (sphere, section, category, link)
            ids_in_order: List of item IDs in desired order
        """
        self.db.update_item_positions(table_name, ids_in_order)
