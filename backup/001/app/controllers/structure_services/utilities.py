from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Union

from app.models import StructureModel

# Модульный логгер для диагностических сообщений (не навязывает параметр logger)
logger = logging.getLogger(__name__)


class UtilityService:
    """Вспомогательные и совместимые операции для структуры."""

    def get_links(
        self,
        model: StructureModel,
        category_id: int,
        logger: Optional[logging.Logger] = None,
    ) -> List[Dict[str, Any]]:
        try:
            links = model.get_links(category_id)
            return links or []
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error(
                    "Ошибка валидации данных при получении ссылок для категории %s: %s",
                    category_id,
                    e,
                )
            return []
        except Exception as e:
            if logger:
                logger.exception(
                    "Критическая ошибка получения ссылок для категории %s", category_id
                )
            raise  # Пробрасываем критические ошибки

    def get_item_for_editing(
        self,
        item_id: int,
        item_type: Union[str, Any],
        get_section_data: Callable[[int], Optional[Dict[str, Any]]],
        get_category_data: Callable[[int], Optional[Dict[str, Any]]],
        logger: Optional[logging.Logger] = None,
    ) -> Optional[Dict[str, Any]]:
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
                    "Ошибка валидации данных при получении элемента %s типа %s: %s",
                    item_id,
                    item_type,
                    e,
                )
            return None
        except Exception as e:
            if logger:
                logger.exception(
                    "Критическая ошибка получения элемента %s типа %s", item_id, item_type
                )
            raise  # Пробрасываем критические ошибки

    def get_category_hierarchy(
        self,
        category_id: int,
        get_category_data: Callable[[int], Optional[Dict[str, Any]]],
        get_section_data: Callable[[int], Optional[Dict[str, Any]]],
        get_sphere_by_id: Callable[[int], Optional[Dict[str, Any]]],
    ) -> Optional[Dict[str, Any]]:
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
        current_sphere_id: Optional[int],
        get_sections: Callable[[int], List[Dict[str, Any]]],
        get_categories: Callable[[int], List[Dict[str, Any]]],
        cache_get: Callable[[str], Any],
        cache_set: Callable[[str, Any], None],
    ) -> Optional[int]:
        if current_sphere_id is None:
            return None
        # Единый формат ключа кэша (per-sphere), согласованный с CacheManager: 'first_category_id:{sphere_id}'
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
        current_sphere_id: Optional[int],
        get_sections: Callable[[int], List[Dict[str, Any]]],
        get_categories: Callable[[int], List[Dict[str, Any]]],
        cache_get: Callable[[str], Any],
        cache_set: Callable[[str, Any], None],
    ) -> Optional[int]:
        """Алиас для get_target_section_id для обратной совместимости.
        
        Использует ту же логику, что и get_target_section_id.
        """
        return self.get_target_section_id(
            current_sphere_id,
            get_sections,
            get_categories,
            cache_get,
            cache_set,
        )

    def update_item_positions(
        self,
        table_name: str,
        ids_in_order: List[int],
        model: StructureModel,
        cache_invalidate: Callable[[str], None],
        logger: Optional[logging.Logger] = None,
    ) -> bool:
        """Обновляет позиции элементов.

        Усилен контроль корректности имени таблицы: вместо молчаливого успеха при
        неподдерживаемом table_name метод теперь логирует ошибку и возвращает False.

        Допустимые имена (вход → БД):
          - "sections"  → "section"
          - "categories"→ "category"
          - "spheres"   → "sphere"
          - "links"     → "link"

        Фактическое обновление делегируется в модель (`StructureModel.update_item_positions`),
        которая проксирует вызов в `Database.update_item_positions` с полной валидацией и
        корректной пересборкой позиций.
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
                        "update_item_positions: неподдерживаемое имя таблицы: %s",
                        table_name,
                    )
                return False

            # Делегируем атомарное обновление порядков в слой БД через модель
            model.update_item_positions(normalized, ids_in_order)

            # Инвалидируем кэш по исходному ключу и нормализованному имени (на всякий случай)
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
                logger.error("Ошибка валидации данных при обновлении позиций в %s: %s", table_name, e)
            return False
        except Exception as e:
            if logger:
                logger.exception("Критическая ошибка обновления позиций в %s", table_name)
            raise  # Пробрасываем критические ошибки
