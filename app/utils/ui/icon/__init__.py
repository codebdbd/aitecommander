"""Module for working with icons (cache, validation, metrics)"""

# Import all public functions and classes from modules

# Cache management
from .cache_manager import (
    IconManager,
    ThreadSafeIconCache,
    clear_icon_cache,
    get_cached_category_icon,
    get_icon_cache_stats,
    log_icon_cache_stats,
    reset_icon_cache_stats,
)

# Category path resolution - from icon_resolver to avoid circular imports
from .icon_resolver import (
    resolve_category_icon_path,
)

# Centralized locking system
from .lock_manager import (
    LockLevel,
    acquire_cache_lock,
    acquire_global_lock,
    acquire_lru_lock,
    acquire_metrics_lock,
    acquire_multiple_locks,
)

# LRU policy
from .lru_policy import LRUPolicy

# Cache metrics
from .metrics import CacheMetrics

# Centralized icon path service
from .path_service import (
    IconPathService,
    get_current_theme,
    get_icon_path,
    get_qss_dir,
    icon_path_service,
)

# Import is_valid_icon_file from local validator
# Validation and checks
from .validation import (
    IconError,
    IconNotFoundError,
    InvalidIconError,
    Theme,
    is_cached_icon_valid,
    is_valid_icon_file,
    validate_config_for_icons,
    validate_theme,
)

# Icon operations (new modular structure)
# IMPORTANT: Avoid heavy re-exports from icon_operations to prevent circular imports.
# Use explicit imports from subpackages, for example:
#   from app.utils.ui.icon.icon_operations.creators import themed_icon, create_icon_from_path

# Import conversion functions directly from converters
# Converters are no longer re-exported from the root package.
#   from app.utils.ui.icon.icon_operations.converters import copy_icon_smart, convert_icon_to_png_128, ...

# UI utilities for working with icons
# UI helpers are not re-exported.
#   from app.utils.ui.icon.ui_helpers import set_icon_to_button

# Menu icon cache
# (functionality moved to icon_operations.py)

# Export all public functions and classes
__all__ = [
    # Validation and checks
    "Theme",
    "IconError",
    "IconNotFoundError",
    "InvalidIconError",
    "validate_theme",
    "is_valid_icon_file",
    "is_cached_icon_valid",
    "validate_config_for_icons",
    # Centralized path service
    "IconPathService",
    "icon_path_service",
    # Working with paths
    "get_icon_path",
    "get_current_theme",
    "get_qss_dir",
    "resolve_category_icon_path",
    # Cache management
    "ThreadSafeIconCache",
    "IconManager",
    "clear_icon_cache",
    "get_icon_cache_stats",
    "reset_icon_cache_stats",
    "log_icon_cache_stats",
    "get_cached_category_icon",
    # Cache metrics (only from metrics.py)
    "CacheMetrics",
    # LRU policy
    "LRUPolicy",
    # Centralized locking system
    "LockLevel",
    "acquire_global_lock",
    "acquire_cache_lock",
    "acquire_metrics_lock",
    "acquire_lru_lock",
    "acquire_multiple_locks",
    # Note: icon creation/conversion functions and UI helpers
    # are available through explicit subpackages and are not re-exported here to avoid import cycles.
]
