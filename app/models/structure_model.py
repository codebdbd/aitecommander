# app/models/structure_model.py

"""Модель для работы со структурой (сферы, разделы, категории)."""

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.models.db import Database


class StructureModel:
    """Модель для работы со структурой."""
    
    def __init__(self, db: Database, logger: Optional[logging.Logger] = None):
        self.db = db
        self.logger = logger or logging.getLogger(__name__)
    
    def get_spheres(self) -> List[Dict[str, Any]]:
        """Возвращает список всех сфер."""
        spheres_raw = self.db.spheres.get_spheres()
        # Нужно преобразовать в dict для совместимости с .get() методом
        return [dict(sphere) for sphere in spheres_raw] if spheres_raw else []
    
    def get_sphere_by_id(self, sphere_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает сферу по её ID."""
        sphere_data = self.db.spheres.get_sphere_by_id(sphere_id)
        # Нужно преобразовать в dict для совместимости с .get() методом
        return dict(sphere_data) if sphere_data else None
    
    def get_sections(self, sphere_id: int) -> List[Dict[str, Any]]:
        """Возвращает список разделов для указанной сферы."""
        sections_raw = self.db.sections.get_sections(sphere_id)
        # Нужно преобразовать в dict для совместимости с .get() методом
        return [dict(section) for section in sections_raw] if sections_raw else []
    
    def get_section_by_id(self, section_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает раздел по его ID."""
        section_data = self.db.sections.get_section_by_id(section_id)
        # Нужно преобразовать в dict для совместимости с .get() методом
        return dict(section_data) if section_data else None
    
    def get_categories(self, section_id: int) -> List[Dict[str, Any]]:
        """Возвращает список категорий для указанного раздела."""
        categories_raw = self.db.categories.get_categories(section_id)
        # Нужно преобразовать в dict для совместимости с .get() методом
        return [dict(category) for category in categories_raw] if categories_raw else []
    
    def get_category_by_id(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает категорию по её ID."""
        category_data = self.db.categories.get_category_by_id(category_id)
        # Нужно преобразовать в dict для совместимости с .get() методом
        return dict(category_data) if category_data else None
    
    def get_category_hierarchy(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает иерархию категории (sphere_id, section_id)."""
        hierarchy_data = self.db.categories.get_category_hierarchy(category_id)
        if not hierarchy_data:
            return None

        try:
            # Поддерживаем оба формата: dict и последовательность (tuple/list)
            if isinstance(hierarchy_data, dict):
                # Пытаемся прочитать стандартные ключи
                sphere_id = hierarchy_data.get('sphere_id')
                section_id = hierarchy_data.get('section_id')
                # Возможные альтернативные ключи
                if sphere_id is None:
                    sphere_id = hierarchy_data.get('sphereId')
                if section_id is None:
                    section_id = hierarchy_data.get('sectionId')
            else:
                # Считаем, что это последовательность из 2 элементов
                if isinstance(hierarchy_data, (tuple, list)) and len(hierarchy_data) >= 2:
                    sphere_id, section_id = hierarchy_data[0], hierarchy_data[1]
                else:
                    self.logger.warning(
                        f"Некорректный формат иерархии для категории {category_id}: {type(hierarchy_data)}"
                    )
                    return None

            # Базовая проверка типов/значений
            if sphere_id is None or section_id is None:
                self.logger.warning(
                    f"Отсутствуют ключи sphere_id/section_id в иерархии категории {category_id}: {hierarchy_data}"
                )
                return None

            return {
                'sphere_id': sphere_id,
                'section_id': section_id
            }
        except Exception as e:
            self.logger.error(f"Ошибка обработки иерархии категории {category_id}: {e}")
            return None
    
    def upsert_section(self, data: Dict[str, Any]) -> int:
        """Вставляет или обновляет раздел. Возвращает ID записи."""
        return self.db.sections.upsert_section(data)
    
    def upsert_category(self, data: Dict[str, Any]) -> int:
        """Вставляет или обновляет категорию. Возвращает ID записи."""
        return self.db.categories.upsert_category(data)

    # ---------------------------------------------------------------------
    # Обертки для совместимости с бизнес-логикой (ожидаемые методы)
    # ---------------------------------------------------------------------
    def create_section(self, data: Dict[str, Any]) -> Optional[int]:
        """Создает новый раздел (обертка для upsert_section)."""
        try:
            return self.db.sections.upsert_section(data)
        except Exception as e:
            self.logger.error(f"Ошибка создания раздела: {e}")
            return None

    def update_section(self, section_id: int, data: Dict[str, Any]) -> bool:
        """Обновляет раздел по ID (обертка для upsert_section)."""
        try:
            payload = dict(data) if data else {}
            payload['id'] = section_id
            self.db.sections.upsert_section(payload)
            return True
        except Exception as e:
            self.logger.error(f"Ошибка обновления раздела {section_id}: {e}")
            return False

    def update_category(self, category_id: int, data: Dict[str, Any]) -> bool:
        """Обновляет категорию по ID (обертка для upsert_category)."""
        try:
            payload = dict(data) if data else {}
            payload['id'] = category_id
            self.db.categories.upsert_category(payload)
            return True
        except Exception as e:
            self.logger.error(f"Ошибка обновления категории {category_id}: {e}")
            return False

    def get_section_data(self, section_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает данные раздела (алиас get_section_by_id)."""
        return self.get_section_by_id(section_id)

    def get_category_data(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает данные категории (алиас get_category_by_id)."""
        return self.get_category_by_id(category_id)
    
    def delete_section(self, section_id: int) -> bool:
        """Удаляет раздел по его ID."""
        try:
            self.db.sections.delete_section(section_id)
            return True
        except Exception as e:
            self.logger.error(f"Ошибка удаления раздела {section_id}: {e}")
            return False
    
    def delete_category(self, category_id: int) -> bool:
        """Удаляет категорию по её ID."""
        try:
            self.db.categories.delete_category(category_id)
            return True
        except Exception as e:
            self.logger.error(f"Ошибка удаления категории {category_id}: {e}")
            return False
    
    def get_first_category_id(self) -> Optional[int]:
        """Получает ID первой категории в системе."""
        try:
            result = self.db.categories.get_first_category_id()
            return result if result else None
        except Exception as e:
            self.logger.error(f"Ошибка получения первой категории: {e}")
            return None
    
    def get_categories_batch(self, section_ids: List[int]) -> List[Dict[str, Any]]:
        """Получает категории для нескольких разделов одним оптимизированным запросом."""
        if not section_ids:
            return []
        
        try:
            # Используем оптимизированный метод БД вместо N+1 запросов
            categories_raw = self.db.categories.get_categories_for_sections(section_ids)
            # Нужно преобразовать в dict для совместимости с .get() методом
            return [dict(cat) for cat in categories_raw] if categories_raw else []
        except Exception as e:
            self.logger.error(f"Ошибка получения категорий для разделов {section_ids}: {e}")
            return []
    
    def count_nested_objects_for_section(self, section_id: int) -> Tuple[int, int]:
        """Подсчитывает категории и ссылки в разделе."""
        categories_data = self.db.categories.get_categories(section_id)
        cats_count = len(categories_data) if categories_data else 0
        
        links_count = 0
        if categories_data:
            for category_row in categories_data:
                # Оптимизация: прямой доступ к полю без преобразования dict()
                category_id = category_row['id'] if hasattr(category_row, '__getitem__') else category_row.id
                # Оптимизировано: используем эффективный подсчет вместо загрузки всех строк ссылок
                links_count += self.db.links.count_links_by_category(category_id)
        
        return cats_count, links_count
    
    def update_item_positions(self, table_name: str, ids_in_order: List[int]) -> None:
        """Обновляет позиции элементов в указанной таблице."""
        self.db.update_item_positions(table_name, ids_in_order)

    def create_category(self, category_data: Dict[str, Any]) -> Optional[int]:
        """Создает новую категорию."""
        try:
            return self.db.categories.insert_category(category_data)
        except Exception as e:
            self.logger.error(f"Ошибка создания категории: {e}")
            return None

    def create_link(self, link_data: Dict[str, Any]) -> Optional[int]:
        """Создает новую ссылку."""
        try:
            return self.db.links.upsert_link(link_data)
        except Exception as e:
            self.logger.error(f"Ошибка создания ссылки: {e}")
            return None

    def get_links(self, category_id: int) -> List[Dict[str, Any]]:
        """Получает список ссылок для указанной категории."""
        try:
            links_raw = self.db.links.get_links(category_id)
            # Нужно преобразовать в dict для совместимости с .get() методом
            return [dict(link) for link in links_raw] if links_raw else []
        except Exception as e:
            self.logger.error(f"Ошибка получения ссылок для категории {category_id}: {e}")
            return []

    def count_links_by_category(self, category_id: int) -> int:
        """Возвращает количество ссылок для указанной категории (эффективный подсчет)."""
        try:
            return self.db.links.count_links_by_category(category_id)
        except Exception as e:
            self.logger.error(f"Ошибка подсчета ссылок для категории {category_id}: {e}")
            return 0
    
    def has_duplicate_category(self, section_id: int, category_name: str, exclude_id: Optional[int] = None) -> bool:
        """Проверяет наличие дубликата категории в разделе."""
        try:
            return self.db.categories.has_duplicate_category(section_id, category_name, exclude_id)
        except Exception as e:
            self.logger.error(f"Ошибка проверки дубликата категории '{category_name}' в разделе {section_id}: {e}")
            raise
