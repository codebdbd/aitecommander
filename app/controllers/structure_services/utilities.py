from __future__ import annotations

import logging
from typing import Any, Callable

from app.models import StructureModel

# Module logger for diagnostic messages (does not enforce logger parameter)
logger = logging.getLogger(__name__)


class UtilityService:
    """Auxiliary and compatible operations for structure."""

    def get_links(
        self,
        model: StructureModel,
        category_id: int,
        logger: logging.Logger | None = None,
    ) -> list[dict[str, Any]]:
        try:
            links = model.get_links(category_id)
            return links or []
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error(
                    "Data validation error while getting links for category %s: %s",
                    category_id,
                    e,
                )
            return []
        except Exception:
            if logger:
                logger.exception(
                    "Critical error getting links for category %s", category_id
                )
            raise  # Re-raise critical errors

    def get_item_for_editing(
        self,
        item_id: int,
        item_type: str | Any,
        get_section_data: Callable[[int], dict[str, Any] | None],
        get_category_data: Callable[[int], dict[str, Any] | None],
        logger: logging.Logger | None = None,
    ) -> dict[str, Any] | None:
        try:
            if not isinstance(item_type, str) and hasattr(item_type, "value"):
                item_type = item_type.value
            if item_type == "section":
                return get_section_data(item_id)
            if item_type == "category":
                return get_category_data(item_id)
            return None
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error(
                    "Data validation error while getting item %s of type %s: %s",
                    item_id,
                    item_type,
                    e,
                )
            return None
        except Exception:
            if logger:
                logger.exception(
                    "Critical error getting item %s of type %s", item_id, item_type
                )
            raise  # Re-raise critical errors

    def get_category_hierarchy(
        self,
        category_id: int,
        get_category_data: Callable[[int], dict[str, Any] | None],
        get_section_data: Callable[[int], dict[str, Any] | None],
        get_sphere_by_id: Callable[[int], dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        category_data = get_category_data(category_id)
        if not category_data:
            return None
        section_id = category_data.get("section_id")
        if not section_id:
            return None
        section_data = get_section_data(section_id)
        if not section_data:
            return None
        sphere_id = section_data.get("sphere_id")
        sphere_data = get_sphere_by_id(sphere_id) if sphere_id else None
        return {
            "category": category_data,
            "section": section_data,
            "sphere": sphere_data,
            "sphere_id": sphere_id,
        }

    def get_target_section_id(
        self,
        current_sphere_id: int | None,
        get_sections: Callable[[int], list[dict[str, Any]]],
        get_categories: Callable[[int], list[dict[str, Any]]],
        cache_get: Callable[[str], Any],
        cache_set: Callable[[str, Any], None],
    ) -> int | None:
        if current_sphere_id is None:
            return None
        # Unified cache key format (per-sphere), consistent with CacheManager: 'first_category_id:{sphere_id}'
        cache_key = f"first_category_id:{current_sphere_id}"
        cached = cache_get(cache_key)
        if cached is not None:
            try:
                logger.debug("first_category cache HIT: key=%s → %s", cache_key, cached)
            except Exception:
                pass
            return cached
        sections = get_sections(current_sphere_id)
        try:
            logger.debug(
                "first_category cache MISS: key=%s; sections_count=%s",
                cache_key,
                len(sections) if isinstance(sections, list) else "?",
            )
        except Exception:
            pass
        for section in sections:
            categories = get_categories(section["id"])
            if categories:
                first_category_id = categories[0]["id"]
                cache_set(cache_key, first_category_id)
                try:
                    logger.debug(
                        "first_category cache SET: key=%s → %s (section=%s, cats=%s)",
                        cache_key,
                        first_category_id,
                        section.get("id"),
                        len(categories) if isinstance(categories, list) else "?",
                    )
                except Exception:
                    pass
                return first_category_id
        cache_set(cache_key, None)
        try:
            logger.debug("first_category cache SET: key=%s → None (no categories)", cache_key)
        except Exception:
            pass
        return None

    def get_first_category_id(
        self,
        current_sphere_id: int | None,
        get_categories: Callable[[int], list[dict[str, Any]]],
        cache_get: Callable[[str], Any],
        cache_set: Callable[[str, Any], None],
    ) -> int | None:
        """Alias for get_target_section_id for backward compatibility.
        
        Uses the same logic as get_target_section_id.
        """
        return self.get_target_section_id(
            current_sphere_id,
            get_categories,
            get_categories,
            cache_get,
            cache_set,
        )

    def update_item_positions(
        self,
        table_name: str,
        ids_in_order: list[int],
        model: StructureModel,
        cache_invalidate: Callable[[str], None],
        logger: logging.Logger | None = None,
    ) -> bool:
        """Update item positions.

        Strengthened table name validation: instead of silent success on
        unsupported table_name, method now logs error and returns False.

        Valid names (input → DB):
          - "sections"  → "section"
          - "categories"→ "category"
          - "spheres"   → "sphere"
          - "links"     → "link"

        Actual update is delegated to model (`StructureModel.update_item_positions`),
        which proxies call to `Database.update_item_positions` with full validation and
        correct position reassembly.
        """
        try:
            name_map = {
                "sections": "section",
                "categories": "category",
                "spheres": "sphere",
                "links": "link",
            }
            normalized = name_map.get(table_name)
            if not normalized:
                if logger:
                    logger.error(
                        "update_item_positions: unsupported table name: %s",
                        table_name,
                    )
                return False

            # Delegate atomic order update to DB layer through model
            model.update_item_positions(normalized, ids_in_order)

            # Invalidate cache by original key and normalized name (just in case)
            try:
                cache_invalidate(table_name)
            except Exception:
                pass
            if table_name != normalized:
                try:
                    cache_invalidate(normalized)
                except Exception:
                    pass
            return True
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error("Data validation error while updating positions in %s: %s", table_name, e)
            return False
        except Exception:
            if logger:
                logger.exception("Critical error updating positions in %s", table_name)
            raise  # Re-raise critical errors

