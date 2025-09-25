from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

# Модульный логгер для диагностических сообщений
logger = logging.getLogger(__name__)


class SelectionService:
    """Сервис выборок и вычислений на базе модели (без Qt и кэша)."""

    def get_spheres(self, structure_model, logger) -> List[Dict[str, Any]]:
        try:
            spheres = structure_model.get_spheres() or []
            return spheres
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error("Ошибка валидации данных при получении сфер: %s", e)
            return []
        except Exception as e:
            if logger:
                logger.exception("Критическая ошибка получения сфер")
            raise  # Пробрасываем критические ошибки

    def get_sections(
        self, structure_model, sphere_id: int, logger
    ) -> List[Dict[str, Any]]:
        try:
            sections = structure_model.get_sections(sphere_id) or []
            return sections
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error("Ошибка валидации данных при получении разделов для сферы %s: %s", sphere_id, e)
            return []
        except Exception as e:
            if logger:
                logger.exception("Критическая ошибка получения разделов для сферы %s", sphere_id)
            raise  # Пробрасываем критические ошибки

    def get_categories(
        self, structure_model, section_id: int, logger
    ) -> List[Dict[str, Any]]:
        try:
            categories = structure_model.get_categories(section_id) or []
            return categories
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error(
                    "Ошибка валидации данных при получении категорий для раздела %s: %s", section_id, e
                )
            return []
        except Exception as e:
            if logger:
                logger.exception(
                    "Критическая ошибка получения категорий для раздела %s", section_id
                )
            raise  # Пробрасываем критические ошибки

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
