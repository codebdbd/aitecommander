from __future__ import annotations

import logging
from typing import Any, Callable

# Module logger for diagnostic messages
logger = logging.getLogger(__name__)


class IntegrityService:
    """Structure integrity and statistics service."""

    def get_statistics(
        self,
        get_spheres: Callable[[], list[dict[str, Any]]],
        get_sections: Callable[[int], list[dict[str, Any]]],
        get_categories: Callable[[int], list[dict[str, Any]]],
        current_sphere_id: int | None,
        logger,
    ) -> dict[str, Any]:
        try:
            stats: dict[str, Any] = {
                "spheres_count": 0,
                "sections_count": 0,
                "categories_count": 0,
                "current_sphere_sections": 0,
                "current_sphere_categories": 0,
            }

            spheres = get_spheres() or []
            stats["spheres_count"] = len(spheres)

            # Optimization: collect statistics in one pass
            total_sections = 0
            total_categories = 0
            current_sphere_sections = 0
            current_sphere_categories = 0

            # Cache for sections to avoid calling get_sections twice for current_sphere
            sections_cache = {}

            for sphere in spheres:
                sphere_id = sphere.get("id")
                if sphere_id is None:
                    continue

                sections = get_sections(sphere_id) or []
                sections_cache[sphere_id] = sections
                total_sections += len(sections)

                # Count categories for all sections of sphere
                sphere_categories = 0
                for section in sections:
                    section_id = section.get("id")
                    if section_id is not None:
                        categories = get_categories(int(section_id)) or []
                        sphere_categories += len(categories)
                total_categories += sphere_categories

                # If this is the current sphere, save statistics
                if sphere_id == current_sphere_id:
                    current_sphere_sections = len(sections)
                    current_sphere_categories = sphere_categories

            stats["sections_count"] = total_sections
            stats["categories_count"] = total_categories
            stats["current_sphere_sections"] = current_sphere_sections
            stats["current_sphere_categories"] = current_sphere_categories

            return stats
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error("Data validation error while getting statistics: %s", e)
            return {
                "spheres_count": 0,
                "sections_count": 0,
                "categories_count": 0,
                "current_sphere_sections": 0,
                "current_sphere_categories": 0,
            }
        except Exception:
            if logger:
                logger.exception("Critical error getting statistics")
            raise  # Re-raise critical errors

    def validate_structure_integrity(
        self,
        get_spheres: Callable[[], list[dict[str, Any]]],
        get_sections: Callable[[int], list[dict[str, Any]]],
        get_categories: Callable[[int], list[dict[str, Any]]],
        get_statistics: Callable[[], dict[str, Any]],
        logger,
    ) -> dict[str, Any]:
        try:
            spheres = get_spheres() or []
            errors = self._validate_spheres(
                spheres,
                get_sections,
                get_categories,
            )

            return {
                "is_valid": len(errors) == 0,
                "errors": errors,
                "warnings": [],
                "statistics": get_statistics(),
            }
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error("Data validation error during integrity check: %s", e)
            return {
                "is_valid": False,
                "errors": [
                    f"Validation error: {str(e)}",
                ],
                "warnings": [],
                "statistics": {},
            }
        except Exception:
            if logger:
                logger.exception("Critical error checking structure integrity")
            return {
                "is_valid": False,
                "errors": ["Critical error during integrity check"],
                "warnings": [],
                "statistics": {},
            }

    def _validate_spheres(
        self,
        spheres: list[dict[str, Any]],
        get_sections: Callable[[int], list[dict[str, Any]]],
        get_categories: Callable[[int], list[dict[str, Any]]],
    ) -> list[str]:
        errors: list[str] = []
        for sphere in spheres:
            sphere_id = sphere.get("id")
            if sphere_id is None:
                continue

            sections = get_sections(sphere_id) or []
            errors.extend(self._validate_sections(sphere_id, sections, get_categories))

        return errors

    def _validate_sections(
        self,
        sphere_id: int,
        sections: list[dict[str, Any]],
        get_categories: Callable[[int], list[dict[str, Any]]],
    ) -> list[str]:
        errors: list[str] = []
        errors.extend(self._find_invalid_sections(sphere_id, sections))

        for section in sections:
            section_id = section.get("id")
            if section_id is None:
                continue

            categories = get_categories(section_id) or []
            errors.extend(self._find_invalid_categories(section_id, categories))

        return errors

    def _find_invalid_sections(
        self, sphere_id: int, sections: list[dict[str, Any]]
    ) -> list[str]:
        return [
            f"Section {section.get('id')} has invalid sphere relationship"
            for section in sections
            if section.get("sphere_id") != sphere_id
        ]

    def _find_invalid_categories(
        self, section_id: int, categories: list[dict[str, Any]]
    ) -> list[str]:
        return [
            f"Category {category.get('id')} has invalid section relationship"
            for category in categories
            if category.get("section_id") != section_id
        ]
