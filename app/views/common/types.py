"""Data types for the ``views`` module.

Centralized TypedDict definitions to improve type safety across models, dialogs,
and controllers.
"""

from typing import Any, Literal, TypedDict, NotRequired

# ================================================================================
# BASIC TYPES
# ================================================================================

NodeType = Literal["section", "category", "root"]
LinkType = Literal["web", "file", "folder", "app"]


# ================================================================================
# LINK TYPES
# ================================================================================

class LinkData(TypedDict):
    """Full link data structure.

    Used in models, dialogs, and controllers for type-safe link data passing.
    """
    id: NotRequired[int]
    name: str
    url: str
    type: LinkType
    category_id: NotRequired[int]
    icon_path: NotRequired[str]
    is_favorite: NotRequired[bool]
    notes: NotRequired[str]
    args: NotRequired[str]
    last_used: NotRequired[str | float | None]
    created_at: NotRequired[str]
    updated_at: NotRequired[str]
    # Icon cache (model's internal use)
    _icon: NotRequired[Any]


class MinimalLinkData(TypedDict):
    """Minimal link structure for display purposes."""
    id: int
    name: str
    url: str
    type: LinkType


# ================================================================================
# STRUCTURE TYPES (HIERARCHY)
# ================================================================================

class SphereData(TypedDict):
    """Sphere data."""
    id: int
    name: str
    icon_path: NotRequired[str]
    color: NotRequired[str]


class SectionData(TypedDict):
    """Section data."""
    id: int
    name: str
    sphere_id: int
    icon_path: NotRequired[str]
    categories: NotRequired[list["CategoryData"]]


class CategoryData(TypedDict):
    """Category data."""
    id: int
    name: str
    section_id: int
    icon_path: NotRequired[str]


class HierarchyData(TypedDict):
    """Hierarchical path to a category."""
    sphere_id: NotRequired[int]
    section_id: NotRequired[int]
    category_id: NotRequired[int]


# ================================================================================
# DIALOG TYPES
# ================================================================================

class LinkDialogInitData(TypedDict):
    """Initialization data for LinkDialog."""
    spheres: list[SphereData]
    category_hierarchy: NotRequired[HierarchyData]


class BrowserProfileData(TypedDict):
    """Browser profile data."""
    id: NotRequired[int]
    name: str
    email: NotRequired[str]
    browser_type: str
    profile_path: str


# ================================================================================
# DRAG & DROP TYPES
# ================================================================================

class DragDropPayload(TypedDict):
    """Payload for drag & drop operations."""
    item_type: NodeType
    item_id: int
    source_parent_id: NotRequired[int]


# ================================================================================
# CONFIGURATION TYPES
# ================================================================================

class UIConfig(TypedDict):
    """UI configuration (subset of app_config.ui)."""
    row_height: int
    icon_size: tuple[int, int]
    col_widths: list[int]
    link_dialog_width: int
    link_dialog_height: int
    link_dialog_margins: int
    link_dialog_spacing: int


# ================================================================================
# EXPORTS
# ================================================================================

__all__ = [
    # Basic types
    "NodeType",
    "LinkType",
    # Link types
    "LinkData",
    "MinimalLinkData",
    # Structure types
    "SphereData",
    "SectionData",
    "CategoryData",
    "HierarchyData",
    # Dialog types
    "LinkDialogInitData",
    "BrowserProfileData",
    # Drag & Drop
    "DragDropPayload",
    # Configuration
    "UIConfig",
]
