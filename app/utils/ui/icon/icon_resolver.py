from pathlib import Path
from typing import Optional

from .negative_cache import mark_negative, negative_cache
from .path_service import icon_path_service
from .validation import is_valid_icon_file


def get_default_icon_path() -> Path:
    """Return the default icon Path (centralized).

    Uses app_config.get_default_icons()['default'] if present, otherwise 'star.ico',
    and resolves it under UI icons directory.
    """
    try:
        from app.config_data import app_config

        default_name = app_config.get_default_icons().get("default", "star.ico")
    except Exception:
        default_name = "star.ico"
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
    normalized = (icon_path or "").strip()
    negative_key = normalized.casefold() if normalized else ""
    if negative_key and negative_cache.is_negative(negative_key):
        try:
            candidate = get_default_icon_path()
            if candidate.exists() and is_valid_icon_file(str(candidate)):
                return str(candidate)
        except Exception:
            pass
        return ""

    # 1) Absolute path
    if normalized:
        try:
            p = Path(normalized)
            if p.is_absolute() and p.exists():
                if negative_key:
                    negative_cache.invalidate(negative_key)
                return str(p)
        except Exception:
            pass

    # 2) Relative in user icons dir
    try:
        if normalized:
            user_dir = icon_path_service.get_user_icons_dir()
            candidate = user_dir / normalized
            if candidate.exists() and is_valid_icon_file(str(candidate)):
                if negative_key:
                    negative_cache.invalidate(negative_key)
                return str(candidate)
    except Exception:
        pass

    # 3) Relative in UI icons dir (system)
    try:
        if normalized:
            ui_dir = icon_path_service.get_ui_icons_dir()
            candidate = ui_dir / normalized
            if candidate.exists() and is_valid_icon_file(str(candidate)):
                if negative_key:
                    negative_cache.invalidate(negative_key)
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

    if negative_key:
        mark_negative(negative_key)

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
        if path and Path(path).exists() and is_valid_icon_file(path):
            return path
        # fallback to configured default path if valid
        try:
            default_path = str(get_default_icon_path())
        except Exception:
            default_path = ""
        if (
            default_path
            and Path(default_path).exists()
            and is_valid_icon_file(default_path)
        ):
            return default_path
        return ""
    except Exception:
        try:
            default_path = str(get_default_icon_path())
        except Exception:
            default_path = ""
        return (
            default_path
            if (
                default_path
                and Path(default_path).exists()
                and is_valid_icon_file(default_path)
            )
            else ""
        )


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
            if (
                path
                and default_path
                and str(Path(path).resolve()).lower()
                == str(Path(default_path).resolve()).lower()
            ):
                type_path = resolve_link_type_icon(link_type)
                if (
                    type_path
                    and Path(type_path).exists()
                    and is_valid_icon_file(type_path)
                ):
                    return type_path
            # prefer explicit path if valid
            if path and Path(path).exists() and is_valid_icon_file(path):
                return path
            # fallback to default if valid
            if (
                default_path
                and Path(default_path).exists()
                and is_valid_icon_file(default_path)
            ):
                return default_path
            return ""

        # No explicit icon -> by type
        path_by_type = resolve_link_type_icon(link_type)
        if (
            path_by_type
            and Path(path_by_type).exists()
            and is_valid_icon_file(path_by_type)
        ):
            return path_by_type
        try:
            default_path = str(get_default_icon_path())
        except Exception:
            default_path = ""
        return (
            default_path
            if (
                default_path
                and Path(default_path).exists()
                and is_valid_icon_file(default_path)
            )
            else ""
        )
    except Exception:
        return str(get_default_icon_path())


def _is_default_fallback(path: str) -> bool:
    """Check if resolved path is the global default icon (not a type-specific one)."""
    try:
        default = str(get_default_icon_path())
        return Path(path).resolve() == Path(default).resolve()
    except Exception:
        return False


def resolve_section_icon_path(icon_path: Optional[str]) -> str:
    """Resolve section icon path with fallback to configured section/default icon."""
    if icon_path:
        p = Path(icon_path)
        if p.is_absolute():
            if p.exists() and is_valid_icon_file(str(p)):
                return str(p)
        else:
            rel = resolve_icon_path(icon_path)
            if rel and not _is_default_fallback(rel):
                return rel
    # fallback to section default
    try:
        from app.config_data import app_config

        defaults = app_config.get_default_icons()
        section_name = defaults.get("section", defaults.get("default", ""))
        path = resolve_icon_path(section_name)
        if path and not _is_default_fallback(path):
            return path
        return path or str(get_default_icon_path())
    except Exception:
        return str(get_default_icon_path())


def resolve_category_icon_path(icon_path: Optional[str]) -> str:
    """Resolve category icon path with fallback to configured category/default icon."""
    if icon_path:
        p = Path(icon_path)
        if p.is_absolute():
            if p.exists() and is_valid_icon_file(str(p)):
                return str(p)
        else:
            rel = resolve_icon_path(icon_path)
            if rel and not _is_default_fallback(rel):
                return rel
    # fallback to category default
    try:
        from app.config_data import app_config

        defaults = app_config.get_default_icons()
        category_name = defaults.get("category", defaults.get("default", ""))
        path = resolve_icon_path(category_name)
        if path and not _is_default_fallback(path):
            return path
        return path or str(get_default_icon_path())
    except Exception:
        return str(get_default_icon_path())


def resolve_folder_icon_path(icon_path: Optional[str]) -> str:
    """Resolve folder icon path with fallback to configured folder/default icon."""
    if icon_path:
        p = Path(icon_path)
        if p.is_absolute():
            if p.exists() and is_valid_icon_file(str(p)):
                return str(p)
        else:
            rel = resolve_icon_path(icon_path)
            if rel and not _is_default_fallback(rel):
                return rel
    # fallback to folder default
    try:
        from app.config_data import app_config

        defaults = app_config.get_default_icons()
        folder_name = defaults.get("folder", defaults.get("default", ""))
        path = resolve_icon_path(folder_name)
        if path and not _is_default_fallback(path):
            return path
        return path or str(get_default_icon_path())
    except Exception:
        return str(get_default_icon_path())


def resolve_link_type_icon_path(icon_path: Optional[str], link_type: str) -> str:
    """Resolve link icon path with fallback to type-specific default."""
    if icon_path:
        p = Path(icon_path)
        if p.is_absolute():
            if p.exists() and is_valid_icon_file(str(p)):
                return str(p)
        else:
            rel = resolve_icon_path(icon_path)
            if rel and not _is_default_fallback(rel):
                return rel
    # fallback to type-specific default
    try:
        from app.config_data import app_config

        defaults = app_config.get_default_icons()
        lt = ((link_type or "file").strip() or "file").lower()
        type_name = defaults.get(lt, defaults.get("default", ""))
        path = resolve_icon_path(type_name)
        if path and not _is_default_fallback(path):
            return path
        return path or str(get_default_icon_path())
    except Exception:
        return str(get_default_icon_path())
