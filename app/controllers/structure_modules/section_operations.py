# app/controllers/structure_modules/section_operations.py

"""Модуль для операций с разделами."""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.models.structure_model import StructureModel

from .base import StructureItemType, BaseOperations

class SectionOperations(BaseOperations):
    """Класс для операций с разделами."""
    
    def __init__(self, structure_model: StructureModel, logger: logging.Logger,
                 execute_with_error_handling: Callable, execute_with_validation: Callable,
                 emit_signal_callback: Callable):
        super().__init__(structure_model, logger, execute_with_error_handling)
        self._execute_with_validation = execute_with_validation
        self._emit_signal = emit_signal_callback
    
    def create_section(self, data: Dict[str, Any]) -> bool:
        """Создает новый раздел."""
        return self._process_item(data, StructureItemType.SECTION)
    
    def update_section(self, section_id: int, data: Dict[str, Any]) -> bool:
        """Обновляет существующий раздел."""
        return self._process_item(data, StructureItemType.SECTION, section_id, is_update=True)
    
    def delete_section(self, section_id: int) -> Tuple[bool, Dict[str, Any], int, int]:
        """Удаляет раздел. Возвращает (успех, данные_раздела, количество_категорий, количество_ссылок)."""
        def _delete_operation():
            section_data = self.structure_model.get_section_by_id(section_id)
            if not section_data:
                error_msg = f"Раздел с ID {section_id} не найден"
                self.logger.error(error_msg)
                return False, {}, 0, 0
            
            # Модель уже возвращает нормализованные данные
            section_dict = section_data
            
            # Оптимизированный подсчет вложенных объектов
            cats_count, links_count = self._count_nested_objects_for_section(section_id)
            
            self.logger.info(f"Подготовка к удалению раздела {section_id}: "
                           f"{cats_count} категорий, {links_count} ссылок")
            
            return True, section_dict, cats_count, links_count
        
        result = self._execute_with_error_handling(
            _delete_operation, 
            f"получить данные раздела {section_id}",
            default_return=(False, {}, 0, 0)
        )
        return result
    
    def confirm_delete_section(self, section_id: int) -> bool:
        """Подтверждает и выполняет удаление раздела."""
        def _confirm_delete_operation():
            self.structure_model.delete_section(section_id)
            self._emit_signal("item_deleted", StructureItemType.SECTION.value, section_id)
            self.logger.info(f"Удален раздел {section_id}")
            return True
        
        result = self._execute_with_error_handling(
            _confirm_delete_operation,
            f"удалить раздел {section_id}",
            default_return=False
        )
        return result
    
    def get_section_data(self, section_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные раздела с гарантированной нормализацией."""
        def _get_section_operation():
            section_data = self.structure_model.get_section_by_id(section_id)
            if section_data:
                self.logger.debug(f"Найден раздел {section_id}")
                return section_data
            else:
                self.logger.warning(f"Раздел {section_id} не найден")
                return None
        
        return self._exec_with_norm(
            _get_section_operation,
            f"загрузить данные раздела {section_id}",
            default_return=None
        )
    
    def get_sections(self, sphere_id: int) -> List[Dict[str, Any]]:
        """Получает список разделов для указанной сферы."""
        def _get_sections_operation():
            sections_data = self.structure_model.get_sections(sphere_id)
            result = sections_data if sections_data else []
            self.logger.debug(f"Загружено {len(result)} разделов для сферы {sphere_id}")
            return result
        
        return self._exec_with_norm(
            _get_sections_operation,
            f"загрузить разделы для сферы {sphere_id}",
            default_return=[]
        )
    
    
    
    def _count_nested_objects_for_section(self, section_id: int) -> Tuple[int, int]:
        """Подсчитывает категории и ссылки в разделе через единый интерфейс модели."""
        return self.structure_model.count_nested_objects_for_section(section_id)
