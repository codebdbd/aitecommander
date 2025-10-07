from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

# Module logger for diagnostic messages
logger = logging.getLogger(__name__)


class SelectionService:
    """Selection and computation service based on model (without Qt and cache)."""

    def get_spheres(self, structure_model, logger) -> List[Dict[str, Any]]:
        try:
            spheres = structure_model.get_spheres() or []
            return spheres
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error("Data validation error while getting spheres: %s", e)
            return []
        except Exception as e:
            if logger:
                logger.exception("Critical error getting spheres")
            raise  # Re-raise critical errors

    def get_sections(
        self, structure_model, sphere_id: int, logger
    ) -> List[Dict[str, Any]]:
        try:
            sections = structure_model.get_sections(sphere_id) or []
            return sections
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error("Data validation error while getting sections for sphere %s: %s", sphere_id, e)
            return []
        except Exception as e:
            if logger:
                logger.exception("Critical error getting sections for sphere %s", sphere_id)
            raise  # Re-raise critical errors

    def get_categories(
        self, structure_model, section_id: int, logger
    ) -> List[Dict[str, Any]]:
        try:
            categories = structure_model.get_categories(section_id) or []
            return categories
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error(
                    "Data validation error while getting categories for section %s: %s", section_id, e
                )
            return []
        except Exception as e:
            if logger:
                logger.exception(
                    "Critical error getting categories for section %s", section_id
                )
            raise  # Re-raise critical errors

    def get_first_category_id(
        self,
        current_sphere_id: Optional[int],
        get_sections: Callable[[int], List[Dict[str, Any]]],
        get_categories: Callable[[int], List[Dict[str, Any]]],
    ) -> Optional[int]:
        if current_sphere_id is None:
            return None
        sections = get_sections(current_sphere_id) or []
        for section in sections:
            section_id = section.get("id")
            if section_id is None:
                continue
            categories = get_categories(section_id) or []
            if categories:
                return categories[0].get("id")
        return None
