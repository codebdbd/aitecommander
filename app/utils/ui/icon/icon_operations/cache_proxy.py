# cache_proxy.py
"""Proxy class for menu icon caching with async support."""

from __future__ import annotations

import asyncio
import logging

from PyQt6.QtGui import QIcon

from ..cache_manager import get_theme_icon, get_theme_icon_async

logger = logging.getLogger(__name__)


class IconCache:
    """Icon cache for menu with LRU and async support."""

    def get_icon(
        self, name: str, theme: str | None = None, source: str = "menu"
    ) -> QIcon:
        """Get icon with caching via central cache manager."""
        return get_theme_icon(name, theme, source)

    async def get_icon_async(
        self, name: str, theme: str | None = None, source: str = "menu"
    ) -> QIcon:
        """Get icon asynchronously with caching via central cache manager."""
        return await get_theme_icon_async(name, theme, source)

    def clear_cache(self) -> None:
        """Clear cache (when changing theme)."""
        logger.debug("Clearing icon cache")
        # Clear global cache and path cache
        # Lazy loading to avoid circular imports at module level
        from ..cache_manager import clear_icon_cache

        clear_icon_cache()
        # Clear path cache via service
        from ..path_service import icon_path_service

        icon_path_service.clear_cache()
        logger.debug("Icon cache cleared successfully")

    async def clear_cache_async(self) -> None:
        """Clear cache asynchronously."""
        await asyncio.get_event_loop().run_in_executor(None, self.clear_cache)
        logger.debug("Icon cache cleared asynchronously")


# Single global instance
icon_cache = IconCache()
