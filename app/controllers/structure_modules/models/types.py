# app/controllers/structure_modules/types.py

"""Strict types for structure_modules - PyQt6 Best Practices.

This module contains TypedDict definitions for all data structures
used in structure operations. Replaces Dict[str, Any] with
concrete typed structures for better type safety.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, TypeAlias, TypedDict, Union

# ===== ENUMS =====


class StructureItemType(Enum):
    """Structure item types."""

    SPHERE = "sphere"
    SECTION = "section"
    CATEGORY = "category"
    LINK = "link"


class SignalType(Enum):
    """Signal types for structure operations."""

    ITEM_ADDED = "item_added"
    ITEM_UPDATED = "item_updated"
    ITEM_DELETED = "item_deleted"
    STRUCTURE_LOADED = "structure_loaded"
    SECTIONS_LOADED = "sections_loaded"
    CATEGORIES_LOADED = "categories_loaded"
    SPHERES_LOADED = "spheres_loaded"
    LINKS_LOADED = "links_loaded"
    SEARCH_RESULTS = "search_results"
    ERROR_OCCURRED = "error_occurred"
    OPERATION_STARTED = "operation_started"
    OPERATION_FINISHED = "operation_finished"
    LOADING_STARTED = "loading_started"
    UPDATE_UI = "update_ui"
    UPDATE_FAVORITES = "update_favorites"
    UPDATE_RECENT_LINKS = "update_recent_links"


# ===== BASE TYPED DICTS =====


class BaseItemData(TypedDict):
    """Base fields for all structure items."""

    id: int
    name: str
    created_at: str | None
    updated_at: str | None


# ===== SPHERE TYPES =====


class SphereData(BaseItemData):
    """Sphere data.

    Sphere is the top level of the structure containing sections.
    Examples: "Work", "Personal", "Education".

    Attributes:
        id: Unique sphere identifier
        name: Sphere name (required)
        description: Sphere description (optional)
        color: Sphere color in hex format (e.g., "#FF5733")
        icon: Sphere icon (optional)
        is_active: Whether the sphere is active (required)
        created_at: Creation time
        updated_at: Last update time
    """

    description: str | None
    color: str | None
    icon: str | None


# ===== SPHERE TYPES =====


class SphereCreateData(TypedDict):
    """Data for creating a sphere."""

    name: str
    description: str | None
    color: str | None
    icon: str | None
    is_active: bool


class SphereUpdateData(TypedDict, total=False):
    """Data for updating a sphere (all fields optional)."""

    name: str
    description: str | None
    color: str | None
    icon: str | None
    is_active: bool


# ===== SECTION TYPES =====


class SectionData(BaseItemData):
    """Section data.

    Section is the middle level of the structure; belongs to a sphere and contains categories.
    Examples: "Projects", "Tasks", "Documents".

    Attributes:
        id: Unique section identifier
        name: Section name (required)
        sphere_id: Sphere ID the section belongs to
        description: Section description (optional)
        position: Section position in list (for sorting)
        is_active: Whether the section is active (required)
        created_at: Creation time
        updated_at: Last update time
    """

    sphere_id: int
    description: str | None
    position: int
    is_active: bool


class SectionCreateData(TypedDict):
    """Data for creating a section."""

    name: str
    sphere_id: int
    description: str | None
    position: int | None
    is_active: bool


class SectionUpdateData(TypedDict, total=False):
    """Data for updating a section (all fields optional)."""

    name: str
    sphere_id: int
    description: str | None
    position: int
    is_active: bool


# ===== CATEGORY TYPES =====


class CategoryData(BaseItemData):
    """Category data.

    Category is the bottom level of the structure; belongs to a section and contains links.
    Examples: "Important", "Ideas", "Resources".

    Attributes:
        id: Unique category identifier
        name: Category name (required)
        section_id: Section ID the category belongs to
        description: Category description (optional)
        position: Category position in list (for sorting)
        is_active: Whether the category is active (required)
        color: Category color in hex format (optional)
        icon: Category icon (optional)
        created_at: Creation time
        updated_at: Last update time
    """

    section_id: int
    description: str | None
    position: int
    is_active: bool
    color: str | None
    icon: str | None


class CategoryCreateData(TypedDict):
    """Data for creating a category."""

    name: str
    section_id: int
    description: str | None
    position: int | None
    is_active: bool
    color: str | None
    icon: str | None


class CategoryUpdateData(TypedDict, total=False):
    """Data for updating a category (all fields optional)."""

    name: str
    section_id: int
    description: str | None
    position: int
    is_active: bool
    color: str | None
    icon: str | None


# ===== GENERIC ITEM TYPES =====


AnyItemData: TypeAlias = Union[SphereData, SectionData, CategoryData]
AnyCreateData: TypeAlias = Union[SphereCreateData, SectionCreateData, CategoryCreateData]
AnyUpdateData: TypeAlias = Union[SphereUpdateData, SectionUpdateData, CategoryUpdateData]
AnyItemPayload: TypeAlias = Union[AnyItemData, BaseItemData, dict[str, Any]]


# ===== LINK TYPES =====


class LinkData(TypedDict):
    """Link data."""

    id: int
    category_id: int
    url: str
    title: str
    description: str | None
    favicon_url: str | None
    is_favorite: bool
    created_at: str | None
    updated_at: str | None
    last_accessed: str | None
    access_count: int


# ===== SEARCH TYPES =====


class SearchResultItem(TypedDict):
    """Search result item."""

    id: int
    type: str  # "sphere", "section", "category", "link"
    title: str
    description: str | None
    url: str | None
    parent_id: int | None
    parent_name: str | None
    relevance_score: float


# ===== OPERATION RESULT TYPES =====


class OperationResult(TypedDict):
    """Operation result."""

    success: bool
    message: str | None
    error: str | None
    data: Any | None


class ValidationResult(TypedDict):
    """Validation result."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]


