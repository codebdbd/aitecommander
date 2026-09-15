"""Type definitions for LinkModel."""

from typing import Optional, TypedDict


class LinkDict(TypedDict, total=False):
    """Link dictionary structure."""
    id: int
    category_id: int
    name: str
    url: str
    type: str
    notes: str
    is_favorite: int
    last_used: str
    icon_path: str
    args: str
    browser_key: str
    position: int
    chrome_rotation: int
    rotation_index: int
    rotation_profiles: Optional[str]


class LinkInput(TypedDict, total=False):
    """Input for link insert/update operations."""
    id: int
    category_id: int
    name: str
    url: str
    type: str
    notes: str
    is_favorite: int
    last_used: str
    icon_path: str
    args: str
    browser_key: str
    position: int
    chrome_rotation: int
    rotation_index: int
    rotation_profiles: Optional[str]
