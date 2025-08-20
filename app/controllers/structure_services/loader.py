from __future__ import annotations

from typing import Any, Dict, List, Optional


class LoaderService:
    """Сервис загрузки структуры из БД/модели."""

    def load_structure_from_db(
        self,
        structure_model,
        sphere_id: int,
        logger,
    ) -> List[Dict[str, Any]]:
        """Загружает разделы и категории для сферы.

        Не знает о кэшах и сигналах; только чтение модели и сбор данных.
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
        except Exception as e:  # noqa: BLE001
            if logger:
                logger.error(f"Ошибка загрузки структуры из БД: {e}")
            return []
