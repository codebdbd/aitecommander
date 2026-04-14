"""Type definitions for CategoryModel."""

from typing import TypedDict


class CategoryDict(TypedDict, total=False):
    """Category dictionary structure."""
    id: int
    name: str
    section_id: int
    position: int
    icon_path: str


class BulkInsertResult(TypedDict):
    """Result of bulk insert operation."""
    inserted: list[CategoryDict]
    duplicates_skipped: int
    total_items: int
