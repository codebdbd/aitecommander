from functools import lru_cache
import re
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QCoreApplication

from .path_service import icon_path_service
from .validation import is_valid_icon_file


@lru_cache(maxsize=1024)
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
        if p.is_absolute():
            if p.exists() and is_valid_icon_file(str(p)):
                return str(p)
            normalized = p.name
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


def clear_icon_resolver_cache() -> None:
    """Clear in-memory icon path resolution cache."""
    _resolve_filesystem.cache_clear()


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


DEFAULT_SPHERE_ICONS_BY_NUMBER: dict[int, str] = {
    1: "ai_icon.png",
    2: "work_icon.png",
    3: "study_icon.png",
    4: "personal_icon.png",
}

DEFAULT_SPHERE_NAMES_BY_NUMBER: dict[int, str] = {
    1: "AI",
    2: "Work",
    3: "Study",
    4: "Personal",
}


def get_default_sphere_icon_name(
    sphere: dict | str | int | None = None, position: int | None = None
) -> str:
    """Return default icon filename for a sphere mapped by number (1=, 2=, 3=, 4=...)."""
    num: int | None = None

    # 1. Direct position argument (in DB/UI, position is 0-indexed: 0 -> sphere 1, 1 -> sphere 2, ...)
    if position is not None and isinstance(position, int):
        num = position + 1 if position >= 0 else None

    # 2. Integer sphere argument
    if num is None and isinstance(sphere, int):
        num = sphere if sphere > 0 else 1

    # 3. String or dict sphere argument
    name = ""
    if isinstance(sphere, str):
        name = sphere.strip()
    elif isinstance(sphere, dict):
        name = str(sphere.get("name") or "").strip()
        if num is None:
            if sphere.get("position") is not None and isinstance(sphere["position"], int):
                num = int(sphere["position"]) + 1
            elif sphere.get("id") is not None and isinstance(sphere["id"], int):
                num = int(sphere["id"])
            elif sphere.get("number") is not None and isinstance(sphere["number"], int):
                num = int(sphere["number"])

    # 4. Check name if available
    if name:
        name_clean = name.lower()
        # Direct digit check (e.g. "1", "1=", "2", "3", "4", "Sphere 1")
        match = re.search(r"\b([1-9]\d*)\b", name)
        if match:
            num = int(match.group(1))
        else:
            canonical_keys = {"ai": 1, "work": 2, "study": 3, "personal": 4}
            if name_clean in canonical_keys:
                num = canonical_keys[name_clean]
            else:
                # Dynamically resolve using Qt translation engine (no hardcoded language dicts)
                for n, eng_name in DEFAULT_SPHERE_NAMES_BY_NUMBER.items():
                    try:
                        translated = (
                            QCoreApplication.translate("SpheresBarController", eng_name)
                            .strip()
                            .lower()
                        )
                        if translated and (name_clean == translated or translated in name_clean):
                            num = n
                            break
                    except Exception:
                        pass

    if num is not None and num > 0:
        if num in DEFAULT_SPHERE_ICONS_BY_NUMBER:
            return DEFAULT_SPHERE_ICONS_BY_NUMBER[num]
        cycled = ((num - 1) % len(DEFAULT_SPHERE_ICONS_BY_NUMBER)) + 1
        return DEFAULT_SPHERE_ICONS_BY_NUMBER[cycled]

    return DEFAULT_SPHERE_ICONS_BY_NUMBER[1]


def resolve_sphere_icon_path(
    icon_path: Optional[str],
    sphere: dict | str | None = None,
    position: int | None = None,
) -> str:
    """Resolve sphere icon path with fallback to default sphere icon."""
    if icon_path:
        p = Path(icon_path)
        if p.is_absolute():
            if p.exists() and is_valid_icon_file(str(p)):
                return str(p)
            rel = _resolve_filesystem(p.name)
            if rel:
                return rel
        else:
            rel = _resolve_filesystem(icon_path)
            if rel:
                return rel
    default_name = get_default_sphere_icon_name(sphere, position)
    if default_name:
        resolved = _resolve_filesystem(default_name)
        if resolved:
            return resolved
    return _type_default_path("sphere")
