# path_service.py
"""Centralized path service for icons and resources."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from app.config_data import app_config

from .cache_manager import get_path, set_path
from .metrics import CacheMetrics
from .negative_cache import negative_cache
from .validation import (
    _validate_icon_name,
    is_valid_icon_file,
    validate_theme,
)

logger = logging.getLogger(__name__)

# --- Metrics ---
_ICON_METRICS = CacheMetrics()
_METRICS_LAST_LOG: float = 0.0
_metrics_lock = threading.Lock()


def _maybe_log_metrics() -> None:
    global _METRICS_LAST_LOG
    # Get metrics logging interval with narrow error handling
    try:
        raw_interval = getattr(app_config, "icon_metrics_report_interval_s", 60.0)
    except AttributeError:
        raw_interval = 60.0
    except Exception:
        logger.exception(
            "_maybe_log_metrics: unexpected error accessing app_config.icon_metrics_report_interval_s"
        )
        raw_interval = 60.0
    try:
        interval = float(raw_interval)
    except (TypeError, ValueError):
        interval = 60.0
    except Exception:
        logger.exception(
            "_maybe_log_metrics: unexpected error converting interval to float"
        )
        interval = 60.0
    now = time.time()
    # Critical section: window check and timestamp update
    with _metrics_lock:
        if now - _METRICS_LAST_LOG < interval:
            return
        _METRICS_LAST_LOG = now

    # Logging is performed outside the lock to avoid blocking other threads
    try:
        stats = _ICON_METRICS.get_stats()
        # Use safe key access to avoid KeyError
        logger.info(
            "Icon metrics: hits=%s misses=%s hit_rate=%s disk_loads=%s not_found=%s avg_load_time=%s load_count=%s uptime=%s",
            stats.get("hits"),
            stats.get("misses"),
            stats.get("hit_rate"),
            stats.get("disk_loads"),
            stats.get("not_found"),
            stats.get("avg_load_time"),
            stats.get("load_count"),
            stats.get("uptime"),
        )
    except (AttributeError, TypeError, ValueError):
        logger.exception("_maybe_log_metrics: incorrect metrics statistics format")
    except Exception:
        logger.exception("_maybe_log_metrics: unexpected error when logging metrics")



class IconPathService:
    """Singleton service for managing icon and resource paths."""

    _instance: IconPathService | None = None

    def __new__(cls) -> IconPathService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self._user_icons_dir: Path | None = None
        self._ui_icons_dir: Path | None = None
        self._user_data_dir: Path | None = None

    # --- User and UI folders ---

    def get_user_icons_dir(self) -> Path:
        """Path to user icons folder (delegates to PathConfig)."""
        if self._user_icons_dir is None:
            # Single source of truth — PathConfig
            self._user_icons_dir = app_config.paths.get_link_icons_dir()
        return self._user_icons_dir

    def ensure_user_icons_dir(self) -> Path:
        """Create user icons folder (delegates to PathConfig)."""
        app_config.paths.ensure_user_data_dirs()
        return self.get_user_icons_dir()

    def get_user_icon_path(self, filename: str) -> Path:
        """Full path to user icon."""
        return self.get_user_icons_dir() / filename

    def get_ui_icons_dir(self) -> Path:
        """Path to UI icons directory (delegates to PathConfig)."""
        if self._ui_icons_dir is None:
            self._ui_icons_dir = app_config.paths.get_ui_icons_dir()
        return self._ui_icons_dir

    # --- Helper addresses ---

    def get_themed_icon_path(self, icon_name: str, theme: str = "light") -> Path:
        """Path to icon in specified theme (without existence check)."""
        return self.get_ui_icons_dir() / theme / icon_name

    def get_ui_icon_path(self, icon_name: str, theme: str = "light") -> Path | None:
        """Path to existing UI icon with fallback to light."""
        themed_path = self.get_themed_icon_path(icon_name, theme)
        if themed_path.exists():
            return themed_path

        if theme != "light":
            light_path = self.get_themed_icon_path(icon_name, "light")
            if light_path.exists():
                return light_path

        return None

    def get_web_icon_path(self, domain: str) -> Path:
        """Path to user website icon (favicon cache)."""
        filename = f"web_{domain.replace('.', '_')}.png"
        return self.get_user_icon_path(filename)

    def get_favicon_cache_path(self) -> Path:
        """Path to favicon cache file."""
        return self.get_user_icon_path("favicon_cache.db")

    def get_folder_icon_path(self) -> Path:
        """Path to folder icon (warns if file doesn't exist)."""
        folder_icon = self.get_ui_icons_dir() / "folder_icon.png"
        if not folder_icon.exists():
            logger.warning("Folder icon file does not exist: %s", folder_icon)
        return folder_icon

    # --- Application / resource directories ---

    def _get_user_data_dir(self) -> Path:
        """User data folder (delegates to PathConfig)."""
        if self._user_data_dir is None:
            self._user_data_dir = app_config.paths.get_user_data_dir()
        return self._user_data_dir

    def clear_cache(self) -> None:
        """Reset internal path caches."""
        self._user_icons_dir = None
        self._ui_icons_dir = None
        self._user_data_dir = None
        logger.debug("Icon path service caches cleared")


# --- Global instance and convenient proxy functions ---

_icon_path_service = IconPathService()


# --- IconPathResolver has been removed ---
# The IconPathResolver class was only used by get_icon_path(), which has been deprecated.
# For UI icons, use the new simplified system: app.utils.ui.icons.get_icon()
# User-provided icons (links, categories) use create_icon_from_path() directly.




# get_icon_path() has been removed - use app.utils.ui.icons.get_icon() for UI icons


def get_qss_dir() -> Path:
    """Path to QSS themes directory."""
    return app_config.paths.get_qss_dir()


# get_current_theme() has been removed - use app.utils.ui.icons.get_current_theme() instead


# Global service export
icon_path_service = _icon_path_service


# --- Public metrics helpers ---
def get_icon_metrics_stats() -> dict[str, Any]:
    """Return current icon subsystem metrics summary."""
    return _ICON_METRICS.get_stats()


def reset_icon_metrics() -> None:
    """Reset icon subsystem metrics."""
    _ICON_METRICS.reset()


# --- Helper functions for writing metrics for other modules ---
def metrics_record_hit() -> None:
    try:
        _ICON_METRICS.record_hit()
    finally:
        _maybe_log_metrics()


def metrics_record_disk_load(duration_s: float = 0.0) -> None:
    try:
        _ICON_METRICS.record_disk_load()
        if duration_s and duration_s > 0:
            _ICON_METRICS.record_miss_without_increment(duration_s)
    finally:
        _maybe_log_metrics()


def metrics_record_not_found(duration_s: float = 0.0) -> None:
    try:
        _ICON_METRICS.record_not_found()
        _ICON_METRICS.record_actual_miss(duration_s if duration_s > 0 else 0.0)
    finally:
        _maybe_log_metrics()


def metrics_record_miss(duration_s: float = 0.0) -> None:
    try:
        _ICON_METRICS.record_actual_miss(duration_s if duration_s > 0 else 0.0)
    finally:
        _maybe_log_metrics()
