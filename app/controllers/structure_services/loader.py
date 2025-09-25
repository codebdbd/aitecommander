from __future__ import annotations

import logging
from typing import Any, Dict, List

# Модульный логгер для диагностических сообщений
logger = logging.getLogger(__name__)


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
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error("Ошибка валидации данных при загрузке структуры: %s", e)
            return []
        except Exception as e:
            if logger:
                logger.exception("Критическая ошибка загрузки структуры из БД")
            raise  # Пробрасываем критические ошибки
