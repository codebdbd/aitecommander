# app/controllers/structure_modules/coordination.py

"""Модуль для координации сложных операций между модулями."""

import logging
from typing import Any, Callable, Dict, List, Optional

from app.models.structure_model import StructureModel

from .base import StructureItemType, ValidationError
from .normalization import normalize_row, normalize_rows
from .validation import validate_item_data


class OperationCoordinator:
    """Координатор для сложных операций, требующих взаимодействия нескольких модулей."""
    
    def __init__(self, structure_model: StructureModel, logger: logging.Logger):
        self.structure_model = structure_model
        self.logger = logger
    
    def load_structure_with_categories(self, sphere_id: int, category_operations, 
                                     error_callback: Callable = None) -> List[Dict[str, Any]]:
        """Загружает структуру для сферы с оптимизированной загрузкой категорий."""
        def _load_operation():
            sections_data = self.structure_model.get_sections(sphere_id)
            if not sections_data:
                return []
            
            # Получаем ID всех разделов для батчевой загрузки категорий
            section_ids = [section['id'] for section in sections_data]
            categories_raw = category_operations.get_categories_batch(section_ids)
            
            # Группируем категории по разделам
            categories_by_section = {}
            for cat in categories_raw:
                section_id = cat['section_id']
                if section_id not in categories_by_section:
                    categories_by_section[section_id] = []
                categories_by_section[section_id].append(cat)
            
            # Добавляем категории к разделам
            for section in sections_data:
                section['categories'] = categories_by_section.get(section['id'], [])
            
            self.logger.debug(f"Загружена структура для сферы {sphere_id}: "
                            f"{len(sections_data)} разделов")
            return sections_data
        
        return self.execute_with_error_handling(
            _load_operation,
            f"загрузить структуру для сферы {sphere_id}",
            default_return=[],
            error_callback=error_callback
        )
    
    def execute_with_error_handling(self, operation_func: Callable, operation_name: str, 
                                  default_return: Any = None, normalize_result: bool = False,
                                  error_callback: Callable = None) -> Any:
        """Универсальный метод выполнения операций с централизованной обработкой ошибок."""
        try:
            result = operation_func()
            
            if normalize_result and result is not None:
                if isinstance(result, list):
                    result = normalize_rows(result, self.logger)
                elif isinstance(result, dict):
                    result = normalize_row(result, self.logger)
            
            return result
        except Exception as e:
            error_msg = f"Не удалось {operation_name}: {e}"
            if error_callback:
                error_callback("Ошибка", error_msg, True)
            else:
                self.logger.error(f"Ошибка: {error_msg}", exc_info=True)
            return default_return
    
    def execute_with_validation(self, operation_func: Callable, data: Dict[str, Any], 
                               item_type: StructureItemType, operation_name: str, 
                               require_parent: bool = True, error_callback: Callable = None) -> Any:
        """Универсальный метод выполнения операций с валидацией данных."""
        try:
            validate_item_data(data, item_type, require_parent=require_parent)
            self.logger.debug(f"Валидация прошла успешно для {operation_name}")
            return operation_func()
        except ValidationError as e:
            error_msg = f"Ошибка валидации при {operation_name}: {e}"
            if error_callback:
                error_callback("Ошибка валидации", error_msg, False)
            else:
                self.logger.error(error_msg)
            return None
        except Exception as e:
            error_msg = f"Неожиданная ошибка при {operation_name}: {e}"
            if error_callback:
                error_callback("Ошибка", error_msg, True)
            else:
                self.logger.error(error_msg, exc_info=True)
            return None
