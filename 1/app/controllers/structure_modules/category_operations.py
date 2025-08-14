# app/controllers/structure_modules/category_operations.py

"""Модуль для операций с категориями."""

import logging
from typing import Any, Dict, Callable, List, Optional, Tuple

from app.models.structure_model import StructureModel

from .base import StructureItemType, BaseOperations


class CategoryOperations(BaseOperations):
    """Класс для операций с категориями."""
    
    def __init__(self, structure_model: StructureModel, logger: logging.Logger,
                 execute_with_error_handling: Callable, execute_with_validation: Callable,
                 emit_signal_callback: Callable, cache_manager):
        super().__init__(structure_model, logger, execute_with_error_handling)
        self._execute_with_validation = execute_with_validation
        self._emit_signal = emit_signal_callback
        self._cache_manager = cache_manager
    
    def create_category(self, data: Dict[str, Any]) -> bool:
        """Создает новую категорию."""
        result = self._process_item(data, StructureItemType.CATEGORY)
        if result:
            self._cache_manager.invalidate_first_category_cache()
        return result
    
    def update_category(self, category_id: int, data: Dict[str, Any]) -> bool:
        """Обновляет существующую категорию."""
        result = self._process_item(data, StructureItemType.CATEGORY, category_id, is_update=True)
        if result:
            self._cache_manager.invalidate_first_category_cache()
        return result
    
    def delete_category(self, category_id: int) -> Tuple[bool, Dict[str, Any], int]:
        """Удаляет категорию. Возвращает (успех, данные_категории, количество_ссылок)."""
        def _delete_category_operation():
            category_data = self.structure_model.get_category_by_id(category_id)
            if not category_data:
                error_msg = f"Категория с ID {category_id} не найдена"
                self.logger.error(error_msg)
                return False, {}, 0
            
            # Модель уже возвращает нормализованные данные
            category_dict = category_data
            
            # Оптимизировано: используем эффективный подсчет вместо загрузки всех строк ссылок
            links_count = self.structure_model.count_links_by_category(category_id)
            
            self.logger.info(f"Подготовка к удалению категории {category_id}: "
                           f"{links_count} ссылок")
            
            return True, category_dict, links_count
        
        result = self._execute_with_error_handling(
            _delete_category_operation,
            f"получить данные категории {category_id}",
            default_return=(False, {}, 0)
        )
        return result
    
    def confirm_delete_category(self, category_id: int) -> bool:
        """Подтверждает и выполняет удаление категории."""
        def _confirm_delete_category_operation():
            self.structure_model.delete_category(category_id)
            self._emit_signal("item_deleted", StructureItemType.CATEGORY.value, category_id)
            self.logger.info(f"Удалена категория {category_id}")
            self._cache_manager.invalidate_first_category_cache()
            return True
        
        result = self._execute_with_error_handling(
            _confirm_delete_category_operation,
            f"удалить категорию {category_id}",
            default_return=False
        )
        return result
    
    def get_category_data(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные категории с гарантированной нормализацией."""
        def _get_category_operation():
            category_data = self.structure_model.get_category_by_id(category_id)
            if category_data:
                self.logger.debug(f"Найдена категория {category_id}")
                return category_data
            else:
                self.logger.warning(f"Категория {category_id} не найдена")
                return None
        
        return self._exec_with_norm(
            _get_category_operation,
            f"загрузить данные категории {category_id}",
            default_return=None
        )
    
    def get_categories(self, section_id: int) -> List[Dict[str, Any]]:
        """Получает список категорий для указанного раздела."""
        def _get_categories_operation():
            categories_data = self.structure_model.get_categories(section_id)
            result = categories_data if categories_data else []
            self.logger.debug(f"Загружено {len(result)} категорий для раздела {section_id}")
            return result
        
        return self._exec_with_norm(
            _get_categories_operation,
            f"загрузить категории для раздела {section_id}",
            default_return=[]
        )
    
    def get_categories_batch(self, section_ids: List[int]) -> List[Dict[str, Any]]:
        """Получает категории для нескольких разделов с гарантированной нормализацией."""
        if not section_ids:
            return []
        
        # Используем оптимизированный метод модели с нормализацией
        rows = self.structure_model.get_categories_batch(section_ids)
        from .normalization import normalize_rows
        return normalize_rows(rows, self.logger)
    
    def get_first_category_id(self) -> Optional[int]:
        """Получает ID первой категории с кэшированием для оптимизации."""
        cached_id = self._cache_manager.get_first_category_id()
        if cached_id is not None:
            self.logger.debug(f"Используется кэшированная первая категория: {cached_id}")
            return cached_id
        
        def _get_first_category_operation():
            category_id = self.structure_model.get_first_category_id()
            if category_id:
                self.logger.debug(f"Найдена первая категория с ID: {category_id}")
                self._cache_manager.set_first_category_id(category_id)
                return category_id
            else:
                self.logger.debug("Категории не найдены")
                return None
        
        return self._execute_with_error_handling(
            _get_first_category_operation,
            "получить первую категорию",
            default_return=None
        )
    
    def get_category_hierarchy(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Получает иерархию (sphere_id, section_id) для категории с гарантированной нормализацией."""
        def _get_hierarchy_operation():
            hierarchy_data = self.structure_model.get_category_hierarchy(category_id)
            if hierarchy_data:
                self.logger.debug(f"Найдена иерархия для категории {category_id}")
                return hierarchy_data
            else:
                self.logger.warning(f"Иерархия для категории {category_id} не найдена")
                return None
        
        return self._exec_with_norm(
            _get_hierarchy_operation,
            f"получить иерархию категории {category_id}",
            default_return=None
        )
    
    def has_duplicate_category(self, section_id: int, category_name: str, exclude_id: Optional[int] = None) -> bool:
        """Проверяет наличие дубликата категории в разделе."""
        def _check_duplicate_operation():
            return self.structure_model.has_duplicate_category(section_id, category_name, exclude_id)
        
        result = self._execute_with_error_handling(
            _check_duplicate_operation,
            f"проверить дубликат категории '{category_name}' в разделе {section_id}",
            default_return=False
        )
        return result if result is not None else False
    
    def create_category_for_import(self, category_data: Dict[str, Any]) -> Optional[int]:
        """Создает новую категорию для импорта (отдельный метод для избежания конфликтов)."""
        return self._create_item_for_import("category", category_data, self.structure_model.create_category)
    
    
    
    def _create_item_for_import(self, item_type: str, item_data: Dict[str, Any], 
                               create_func: Callable) -> Optional[int]:
        """Универсальный метод создания элементов для импорта."""
        
        def _create_import_operation():
            result_id = create_func(item_data)
            if result_id:
                # Подготавливаем данные для сигнала
                item_data['id'] = result_id
                
                # Определяем parent_id в зависимости от типа элемента
                from .base import ItemTypes
                if item_type == ItemTypes.SECTION:
                    parent_id = item_data.get('sphere_id')
                elif item_type == ItemTypes.CATEGORY:
                    parent_id = item_data.get('section_id')
                elif item_type == ItemTypes.LINK:
                    parent_id = item_data.get('category_id')
                else:
                    raise ValueError(f"Неподдерживаемый тип элемента: {item_type}")
                
                # Эмитируем сигнал о добавлении
                self._emit_signal("item_added", item_type, parent_id, item_data)
                
                self.logger.info(f"Создан {item_type} для импорта: {item_data.get('name', 'без имени')}")
                return result_id
            else:
                self.logger.warning(f"Не удалось создать {item_type} для импорта")
                return None
        
        return self._execute_with_error_handling(
            _create_import_operation,
            f"создать {item_type} для импорта",
            default_return=None
        )
