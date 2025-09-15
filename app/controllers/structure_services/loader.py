from __future__ import annotations

from typing import Any, Dict, List


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
        except Exception as e:  # критические ошибки (например, БД)
            if logger:
                try:
                    logger.error("Ошибка загрузки структуры из БД: %s", e, exc_info=True)
                except Exception:
                    # Никогда не ломаем повторное возбуждение из-за логгера
                    pass
            # Пробрасываем дальше, чтобы вызывающий код мог обработать/показать ошибку
            raise
