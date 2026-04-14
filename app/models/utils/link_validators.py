"""Link validation utilities.

Centralizes link validation logic to eliminate duplication between
link_model.py and import_export_manager.py.
"""

from __future__ import annotations

from typing import Any

from ..base.db_base import ValidationError
from ..types.constants import (
    DEFAULT_ICON_PATH,
    MAX_NAME_LENGTH,
    MAX_NOTES_LENGTH,
    MAX_URL_LENGTH,
)
from ..types.link_type import LinkType


def validate_link_data(link_data: dict[str, Any]) -> None:
    """Validate link data fields (name, url, notes lengths).
    
    Args:
        link_data: Dictionary containing link fields
        
    Raises:
        ValidationError: If any field exceeds maximum length
        
    Example:
        >>> validate_link_data({"name": "Test", "url": "http://example.com"})
        >>> validate_link_data({"name": "A" * 300})  # raises ValidationError
    """
    if "name" in link_data and link_data["name"]:
        name_str = str(link_data["name"])
        if len(name_str) > MAX_NAME_LENGTH:
            raise ValidationError(
                f"Link name too long: {len(name_str)} chars (max {MAX_NAME_LENGTH})"
            )
    
    if "url" in link_data and link_data["url"]:
        url_str = str(link_data["url"])
        if len(url_str) > MAX_URL_LENGTH:
            raise ValidationError(
                f"Link URL too long: {len(url_str)} chars (max {MAX_URL_LENGTH})"
            )
    
    if "notes" in link_data and link_data["notes"]:
        notes_str = str(link_data["notes"])
        if len(notes_str) > MAX_NOTES_LENGTH:
            raise ValidationError(
                f"Link notes too long: {len(notes_str)} chars (max {MAX_NOTES_LENGTH})"
            )


def normalize_link_fields(link_data: dict[str, Any], all_fields: list[str]) -> dict[str, Any]:
    """Normalize link fields with defaults and type conversions.
    
    Args:
        link_data: Raw link data dictionary
        all_fields: List of all expected field names
        
    Returns:
        Normalized dictionary with all fields set and correct types
        
    Example:
        >>> fields = ["id", "name", "url", "type", "is_favorite"]
        >>> normalize_link_fields({"name": "Test"}, fields)
        {"id": None, "name": "Test", "url": "", "type": "web", "is_favorite": 0}
    """
    data = {field: link_data.get(field) for field in all_fields}
    
    # Set string defaults
    data["name"] = data.get("name", "") or ""
    data["url"] = data.get("url", "") or ""
    data["args"] = data.get("args", "") or ""
    data["notes"] = data.get("notes", "") or ""
    data["icon_path"] = data.get("icon_path", DEFAULT_ICON_PATH) or DEFAULT_ICON_PATH
    
    # Normalize type using LinkType enum
    try:
        data["type"] = LinkType.from_value(data.get("type", "web")).value
    except Exception:
        data["type"] = LinkType.WEB.value
    
    # Normalize boolean/integer fields
    data["is_favorite"] = int(data.get("is_favorite", 0) or 0)
    
    return data


__all__ = ["validate_link_data", "normalize_link_fields"]
