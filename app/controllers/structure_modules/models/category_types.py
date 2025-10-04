# app/controllers/structure_modules/category_types.py

"""Типы данных и константы для операций с категориями."""

from dataclasses import dataclass
from typing import Dict

from .types import CategoryData


class SignalTypes:
    """Константы для типов сигналов."""

    ITEM_ADDED = "item_added"
    ITEM_DELETED = "item_deleted"
    ITEM_UPDATED = "item_updated"


@dataclass
class CategoryDeletionInfo:
    """Информация об удалении категории."""

    success: bool
    category_data: CategoryData
    links_count: int

    @classmethod
    def create_empty(cls) -> "CategoryDeletionInfo":
        """Создает пустую информацию об удалении."""
        empty_category: CategoryData = {  # type: ignore
            "id": 0,
            "name": "",
            "section_id": 0,
            "description": None,
            "position": 0,
            "is_active": False,
            "color": None,
            "icon": None,
            "created_at": None,
            "updated_at": None
        }
        return cls(False, empty_category, 0)
