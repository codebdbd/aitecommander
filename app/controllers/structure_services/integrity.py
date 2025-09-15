from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


class IntegrityService:
    """Сервис проверки целостности и статистики структуры."""

    def get_statistics(
        self,
        get_spheres: Callable[[], List[Dict[str, Any]]],
        get_sections: Callable[[int], List[Dict[str, Any]]],
        get_categories: Callable[[int], List[Dict[str, Any]]],
        current_sphere_id: Optional[int],
        logger,
    ) -> Dict[str, Any]:
        try:
            stats: Dict[str, Any] = {
                "spheres_count": 0,
                "sections_count": 0,
                "categories_count": 0,
                "current_sphere_sections": 0,
                "current_sphere_categories": 0,
            }

            spheres = get_spheres() or []
            stats["spheres_count"] = len(spheres)

            total_sections = 0
            total_categories = 0
            for sphere in spheres:
                sphere_id = sphere.get("id")
                if sphere_id is None:
                    continue
                sections = get_sections(sphere_id) or []
                total_sections += len(sections)
                for section in sections:
                    section_id = section.get("id")
                    if section_id is None:
                        continue
                    categories = get_categories(section_id) or []
                    total_categories += len(categories)

            stats["sections_count"] = total_sections
            stats["categories_count"] = total_categories

            if current_sphere_id is not None:
                current_sections = get_sections(current_sphere_id) or []
                stats["current_sphere_sections"] = len(current_sections)
                current_categories = 0
                for section in current_sections:
                    sec_id = section.get("id")
                    if sec_id is None:
                        continue
                    categories = get_categories(sec_id) or []
                    current_categories += len(categories)
                stats["current_sphere_categories"] = current_categories

            return stats
        except Exception as e:  # noqa: BLE001
            if logger:
                logger.error("Ошибка получения статистики: %s", e)
            return {
                "spheres_count": 0,
                "sections_count": 0,
                "categories_count": 0,
                "current_sphere_sections": 0,
                "current_sphere_categories": 0,
            }

    def validate_structure_integrity(
        self,
        get_spheres: Callable[[], List[Dict[str, Any]]],
        get_sections: Callable[[int], List[Dict[str, Any]]],
        get_categories: Callable[[int], List[Dict[str, Any]]],
        get_statistics: Callable[[], Dict[str, Any]],
        logger,
    ) -> Dict[str, Any]:
        try:
            integrity_report: Dict[str, Any] = {
                "is_valid": True,
                "errors": [],
                "warnings": [],
                "statistics": {},
            }

            spheres = get_spheres() or []
            for sphere in spheres:
                sphere_id = sphere.get("id")
                sections = get_sections(sphere_id) if sphere_id is not None else []
                for section in sections:
                    section_id = section.get("id")
                    if section.get("sphere_id") != sphere_id:
                        integrity_report["errors"].append(
                            f"Раздел {section_id} имеет неверную связь со сферой"
                        )
                        integrity_report["is_valid"] = False

                    categories = (
                        get_categories(section_id) if section_id is not None else []
                    )
                    for category in categories:
                        category_id = category.get("id")
                        if category.get("section_id") != section_id:
                            integrity_report["errors"].append(
                                f"Категория {category_id} имеет неверную связь с разделом"
                            )
                            integrity_report["is_valid"] = False

            integrity_report["statistics"] = get_statistics()
            return integrity_report
        except Exception as e:  # noqa: BLE001
            if logger:
                logger.error("Ошибка проверки целостности структуры: %s", e)
            return {
                "is_valid": False,
                "errors": [f"Ошибка проверки: {str(e)}"],
                "warnings": [],
                "statistics": {},
            }