# ===== COUNT TYPES =====


class NestedObjectsCount(TypedDict):
    """Count of nested objects."""

    categories_count: int
    links_count: int


class SectionNestedCount(NestedObjectsCount):
    """Count of objects in a section."""

    pass


class CategoryNestedCount(TypedDict):
    """Count of objects in a category."""

    links_count: int


# ===== SIGNAL PAYLOAD TYPES =====


class ItemCreatedPayload(TypedDict):
    """Payload for item created signal."""

    item_type: str
    parent_id: int
    item_data: BaseItemData


class ItemUpdatedPayload(TypedDict):
    """Payload for item updated signal."""

    item_type: str
    item_id: int
    item_data: BaseItemData


class ItemDeletedPayload(TypedDict):
    """Payload for item deleted signal."""

    item_type: str
    item_id: int
    old_data: BaseItemData | None


class ErrorPayload(TypedDict):
    """Payload for error signal."""

    title: str
    message: str
    error_code: str | None


# ===== CACHE TYPES =====


class CacheKey(TypedDict):
    """Cache key."""

    key: str
    ttl: int | None


class CacheEntry(TypedDict):
    """Cache entry."""

    key: str
    value: Any
    created_at: float
    expires_at: float | None


# ===== METRICS TYPES =====


class MetricSpan(TypedDict):
    """Metric span."""

    name: str
    start_time: float
    end_time: float | None
    duration: float | None
    tags: dict[str, str] | None


# ===== TASK TYPES =====


class TaskInfo(TypedDict):
    """Task information."""

    task_id: str
    description: str
    status: str  # "pending", "running", "completed", "failed"
    created_at: float
    started_at: float | None
    completed_at: float | None
    progress: float | None
    result: Any | None
    error: str | None


# ===== CONFIGURATION TYPES =====


class ItemTypeConfig:
    """Configuration for a structure item type."""

    def __init__(
        self,
        item_type: StructureItemType,
        parent_field: str,
        ru_name: str,
        upsert_method_name: str,
    ):
        self.item_type = item_type
        self.parent_field = parent_field
        self.ru_name = ru_name
        self.upsert_method_name = upsert_method_name
