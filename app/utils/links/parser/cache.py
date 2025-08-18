"""Cache helpers for link metadata (title/icon)."""
from __future__ import annotations

import os
import time
import shelve
from contextlib import closing
from typing import Any, Dict, Optional

from app.utils.ui.icon.path_service import icon_path_service
from .constants import CACHE_TTL, SHORT_NEGATIVE_TTL, logger


def get_cache_path(config=None) -> str:
    return str(icon_path_service.get_user_icons_dir() / "favicon_cache.db")


def read_cache(url: str, config) -> Optional[Dict[str, Any]]:
    path = get_cache_path(config)
    with closing(shelve.open(path)) as db:
        item = db.get(url)
        if not item:
            return None
        default_icon = config.get_default_icons().get("web", "")
        if "ttl" not in item and item.get("icon") == default_icon:
            ttl = SHORT_NEGATIVE_TTL
        else:
            ttl = item.get("ttl", CACHE_TTL)
        if time.time() - item.get("timestamp", 0) < ttl:
            logger.debug(f"[cache] HIT {url}")
            return item
    return None


def write_cache(url: str, data: Dict[str, Any], config):
    path = get_cache_path(config)
    with closing(shelve.open(path, writeback=True)) as db:
        db[url] = data
        logger.debug(f"[cache] SAVE {url}")


__all__ = ["get_cache_path", "read_cache", "write_cache"]
