# app/controllers/structure_modules/types.py

"""Strict types for structure_modules - PyQt6 Best Practices.

This module contains TypedDict definitions for all data structures
used in structure operations. Replaces Dict[str, Any] with
concrete typed structures for better type safety.
"""

from enum import Enum
from typing import Any, Optional, TypedDict

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
    created_at: Optional[str]
    updated_at: Optional[str]


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
    description: Optional[str]
    color: Optional[str]
    icon: Optional[str]
    is_active: bool


class SphereCreateData(TypedDict):
    """Data for creating a sphere."""
    name: str
    description: Optional[str]
    color: Optional[str]
    icon: Optional[str]
    is_active: bool


class SphereUpdateData(TypedDict, total=False):
    """Data for updating a sphere (all fields optional)."""
    name: str
    description: Optional[str]
    color: Optional[str]
    icon: Optional[str]
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
    description: Optional[str]
    position: int
    is_active: bool


class SectionCreateData(TypedDict):
    """Data for creating a section."""
    name: str
    sphere_id: int
    description: Optional[str]
    position: Optional[int]
    is_active: bool


class SectionUpdateData(TypedDict, total=False):
    """Data for updating a section (all fields optional)."""
    name: str
    sphere_id: int
    description: Optional[str]
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
    description: Optional[str]
    position: int
    is_active: bool
    color: Optional[str]
    icon: Optional[str]


class CategoryCreateData(TypedDict):
    """Data for creating a category."""
    name: str
    section_id: int
    description: Optional[str]
    position: Optional[int]
    is_active: bool
    color: Optional[str]
    icon: Optional[str]


class CategoryUpdateData(TypedDict, total=False):
    """Data for updating a category (all fields optional)."""
    name: str
    section_id: int
    description: Optional[str]
    position: int
    is_active: bool
    color: Optional[str]
    icon: Optional[str]


# ===== LINK TYPES =====

class LinkData(TypedDict):
    """Link data."""
    id: int
    category_id: int
    url: str
    title: str
    description: Optional[str]
    favicon_url: Optional[str]
    is_favorite: bool
    created_at: Optional[str]
    updated_at: Optional[str]
    last_accessed: Optional[str]
    access_count: int


# ===== SEARCH TYPES =====

class SearchResultItem(TypedDict):
    """Search result item."""
    id: int
    type: str  # "sphere", "section", "category", "link"
    title: str
    description: Optional[str]
    url: Optional[str]
    parent_id: Optional[int]
    parent_name: Optional[str]
    relevance_score: float


# ===== OPERATION RESULT TYPES =====

class OperationResult(TypedDict):
    """Operation result."""
    success: bool
    message: Optional[str]
    error: Optional[str]
    data: Optional[Any]


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
    old_data: Optional[BaseItemData]


class ErrorPayload(TypedDict):
    """Payload for error signal."""
    title: str
    message: str
    error_code: Optional[str]


# ===== CACHE TYPES =====

class CacheKey(TypedDict):
    """Cache key."""
    key: str
    ttl: Optional[int]


class CacheEntry(TypedDict):
    """Cache entry."""
    key: str
    value: Any
    created_at: float
    expires_at: Optional[float]


# ===== METRICS TYPES =====

class MetricSpan(TypedDict):
    """Metric span."""
    name: str
    start_time: float
    end_time: Optional[float]
    duration: Optional[float]
    tags: Optional[dict[str, str]]


# ===== TASK TYPES =====

class TaskInfo(TypedDict):
    """Task information."""
    task_id: str
    description: str
    status: str  # "pending", "running", "completed", "failed"
    created_at: float
    started_at: Optional[float]
    completed_at: Optional[float]
    progress: Optional[float]
    result: Optional[Any]
    error: Optional[str]


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


# ===== UNION TYPES =====

# Union of all item data types
AnyItemData = SphereData | SectionData | CategoryData
AnyCreateData = SphereCreateData | SectionCreateData | CategoryCreateData  
AnyUpdateData = SphereUpdateData | SectionUpdateData | CategoryUpdateData

# Union of all payload types
AnySignalPayload = (
    ItemCreatedPayload | 
    ItemUpdatedPayload | 
    ItemDeletedPayload | 
    ErrorPayload
)
