import os
from pathlib import Path
from typing import Optional

from .path_service import icon_path_service
from .validation import is_valid_icon_file


def get_default_icon_path() -> Path:
    """Return the default icon Path (centralized).

    Uses app_config.get_default_icons()['default'] if present, otherwise 'star.ico',
    and resolves it under UI icons directory.
    """
    try:
        from app.config_data import app_config
        default_name = app_config.get_default_icons().get('default', 'star.ico')
    except Exception:
        default_name = 'star.ico'
    return icon_path_service.get_ui_icons_dir() / default_name


def resolve_icon_path(icon_path: Optional[str]) -> str:
    """Resolve an icon path by checking user, system and default locations.

    Order:
    1) Absolute path: return as-is if exists and valid
    2) Relative user icons dir
    3) Relative UI icons dir (system)
    4) Default icon from config
    Returns string path (may be empty string if nothing found)
    """
    # 1) Absolute path
    if icon_path:
        try:
            p = Path(icon_path)
            if p.is_absolute() and p.exists():
                return str(p)
        except Exception:
            pass

    # 2) Relative in user icons dir
    try:
        if icon_path:
            user_dir = icon_path_service.get_user_icons_dir()
            candidate = (user_dir / icon_path).resolve()
            if candidate.exists() and is_valid_icon_file(str(candidate)):
                return str(candidate)
    except Exception:
        pass

    # 3) Relative in UI icons dir (system)
    try:
        if icon_path:
            ui_dir = icon_path_service.get_ui_icons_dir()
            candidate = (ui_dir / icon_path).resolve()
            if candidate.exists() and is_valid_icon_file(str(candidate)):
                return str(candidate)
    except Exception:
        pass

    # 4) Default
    try:
        candidate = get_default_icon_path()
        if candidate.exists() and is_valid_icon_file(str(candidate)):
            return str(candidate)
    except Exception:
        pass

    return ""


def resolve_link_type_icon(link_type: Optional[str]) -> str:
    """Return icon path for a given logical link type using config defaults.

    Example types: 'file', 'web', 'folder', 'category', ... Fallbacks to 'default'.
    """
    try:
        from app.config_data import app_config
        defaults = app_config.get_default_icons()
        lt = ((link_type or "file").strip() or "file").lower()
        icon_name = defaults.get(lt, defaults.get("default", ""))
        path = resolve_icon_path(icon_name)
        return path or str(get_default_icon_path())
    except Exception:
        return str(get_default_icon_path())


def resolve_icon_for_link(link_data: dict | None) -> str:
    """Return resolved icon path for a link dict.

    Priority:
    - If link_data["icon_path"] is provided -> try resolve_icon_path(icon_path)
      If it falls back to default, prefer default-by-type via resolve_link_type_icon(type)
    - Else -> resolve by link type via resolve_link_type_icon(type)
    - Always returns a valid existing path string (falls back to global default path)
    """
    try:
        icon_name = ""
        link_type = "file"
        if isinstance(link_data, dict):
            icon_name = (link_data.get("icon_path") or "").strip()
            link_type = ((link_data.get("type") or "file").strip() or "file").lower()

        if icon_name:
            path = resolve_icon_path(icon_name)
            # If resolving explicit icon fell back to default, try a default by type
            try:
                default_path = str(get_default_icon_path())
            except Exception:
                default_path = ""
            if path and default_path and os.path.normcase(path) == os.path.normcase(default_path):
                type_path = resolve_link_type_icon(link_type)
                return type_path or path
            return path or str(get_default_icon_path())

        # No explicit icon -> by type
        return resolve_link_type_icon(link_type)
    except Exception:
        return str(get_default_icon_path())


def resolve_category_icon_path(icon_path: Optional[str]) -> str:
    """Resolve category icon path with fallback to configured category/default icon."""
    if icon_path:
        p = Path(icon_path)
        if p.is_absolute():
            return str(p) if (p.exists() and is_valid_icon_file(str(p))) else str(get_default_icon_path())
        # relative name -> try user/ui
        rel = resolve_icon_path(icon_path)
        if rel:
            return rel
    # fallback to category default
    try:
        from app.config_data import app_config
        defaults = app_config.get_default_icons()
        category_name = defaults.get("category", defaults.get("default", ""))
        path = resolve_icon_path(category_name)
        return path or str(get_default_icon_path())
    except Exception:
        return str(get_default_icon_path())


def resolve_folder_icon_path(icon_path: Optional[str]) -> str:
    """Resolve folder icon path with fallback to configured folder/default icon."""
    if icon_path:
        p = Path(icon_path)
        if p.is_absolute():
            return str(p) if (p.exists() and is_valid_icon_file(str(p))) else str(get_default_icon_path())
        rel = resolve_icon_path(icon_path)
        if rel:
            return rel
    # fallback to folder default
    try:
        from app.config_data import app_config
        defaults = app_config.get_default_icons()
        folder_name = defaults.get("folder", defaults.get("default", ""))
        path = resolve_icon_path(folder_name)
        return path or str(get_default_icon_path())
    except Exception:
        return str(get_default_icon_path())
