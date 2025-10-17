from __future__ import annotations

import logging
from typing import Any

# Module logger for diagnostic messages
logger = logging.getLogger(__name__)


class LoaderService:
    """Structure loading service from DB/model."""

    def load_structure_from_db(
        self,
        structure_model,
        sphere_id: int,
        logger,
    ) -> list[dict[str, Any]]:
        """Load sections and categories for sphere.

        Does not know about caches and signals; only model reading and data collection.
        """
        try:
            sections = structure_model.get_sections(sphere_id) or []

            for section in sections:
                section_id = section.get("id")
                if section_id is None:
                    section["categories"] = []
                    continue
                categories = structure_model.get_categories(section_id) or []
                section["categories"] = categories

            return sections
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error("Data validation error while loading structure: %s", e)
            return []
        except Exception:
            if logger:
                logger.exception("Critical error loading structure from DB")
            raise  # Re-raise critical errors
