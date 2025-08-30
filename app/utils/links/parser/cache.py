"""Cache helpers for link metadata (title/icon).

Переход на файловый кэш `FaviconCache`, сохраняя прежний API.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.utils.ui.icon.path_service import icon_path_service

from .constants import logger
from .favicon_cache import favicon_cache


def get_cache_path(config=None) -> str:
    # Путь совместим с прежней реализацией
    return str(icon_path_service.get_user_icons_dir() / "favicon_cache.db")


def read_cache(url: str, config) -> Optional[Dict[str, Any]]:
    item = favicon_cache.get(url)
    if item is not None:
        logger.debug(f"[cache] HIT {url}")
    return item


def write_cache(url: str, data: Dict[str, Any], config):
    # ttl может быть задан в data["ttl"], FaviconCache учтёт его
    favicon_cache.set(url, data, ttl=data.get("ttl"))
    logger.debug(f"[cache] SAVE {url}")


__all__ = ["get_cache_path", "read_cache", "write_cache"]
