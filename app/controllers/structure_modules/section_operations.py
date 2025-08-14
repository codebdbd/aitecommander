# app/controllers/structure_modules/section_operations.py

"""Модуль для операций с разделами."""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass

from app.models.structure_model import StructureModel

from .base import StructureItemType, BaseOperations


@dataclass
class DeletionInfo:
    """Информация об удалении раздела."""
    success: bool
    section_data: Dict[str, Any]
    categories_count: int
    links_count: int
    
    @classmethod
    def create_empty(cls) -> 'DeletionInfo':
        """Создает пустую информацию об удалении."""
        return cls(False, {}, 0, 0)


class SectionOperations(BaseOperations):
    """Класс для операций с разделами."""
    
    def __init__(self, structure_model: StructureModel, logger: logging.Logger,
                 execute_with_error_handling: Callable, execute_with_validation: Callable,
                 emit_signal_callback: Callable):
        """
        Инициализация операций с разделами.
        
        Args:
            structure_model: Модель для работы со структурой данных
            logger: Логгер для записи событий
            execute_with_error_handling: Функция обработки ошибок
            execute_with_validation: Функция валидации
            emit_signal_callback: Функция эмиссии сигналов
        """
        super().__init__(structure_model, logger, execute_with_error_handling)
        self._execute_with_validation = execute_with_validation
        self._emit_signal = emit_signal_callback
    
    def create_section(self, data: Dict[str, Any]) -> bool:
        """
        Создает новый раздел.
        
        Args:
            data: Данные для создания раздела
            
        Returns:
            bool: True если раздел создан успешно, False иначе
        """
        self._log_operation_start("создание раздела")
        return self._process_item(data, StructureItemType.SECTION)
    
    def update_section(self, section_id: int, data: Dict[str, Any]) -> bool:
        """
        Обновляет существующий раздел.
        
        Args:
            section_id: ID раздела для обновления
            data: Новые данные раздела
            
        Returns:
            bool: True если раздел обновлен успешно, False иначе
        """
        self._log_operation_start(f"обновление раздела {section_id}")
        return self._process_item(data, StructureItemType.SECTION, section_id, is_update=True)
    
    def delete_section(self, section_id: int) -> Tuple[bool, Dict[str, Any], int, int]:
        """
        Удаляет раздел. Возвращает информацию об удалении.
        
        Args:
            section_id: ID раздела для удаления
            
        Returns:
            Tuple[bool, Dict[str, Any], int, int]: 
            (успех, данные_раздела, количество_категорий, количество_ссылок)
        """
        self._log_operation_start(f"подготовка удаления раздела {section_id}")
        
        deletion_info = self._prepare_section_deletion(section_id)
        return (
            deletion_info.success,
            deletion_info.section_data,
            deletion_info.categories_count,
            deletion_info.links_count
        )
    
    def confirm_delete_section(self, section_id: int) -> bool:
        """
        Подтверждает и выполняет удаление раздела.
        
        Args:
            section_id: ID раздела для удаления
            
        Returns:
            bool: True если раздел удален успешно, False иначе
        """
        self._log_operation_start(f"подтверждение удаления раздела {section_id}")
        return self._execute_section_deletion(section_id)
    
    def get_section_data(self, section_id: int) -> Optional[Dict[str, Any]]:
        """
        Получает данные раздела с гарантированной нормализацией.
        
        Args:
            section_id: ID раздела
            
        Returns:
            Optional[Dict[str, Any]]: Данные раздела или None если не найден
        """
        self._log_operation_start(f"получение данных раздела {section_id}")
        return self._fetch_section_data(section_id)
    
    def get_sections(self, sphere_id: int) -> List[Dict[str, Any]]:
        """
        Получает список разделов для указанной сферы.
        
        Args:
            sphere_id: ID сферы
            
        Returns:
            List[Dict[str, Any]]: Список разделов
        """
        self._log_operation_start(f"получение разделов для сферы {sphere_id}")
        return self._fetch_sections_for_sphere(sphere_id)
    
    # Приватные методы для улучшения читаемости и тестируемости
    
    def _prepare_section_deletion(self, section_id: int) -> DeletionInfo:
        """Подготавливает данные для удаления раздела."""
        def _deletion_preparation():
            section_data = self.structure_model.get_section_by_id(section_id)
            if not section_data:
                self._log_section_not_found(section_id)
                return DeletionInfo.create_empty()
            
            # Получаем нормализованные данные раздела
            normalized_section_data = section_data
            
            # Подсчитываем вложенные объекты
            categories_count, links_count = self._count_nested_objects(section_id)
            
            self._log_deletion_preparation(section_id, categories_count, links_count)
            
            return DeletionInfo(
                success=True,
                section_data=normalized_section_data,
                categories_count=categories_count,
                links_count=links_count
            )
        
        return self._execute_with_error_handling(
            _deletion_preparation, 
            f"получить данные раздела {section_id}",
            default_return=DeletionInfo.create_empty()
        )
    
    def _execute_section_deletion(self, section_id: int) -> bool:
        """Выполняет фактическое удаление раздела."""
        def _deletion_execution():
            self.structure_model.delete_section(section_id)
            self._emit_section_deleted_signal(section_id)
            self._log_successful_deletion(section_id)
            return True
        
        return self._execute_with_error_handling(
            _deletion_execution,
            f"удалить раздел {section_id}",
            default_return=False
        )
    
    def _fetch_section_data(self, section_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные раздела."""
        def _fetch_operation():
            section_data = self.structure_model.get_section_by_id(section_id)
            if section_data:
                self._log_section_found(section_id)
                return section_data
            else:
                self._log_section_not_found(section_id)
                return None
        
        return self._exec_with_norm(
            _fetch_operation,
            f"загрузить данные раздела {section_id}",
            default_return=None
        )
    
    def _fetch_sections_for_sphere(self, sphere_id: int) -> List[Dict[str, Any]]:
        """Получает разделы для сферы."""
        def _fetch_operation():
            sections_data = self.structure_model.get_sections(sphere_id)
            result = sections_data if sections_data else []
            self._log_sections_loaded(len(result), sphere_id)
            return result
        
        return self._exec_with_norm(
            _fetch_operation,
            f"загрузить разделы для сферы {sphere_id}",
            default_return=[]
        )
    
    def _count_nested_objects(self, section_id: int) -> Tuple[int, int]:
        """
        Подсчитывает категории и ссылки в разделе.
        
        Args:
            section_id: ID раздела
            
        Returns:
            Tuple[int, int]: Количество категорий и ссылок
        """
        return self.structure_model.count_nested_objects_for_section(section_id)
    
    def _count_nested_objects_for_section(self, section_id: int) -> Tuple[int, int]:
        """
        Подсчитывает категории и ссылки в разделе через единый интерфейс модели.
        
        Этот метод сохранен для полной совместимости с оригинальным кодом.
        
        Args:
            section_id: ID раздела
            
        Returns:
            Tuple[int, int]: Количество категорий и ссылок
        """
        return self.structure_model.count_nested_objects_for_section(section_id)
    
    def _emit_section_deleted_signal(self, section_id: int) -> None:
        """Отправляет сигнал об удалении раздела."""
        self._emit_signal("item_deleted", StructureItemType.SECTION.value, section_id)
    
    # Методы логирования для централизации и улучшения читаемости
    
    def _log_operation_start(self, operation_name: str) -> None:
        """Логирует начало операции."""
        self.logger.debug(f"Начало операции: {operation_name}")
    
    def _log_section_found(self, section_id: int) -> None:
        """Логирует успешное нахождение раздела."""
        self.logger.debug(f"Найден раздел {section_id}")
    
    def _log_section_not_found(self, section_id: int) -> None:
        """Логирует ненахождение раздела."""
        error_msg = f"Раздел с ID {section_id} не найден"
        self.logger.error(error_msg)
    
    def _log_deletion_preparation(self, section_id: int, cats_count: int, links_count: int) -> None:
        """Логирует подготовку к удалению раздела."""
        self.logger.info(
            f"Подготовка к удалению раздела {section_id}: "
            f"{cats_count} категорий, {links_count} ссылок"
        )
    
    def _log_successful_deletion(self, section_id: int) -> None:
        """Логирует успешное удаление раздела."""
        self.logger.info(f"Удален раздел {section_id}")
    
    def _log_sections_loaded(self, count: int, sphere_id: int) -> None:
        """Логирует загрузку разделов."""
        self.logger.debug(f"Загружено {count} разделов для сферы {sphere_id}")