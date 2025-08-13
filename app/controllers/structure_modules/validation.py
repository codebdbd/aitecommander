# app/controllers/structure_modules/validation.py

"""Модуль для валидации данных элементов структуры."""

from typing import Any, Dict

from .base import StructureItemType, ValidationError


def validate_item_data(data: Dict[str, Any], item_type: StructureItemType, *, require_parent: bool = True) -> None:
    """Универсальная валидация данных элементов структуры.
    
    Args:
        data: Данные для валидации
        item_type: Тип элемента структуры
        require_parent: Требовать ли parent_id поля (True для создания, False для обновления)
        
    Raises:
        ValidationError: При некорректных данных
    """
    if not isinstance(data, dict):
        raise ValidationError("Данные должны быть словарем")
    
    if not data.get('name', '').strip():
        item_name = "раздела" if item_type == StructureItemType.SECTION else "категории"
        raise ValidationError(f"Имя {item_name} не может быть пустым")
    
    if item_type == StructureItemType.SECTION and require_parent and data.get('sphere_id') is None:
        raise ValidationError("Не указана сфера для раздела")
    if item_type == StructureItemType.CATEGORY and require_parent and data.get('section_id') is None:
        raise ValidationError("Не указан родительский раздел")


def validate_section_data(data: Dict[str, Any]) -> None:
    """Устаревший метод валидации данных раздела."""
    validate_item_data(data, StructureItemType.SECTION)


def validate_category_data(data: Dict[str, Any]) -> None:
    """Устаревший метод валидации данных категории."""
    validate_item_data(data, StructureItemType.CATEGORY)
