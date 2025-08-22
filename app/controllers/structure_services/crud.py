from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from app.models.structure_model import StructureModel


class CrudService:
    """Сервис CRUD-операций для разделов и категорий.
    Сервис работает с моделью, без сигналов и кэширования.
    """

    # ----------------------- Разделы -----------------------
    def create_section(self, model: StructureModel, data: Dict[str, Any], logger: logging.Logger) -> Optional[Dict[str, Any]]:
        section_id = model.create_section(data)
        if not section_id:
            return None
        section_data = model.get_section_data(section_id)
        if logger:
            logger.info(f"Создан раздел {section_id}: {data.get('name', 'Без названия')}")
        return section_data

    def update_section(self, model: StructureModel, section_id: int, data: Dict[str, Any], logger: logging.Logger) -> Optional[Dict[str, Any]]:
        success = model.update_section(section_id, data)
        if not success:
            return None
        updated_data = model.get_section_data(section_id)
        if logger and updated_data:
            logger.info(f"Обновлен раздел {section_id}: {data.get('name', 'Без названия')}")
        return updated_data

    def delete_section(self, model: StructureModel, section_id: int, logger: logging.Logger) -> Tuple[bool, Dict[str, Any], int, int]:
        section_data = model.get_section_data(section_id) or {}
        if not section_data:
            return False, {}, 0, 0
        categories = model.get_categories(section_id) or []
        category_count = len(categories)
        # Примечание: доп. проверки на вложенные объекты/ссылки выполняются в фасаде (если нужны)
        success = model.delete_section(section_id)
        if logger and success:
            logger.info(f"Удален раздел {section_id}: {section_data.get('name', 'Без названия')}")
        return success, section_data, category_count, 0

    # ---------------------- Категории ----------------------
    def create_category(self, model: StructureModel, data: Dict[str, Any], logger: logging.Logger) -> Optional[Dict[str, Any]]:
        category_id = model.create_category(data)
        if not category_id:
            return None
        category_data = model.get_category_data(category_id)
        if logger:
            logger.info(f"Создана категория {category_id}: {data.get('name', 'Без названия')}")
        return category_data

    def update_category(self, model: StructureModel, category_id: int, data: Dict[str, Any], logger: logging.Logger) -> Optional[Dict[str, Any]]:
        success = model.update_category(category_id, data)
        if not success:
            return None
        updated_data = model.get_category_data(category_id)
        if logger and updated_data:
            logger.info(f"Обновлена категория {category_id}: {data.get('name', 'Без названия')}")
        return updated_data

    def delete_category(self, model: StructureModel, category_id: int, logger: logging.Logger) -> Tuple[bool, Dict[str, Any], int]:
        category_data = model.get_category_data(category_id) or {}
        if not category_data:
            return False, {}, 0
        success = model.delete_category(category_id)
        if logger and success:
            logger.info(f"Удалена категория {category_id}: {category_data.get('name', 'Без названия')}")
        return success, category_data, 0
