# __init__.py
"""
Icon operations module - split into logical components with async support.

Structure:
- cache_proxy.py: IconCache class for menu icon caching
- converters.py: Icon conversion and copying functions
- creators.py: QIcon creation functions with thread safety
"""

from __future__ import annotations

# Import from validation (for compatibility)
from ..validation import is_valid_icon_file

# Import from cache_proxy
from .cache_proxy import IconCache, icon_cache

# Import from converters
from .converters import (  # Synchronous copy functions; Synchronous conversion functions; Asynchronous copy functions; Asynchronous conversion functions; Batch conversion
    batch_convert_icons_async,
    convert_icon_to_png_32,
    convert_icon_to_png_32_async,
    convert_icon_to_png_128,
    convert_icon_to_png_128_async,
    convert_raster_icon_to_png,
    convert_raster_icon_to_png_async,
    copy_icon,
    copy_icon_async,
    copy_icon_smart,
    copy_icon_to_path,
    copy_icon_to_path_async,
)

# Import from creators
from .creators import (  # Main icon creation functions; Creating icons from absolute paths; Internal functions (for compatibility)
    _create_svg_icon,
    _ensure_gui_thread,
    create_icon_from_path,
    create_icon_from_path_async,
    themed_icon,
    themed_icon_async,
)

# Export all public functions and classes
__all__ = [
    # Icon cache
    "IconCache",
    "icon_cache",
    # Synchronous copy functions
    "copy_icon",
    "copy_icon_smart",
    "copy_icon_to_path",
    # Synchronous conversion functions
    "convert_icon_to_png_128",
    "convert_icon_to_png_32",
    "convert_raster_icon_to_png",
    # Asynchronous copy functions
    "copy_icon_async",
    "copy_icon_to_path_async",
    # Asynchronous conversion functions
    "convert_icon_to_png_128_async",
    "convert_icon_to_png_32_async",
    "convert_raster_icon_to_png_async",
    # Batch conversion
    "batch_convert_icons_async",
    # Main icon creation functions
    "themed_icon",
    "themed_icon_async",
    # Creating icons from absolute paths
    "create_icon_from_path",
    "create_icon_from_path_async",
    # Internal functions (for compatibility)
    "_create_svg_icon",
    "_ensure_gui_thread",
    # Validation functions (for compatibility)
    "is_valid_icon_file",
]
