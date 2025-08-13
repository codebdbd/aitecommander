# app/controllers/structure_modules/legacy_support.py

"""Модуль для поддержки устаревших методов и обратной совместимости."""

from typing import Any, Dict, List, Tuple

from .base import StructureItemType, ValidationError
from .validation import validate_item_data


class LegacySupport:
    """Класс для поддержки устаревших методов."""
    
    def __init__(self, sphere_operations, section_operations, category_operations):
        self.sphere_operations = sphere_operations
        self.section_operations = section_operations
        self.category_operations = category_operations
    
    def validate_section_data(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """Устаревший метод валидации данных раздела."""
        try:
            validate_item_data(data, StructureItemType.SECTION)
            return True, ""
        except ValidationError as e:
            return False, str(e)
    
    def validate_category_data(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """Устаревший метод валидации данных категории."""
        try:
            validate_item_data(data, StructureItemType.CATEGORY)
            return True, ""
        except ValidationError as e:
            return False, str(e)
    
    def get_sphere_data(self) -> List[Dict[str, Any]]:
        """Устаревший метод - используйте get_spheres()."""
        return self.sphere_operations.get_spheres()


class StructureBusinessLogicLegacy:
    """Класс для полной обратной совместимости со старыми методами."""
    
    def __init__(self, main_controller):
        self.main_controller = main_controller
        self.legacy_support = LegacySupport(
            main_controller.sphere_operations,
            main_controller.section_operations, 
            main_controller.category_operations
        )
    
    def __getattr__(self, name):
        """Делегирует все неопределенные методы к основному контроллеру."""
        return getattr(self.main_controller, name)
    
    def validate_section_data(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """Устаревший метод валидации данных раздела."""
        return self.legacy_support.validate_section_data(data)
    
    def validate_category_data(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """Устаревший метод валидации данных категории."""
        return self.legacy_support.validate_category_data(data)
    
    def get_sphere_data(self) -> List[Dict[str, Any]]:
        """Устаревший метод - используйте get_spheres()."""
        return self.legacy_support.get_sphere_data()
