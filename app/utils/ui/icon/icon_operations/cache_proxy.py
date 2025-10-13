# cache_proxy.py
"""Proxy class for menu icon caching with async support."""

from __future__ import annotations

import asyncio
import logging

from PyQt6.QtGui import QIcon

from ..path_service import get_current_theme
from ..validation import validate_theme

logger = logging.getLogger(__name__)


class IconCache:
    """Icon cache for menu with LRU and async support."""

    def get_icon(
        self, name: str, theme: str | None = None, source: str = "menu"
    ) -> QIcon:
        """Get icon with caching via proxy to global manager."""
        if theme is None:
            theme = get_current_theme()
        theme = validate_theme(theme)

        # Add .svg extension if not specified
        icon_name = name if "." in name else f"{name}.svg"

        # Import here to avoid circular imports
        from .creators import themed_icon

        # themed_icon() will check cache itself, so just call it directly
        # This eliminates redundant double cache check
        return themed_icon(icon_name, theme, source)

    async def get_icon_async(
        self, name: str, theme: str | None = None, source: str = "menu"
    ) -> QIcon:
        """Get icon asynchronously with caching."""
        if theme is None:
            theme = get_current_theme()
        theme = validate_theme(theme)

        # Add .svg extension if not specified
        icon_name = name if "." in name else f"{name}.svg"

        # Import here to avoid circular imports
        from .creators import themed_icon_async

        return await themed_icon_async(icon_name, theme, source)

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

    async def preload_icons_async(
        self, icon_names: list[str], theme: str | None = None
    ) -> dict[str, QIcon]:
        """Preload multiple icons asynchronously."""
        # Guard against missing QApplication - fail fast
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            logger.error(
                "preload_icons_async called before QApplication initialization. "
                "Skipping preload."
            )
            # Return empty icons for all requested names
            return {name: QIcon() for name in icon_names}

        if theme is None:
            theme = get_current_theme()
        theme = validate_theme(theme)

        # Import here to avoid circular imports
        from .creators import themed_icon_async

        # Limit concurrent loading to avoid overloading disk/CPU
        # Make limit configurable via app_config, with safe default
        try:
            from app.config_data import (
                app_config,  # local import to avoid cycles
            )

            concurrency = int(getattr(app_config, "icon_preload_concurrency", 6))
        except Exception:  # noqa: BLE001
            concurrency = 6  # fallback
        sem = asyncio.Semaphore(concurrency)

        async def _load(name: str):
            icon_name = name if "." in name else f"{name}.svg"
            async with sem:
                try:
                    return await themed_icon_async(icon_name, theme, "preload")
                except Exception as e:  # noqa: BLE001
                    return e

        icon_tasks = [_load(name) for name in icon_names]
        icons = await asyncio.gather(*icon_tasks, return_exceptions=False)

        result = {}
        for name, icon in zip(icon_names, icons):
            if isinstance(icon, Exception):
                logger.warning("Failed to preload icon %s: %s", name, icon)
                result[name] = QIcon()  # Empty icon on error
            else:
                result[name] = icon

        logger.info("Preloaded %s icons for theme %s", len(result), theme)
        return result


# Single global instance
icon_cache = IconCache()
