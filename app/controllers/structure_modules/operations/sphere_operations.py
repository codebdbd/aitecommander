# app/controllers/structure_modules/sphere_operations.py

"""Module for sphere operations."""

from typing import Any, Dict, List, Optional

from .base import BaseOperations


class SphereOperations(BaseOperations):
    """Class for sphere operations."""

    def get_spheres(self) -> List[Dict[str, Any]]:
        """Get list of all spheres with guaranteed normalization."""

        def _load_spheres():
            result = self.structure_model.get_spheres() or []
            self.logger.debug("Loaded %s spheres", len(result))
            return result

        return self._exec_with_norm(
            _load_spheres, "load list of spheres", default_return=[]
        )

    def get_sphere_by_id(self, sphere_id: int) -> Optional[Dict[str, Any]]:
        """Get sphere data by ID with guaranteed normalization."""
        # Input data validation
        if not isinstance(sphere_id, int) or sphere_id <= 0:
            self.logger.warning("Invalid sphere ID: %s", sphere_id)
            return None

        def _get_sphere():
            sphere_data = self.structure_model.get_sphere_by_id(sphere_id)
            if sphere_data:
                self.logger.debug("Found sphere %s", sphere_id)
                return sphere_data
            else:
                self.logger.warning("Sphere %s not found", sphere_id)
                return None

        return self._exec_with_norm(
            _get_sphere, f"load data for sphere {sphere_id}", default_return=None
        )

    def get_next_sphere_id(self, current_sphere_id: Optional[int]) -> Optional[int]:
        """Determine and return the next sphere ID in the list (cyclically).

        Args:
            current_sphere_id: Current sphere ID or None to get the first sphere

        Returns:
            Next sphere ID or None if not enough spheres for switching
        """

        def _get_next_sphere():
            spheres = self.structure_model.get_spheres()
            if not spheres:
                return None

            # Data from StructureModel is already dict
            MIN_SPHERES_FOR_SWITCHING = 2
            if len(spheres) < MIN_SPHERES_FOR_SWITCHING:
                self.logger.warning("Not enough spheres for switching.")
                return None

            if current_sphere_id is None:
                first_sphere_id = spheres[0]["id"]
                self.logger.debug("Returned first sphere: %s", first_sphere_id)
                return first_sphere_id

            sphere_ids = []
            current_found = False

            for sphere in spheres:
                sphere_id = sphere["id"]
                sphere_ids.append(sphere_id)
                if sphere_id == current_sphere_id:
                    current_found = True

            if not current_found:
                self.logger.warning(
                    "Current sphere with ID %s not found in list.", current_sphere_id
                )
                fallback_sphere_id = sphere_ids[0]
                self.logger.debug("Returned fallback sphere: %s", fallback_sphere_id)
                return fallback_sphere_id

            current_index = sphere_ids.index(current_sphere_id)
            next_index = (current_index + 1) % len(sphere_ids)
            next_sphere_id = sphere_ids[next_index]

            self.logger.info("Next sphere for switching: %s", next_sphere_id)
            return next_sphere_id

        return self._exec_with_norm(
            _get_next_sphere, "determine next sphere", default_return=None
        )

    def get_target_section_id(self, current_sphere_id: Optional[int]) -> Optional[int]:
        """Get ID of first available section in current sphere.

        Args:
            current_sphere_id: Sphere ID to search sections in

        Returns:
            First section ID or None if no section or sphere not specified
        """
        if current_sphere_id is None:
            self.logger.debug(
                "Sphere ID not specified, target section cannot be determined"
            )
            return None

        # Input data validation
        if not isinstance(current_sphere_id, int) or current_sphere_id <= 0:
            self.logger.warning("Invalid sphere ID: %s", current_sphere_id)
            return None

        def _get_target_section():
            sections_data = self.structure_model.get_sections(current_sphere_id)
            if not sections_data:
                self.logger.debug("Sections in sphere %s not found", current_sphere_id)
                return None

            # Data from StructureModel is already dict; take first section
            section_id = sections_data[0]["id"]
            self.logger.debug(
                "Found target section %s in sphere %s",
                section_id,
                current_sphere_id,
            )
            return section_id

        return self._exec_with_norm(
            _get_target_section,
            f"get target section in sphere {current_sphere_id}",
            default_return=None,
        )

    def _validate_sphere_id(self, sphere_id: Any) -> bool:
        """Validate sphere ID correctness.

        Args:
            sphere_id: Value to check

        Returns:
            True if ID is valid, False otherwise
        """
        return isinstance(sphere_id, int) and sphere_id > 0
