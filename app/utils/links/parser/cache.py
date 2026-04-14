"""Cache helpers for link metadata (title/icon).

Migrated to file-based `FaviconCache` while preserving the legacy API.
"""

from __future__ import annotations

from typing import Any

from app.utils.ui.icon.path_service import icon_path_service

from .constants import logger
from .favicon_cache import favicon_cache


def get_cache_path(config=None) -> str:
    icons_dir = icon_path_service.get_user_icons_dir()
    cache_dir = icons_dir.parent / "icon_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return str(cache_dir / "favicon_cache.db")


def read_cache(url: str, config) -> dict[str, Any] | None:
    item = favicon_cache.get(url)
    if item is not None:
        logger.debug("[cache] HIT %s", url)
    return item


def write_cache(url: str, data: dict[str, Any], config):
    # ttl can be provided via data["ttl"], FaviconCache accounts for it
    favicon_cache.set(url, data, ttl=data.get("ttl"))


__all__ = ["get_cache_path", "read_cache", "write_cache"]
