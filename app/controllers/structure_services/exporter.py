from __future__ import annotations

import datetime
import logging
from typing import Any, Callable, Dict, List, Optional

# Модульный логгер для диагностических сообщений
logger = logging.getLogger(__name__)


class ExportService:
    """Сервис экспорта данных структуры.

    Не зависит от Qt. Получает доступ к данным через переданные функции.
    """

    def export_structure_data(
        self,
        current_sphere_id: Optional[int],
        get_spheres: Callable[[], List[Dict[str, Any]]],
        get_sections: Callable[[int], List[Dict[str, Any]]],
        get_categories: Callable[[int], List[Dict[str, Any]]],
        logger,
    ) -> Dict[str, Any]:
        """Экспортирует данные структуры для резервного копирования.

        Параметры повторяют текущие зависимости фасада, чтобы не тянуть Qt/модели внутрь сервиса.
        """
        try:
            export_data: Dict[str, Any] = {
                "spheres": [],
                "sections": [],
                "categories": [],
                "export_timestamp": datetime.datetime.now().isoformat(),
                "current_sphere_id": current_sphere_id,
            }

            # Экспортируем все сферы
            spheres = get_spheres() or []
            export_data["spheres"] = spheres

            # Экспортируем все разделы и категории
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
                    "Экспортированы данные структуры: %s сфер, %s разделов, %s категорий",
                    len(spheres),
                    len(export_data["sections"]),
                    len(export_data["categories"]),
                )

            return export_data

        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error("Ошибка валидации данных при экспорте структуры: %s", e)
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
                logger.exception("Критическая ошибка экспорта данных структуры")
            raise  # Пробрасываем критические ошибки
