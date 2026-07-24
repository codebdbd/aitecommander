from pathlib import Path
from typing import Optional

from .path_service import icon_path_service
from .validation import is_valid_icon_file


def _resolve_filesystem(icon_name: str) -> str:
    """Resolve icon by checking user dir then UI icons dir. Returns path or ''."""
    if not icon_name:
        return ""
    normalized = icon_name.strip()
    if not normalized:
        return ""

    # 1) Absolute path
    try:
        p = Path(normalized)
        if p.is_absolute() and p.exists() and is_valid_icon_file(str(p)):
            return str(p)
    except Exception:
        pass

    # 2) Relative in user icons dir
    try:
        user_dir = icon_path_service.get_user_icons_dir()
        candidate = user_dir / normalized
        if candidate.exists() and is_valid_icon_file(str(candidate)):
            return str(candidate)
    except Exception:
        pass

    # 3) Relative in UI icons dir (system)
    try:
        ui_dir = icon_path_service.get_ui_icons_dir()
        candidate = ui_dir / normalized
        if candidate.exists() and is_valid_icon_file(str(candidate)):
            return str(candidate)
    except Exception:
        pass

    return ""


def resolve_icon_path(icon_path: Optional[str]) -> str:
    """Resolve an icon path by checking user and system locations.

    Order:
    1) Absolute path: return as-is if exists and valid
    2) Relative user icons dir
    3) Relative UI icons dir (system)
    Returns string path (may be empty string if nothing found)
    """
    return _resolve_filesystem(icon_path or "")


def resolve_link_type_icon(link_type: Optional[str]) -> str:
    """Return icon path for a given logical link type using config defaults.

    Example types: 'file', 'web', 'folder', 'category', ...
    """
    try:
        from app.config_data import app_config

        defaults = app_config.get_default_icons()
        lt = ((link_type or "file").strip() or "file").lower()
        icon_name = defaults.get(lt, "")
        if icon_name:
            path = _resolve_filesystem(icon_name)
            if path:
                return path
        return ""
    except Exception:
        return ""


def resolve_icon_for_link(link_data: dict | None) -> str:
    """Return resolved icon path for a link dict.

    Priority:
    - If link_data["icon_path"] is provided -> try resolve_icon_path(icon_path)
    - Else -> resolve by link type via resolve_link_type_icon(type)
    - Returns valid existing path string or empty string
    """
    try:
        icon_name = ""
        link_type = "file"
        if isinstance(link_data, dict):
            icon_name = (link_data.get("icon_path") or "").strip()
            link_type = ((link_data.get("type") or "file").strip() or "file").lower()

        if icon_name:
            path = _resolve_filesystem(icon_name)
            if path:
                return path
            # fallback to type-specific default
            return resolve_link_type_icon(link_type)

        # No explicit icon -> by type
        return resolve_link_type_icon(link_type)
    except Exception:
        return ""


def _type_default_path(type_key: str) -> str:
    """Resolve the configured default icon for a specific type key."""
    try:
        from app.config_data import app_config

        defaults = app_config.get_default_icons()
        name = defaults.get(type_key, "")
        if name:
            return _resolve_filesystem(name)
    except Exception:
        pass
    return ""


def resolve_section_icon_path(icon_path: Optional[str]) -> str:
    """Resolve section icon path with fallback to configured section icon."""
    if icon_path:
        p = Path(icon_path)
        if p.is_absolute():
            if p.exists() and is_valid_icon_file(str(p)):
                return str(p)
        else:
            rel = _resolve_filesystem(icon_path)
            if rel:
                return rel
    return _type_default_path("section")


def resolve_category_icon_path(icon_path: Optional[str]) -> str:
    """Resolve category icon path with fallback to configured category icon."""
    if icon_path:
        p = Path(icon_path)
        if p.is_absolute():
            if p.exists() and is_valid_icon_file(str(p)):
                return str(p)
        else:
            rel = _resolve_filesystem(icon_path)
            if rel:
                return rel
    return _type_default_path("category")


def resolve_folder_icon_path(icon_path: Optional[str]) -> str:
    """Resolve folder icon path with fallback to configured folder icon."""
    if icon_path:
        p = Path(icon_path)
        if p.is_absolute():
            if p.exists() and is_valid_icon_file(str(p)):
                return str(p)
        else:
            rel = _resolve_filesystem(icon_path)
            if rel:
                return rel
    return _type_default_path("folder")


def resolve_link_type_icon_path(icon_path: Optional[str], link_type: str) -> str:
    """Resolve link icon path with fallback to type-specific default."""
    if icon_path:
        p = Path(icon_path)
        if p.is_absolute():
            if p.exists() and is_valid_icon_file(str(p)):
                return str(p)
        else:
            rel = _resolve_filesystem(icon_path)
            if rel:
                return rel
    return _type_default_path(((link_type or "file").strip() or "file").lower())
