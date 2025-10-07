from __future__ import annotations

import datetime
import logging
from typing import Any, Callable, Dict, List, Optional

# Module logger for diagnostic messages
logger = logging.getLogger(__name__)


class ExportService:
    """Structure data export service.

    Does not depend on Qt. Accesses data through passed functions.
    """

    def export_structure_data(
        self,
        current_sphere_id: Optional[int],
        get_spheres: Callable[[], List[Dict[str, Any]]],
        get_sections: Callable[[int], List[Dict[str, Any]]],
        get_categories: Callable[[int], List[Dict[str, Any]]],
        logger,
    ) -> Dict[str, Any]:
        """Export structure data for backup.

        Parameters repeat current facade dependencies to avoid pulling Qt/models into the service.
        """
        try:
            export_data: Dict[str, Any] = {
                "spheres": [],
                "sections": [],
                "categories": [],
                "export_timestamp": datetime.datetime.now().isoformat(),
                "current_sphere_id": current_sphere_id,
            }

            # Export all spheres
            spheres = get_spheres() or []
            export_data["spheres"] = spheres

            # Export all sections and categories
            for sphere in spheres:
                sphere_id = sphere.get("id")
                if sphere_id is None:
                    continue
                sections = get_sections(sphere_id) or []
                export_data["sections"].extend(sections)

                for section in sections:
                    section_id = section.get("id")
                    if section_id is None:
                        continue
                    categories = get_categories(section_id) or []
                    export_data["categories"].extend(categories)

            if logger:
                logger.info(
                    "Exported structure data: %s spheres, %s sections, %s categories",
                    len(spheres),
                    len(export_data["sections"]),
                    len(export_data["categories"]),
                )

            return export_data

        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error("Data validation error during structure export: %s", e)
            return {
                "spheres": [],
                "sections": [],
                "categories": [],
                "export_timestamp": None,
                "current_sphere_id": None,
                "error": str(e),
            }
        except Exception as e:
            if logger:
                logger.exception("Critical error exporting structure data")
            raise  # Re-raise critical errors
