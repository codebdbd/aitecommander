# app/controllers/structure_modules/category_types.py

"""Data types and constants for category operations."""

from dataclasses import dataclass
from .types import CategoryData


class SignalTypes:
    """Constants for signal types."""

    ITEM_ADDED = "item_added"
    ITEM_DELETED = "item_deleted"
    ITEM_UPDATED = "item_updated"


@dataclass
class CategoryDeletionInfo:
    """Information about category deletion."""

    success: bool
    category_data: CategoryData
    links_count: int

    @classmethod
    def create_empty(cls) -> "CategoryDeletionInfo":
        """Create empty deletion info."""
        empty_category: CategoryData = {
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
