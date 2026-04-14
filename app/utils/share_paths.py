from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from PyQt6.QtCore import QStandardPaths

from app.config_data import app_config
from app.core.paths.path_manager import PathManager

logger = logging.getLogger(__name__)

SERVICE_ROOT_NAME: Final[str] = "AiteCommander"

ENTITY_SUBDIRS: Final[dict[str, Path]] = {
    "sections": Path("Sections"),
    "categories": Path("Categories"),
    "database": Path("Databases"),
    "links": Path("Links"),
    "icons": Path("Icons"),
    "themes": Path("Themes"),
}


def get_desktop_dir() -> Path | None:
    """Return desktop directory if available."""
    try:
        desktop = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DesktopLocation
        )
    except Exception:
        desktop = ""
    if desktop:
        p = Path(desktop)
        if p.exists():
            return p
    return None


def _get_default_service_root_base() -> Path:
    org_name = app_config.get("app.org_name", PathManager.DEFAULT_ORG_NAME)
    app_name = app_config.get("app.name", PathManager.DEFAULT_APP_NAME)
    return PathManager.user_data_root(org_name, app_name)


def ensure_service_root(base_dir: Path | None = None) -> Path | None:
    """Ensure service root and subdirectories exist under base_dir."""
    root = (base_dir or _get_default_service_root_base()) / SERVICE_ROOT_NAME
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Failed to create service root %s: %s", root, exc)
        return None
    for sub in ENTITY_SUBDIRS.values():
        try:
            (root / sub).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Failed to create service subdir %s: %s", root / sub, exc)
            return None
    return root


def get_export_dir(root: Path, package_type: str) -> Path:
    return get_entity_dir(root, package_type)


def get_import_dir(root: Path, package_type: str) -> Path:
    return get_entity_dir(root, package_type)


def get_entity_dir(root: Path, entity: str) -> Path:
    key = (entity or "").lower()
    if key in ("section", "sections"):
        return root / ENTITY_SUBDIRS["sections"]
    if key in ("category", "categories"):
        return root / ENTITY_SUBDIRS["categories"]
    if key in ("database", "databases", "db", "backup", "backups"):
        return root / ENTITY_SUBDIRS["database"]
    if key in ("icon", "icons"):
        return root / ENTITY_SUBDIRS["icons"]
    if key in ("link", "links", "bookmark", "bookmarks"):
        return root / ENTITY_SUBDIRS["links"]
    if key in ("theme", "themes"):
        return root / ENTITY_SUBDIRS["themes"]
    return root / Path(entity)
