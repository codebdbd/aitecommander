# cache_proxy.py
"""Proxy class for menu icon caching (simplified for new icon system)."""

from __future__ import annotations

import asyncio
import logging

from PyQt6.QtGui import QIcon

logger = logging.getLogger(__name__)


class IconCache:
    """Icon cache for menu with LRU and async support."""

    def get_icon(
        self, name: str, theme: str | None = None, source: str = "menu"
    ) -> QIcon:
        """Get icon with caching.
        
        Routes to appropriate system:
        - UI icons (simple names like 'delete', 'add_link.svg') -> new simplified system
        - User icons (paths, .ico, web_*.png, etc.) -> old system create_icon_from_path()
        """
        # Check if this is a user-provided icon (has path separators or specific patterns)
        is_user_icon = (
            "/" in name or
            "\\" in name or
            name.endswith(".ico") or
            name.endswith(".png") or
            name.startswith("web_") or
            name == "category.png"
        )
        
        if is_user_icon:
            # User icon - use old system with full path resolution
            from .creators import create_icon_from_path
            
            try:
                return create_icon_from_path(name)
            except Exception as exc:
                logger.debug("Failed to load user icon '%s': %s", name, exc)
                return QIcon()
        else:
            # UI icon - use new simplified system
            from app.utils.ui.icons import get_icon
            
            # Add .svg extension if not specified
            icon_name = name if "." in name else f"{name}.svg"
            
            return get_icon(icon_name, theme)

    async def get_icon_async(
        self, name: str, theme: str | None = None, source: str = "menu"
    ) -> QIcon:
        """Get icon asynchronously (instant with new system)."""
        # With new icon system, loading is instant after first access
        # No need for async, but keep method for backward compatibility
        return self.get_icon(name, theme, source)

    def clear_cache(self) -> None:
        """Clear cache (when changing theme)."""
        from app.utils.ui.icons import clear_cache
        
        clear_cache()
        logger.debug("Icon cache cleared successfully")

    async def clear_cache_async(self) -> None:
        """Clear cache asynchronously."""
        await asyncio.get_event_loop().run_in_executor(None, self.clear_cache)
        logger.debug("Icon cache cleared asynchronously")

    async def preload_icons_async(
        self, icon_names: list[str], theme: str | None = None
    ) -> dict[str, QIcon]:
        """Preload multiple icons (instant with new system)."""
        from app.utils.ui.icons import preload_icons
        
        # With new icon system, preloading is synchronous and instant
        icon_names_with_ext = [
            name if "." in name else f"{name}.svg" for name in icon_names
        ]
        
        preload_icons(icon_names_with_ext, theme)
        
        # Return dict for backward compatibility
        result = {name: self.get_icon(name, theme) for name in icon_names}
        return result


# Single global instance
icon_cache = IconCache()
