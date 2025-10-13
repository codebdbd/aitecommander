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


# Negative cache moved to unified negative_cache module

# Icon index by themes: theme -> {lower_name: Path}
_THEME_ICON_INDEX: dict[str, dict[str, Path]] = {}
_INDEX_LOCK = threading.RLock()
_INDEX_TTL: float = 60.0
_THEME_INDEX_TS: dict[str, float] = {}
_THEME_DIR_MTIME: dict[str, float] = {}

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


def _build_theme_index(theme: str) -> None:
    """Build icon index for theme.
    Stores only valid files. No side effects.
    """
    ui_dir = _icon_path_service.get_ui_icons_dir()
    theme_dir = ui_dir / theme
    mapping: dict[str, Path] = {}
    try:
        if theme_dir.is_dir():
            for p in theme_dir.iterdir():
                if p.is_file() and is_valid_icon_file(p):
                    mapping[p.name.lower()] = p
    except (OSError, PermissionError) as exc:
        logger.debug(
            "Index build failed for theme %s due to filesystem error: %s", theme, exc
        )
        mapping = {}
    except Exception:
        logger.exception(
            "_build_theme_index: unexpected error when traversing theme directory '%s'",
            theme,
        )
        mapping = {}
    # Get theme directory mtime (if available)
    try:
        dir_mtime = theme_dir.stat().st_mtime if theme_dir.is_dir() else 0.0
    except (OSError, PermissionError):
        dir_mtime = 0.0
    except Exception:
        logger.exception(
            "_build_theme_index: unexpected error getting mtime for theme '%s'",
            theme,
        )
        dir_mtime = 0.0
    with _INDEX_LOCK:
        _THEME_ICON_INDEX[theme] = mapping
        _THEME_INDEX_TS[theme] = time.time()
        _THEME_DIR_MTIME[theme] = dir_mtime


def _get_indexed_icon(theme: str, icon_name: str) -> Path | None:
    """Return Path from index or None. Creates/updates index by TTL."""
    name_key = icon_name.lower()
    # Read index state under common lock
    with _INDEX_LOCK:
        ts = _THEME_INDEX_TS.get(theme, 0.0)
        stored_mtime = _THEME_DIR_MTIME.get(theme, -1.0)
        has_index = theme in _THEME_ICON_INDEX
        index_ttl = getattr(app_config, "icon_index_ttl", _INDEX_TTL)

    # Check theme directory content change by mtime (outside lock)
    ui_dir = _icon_path_service.get_ui_icons_dir()
    theme_dir = ui_dir / theme
    try:
        current_mtime = theme_dir.stat().st_mtime if theme_dir.is_dir() else 0.0
    except (OSError, PermissionError) as exc:
        logger.warning(
            "_get_indexed_icon: failed to stat theme dir for mtime (theme=%s, dir=%s): %s",
            theme,
            theme_dir,
            exc,
        )
        current_mtime = 0.0

    # Decision to rebuild index is made based on snapshot, reading was under lock
    if (
        ((time.time() - ts) > index_ttl)
        or (not has_index)
        or (current_mtime != stored_mtime)
    ):
        _build_theme_index(theme)
    with _INDEX_LOCK:
        mapping = _THEME_ICON_INDEX.get(theme, {})
        return mapping.get(name_key)


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


# --- Separation of responsibilities: Resolver for cache/search/conversion ---


class IconPathResolver:
    """Responsible for stages: cache/negative cache/metrics, search by theme indexes, SVG→PNG conversion.

    Methods:
    - resolve_from_cache: name validation, negative cache, hits/misses in path cache.
      Returns (path_or_none, terminal). If terminal=True — result is final.
    - find_source: fast search for icon files by theme indexes (with fallback to light).
    - convert_svg: attempt to convert SVG to PNG (in theme and/or from light).
    """

    def __init__(self, service: IconPathService) -> None:
        self.service = service

    # --- Cache and statistics management ---
    def resolve_from_cache(self, icon_name: str, theme: str) -> tuple[str | None, bool]:
        if not _validate_icon_name(icon_name):
            logger.warning("Invalid icon name provided: %r", icon_name)
            set_path(icon_name, theme, None)  # negative caching
            try:
                _ICON_METRICS.record_not_found()
                _ICON_METRICS.record_miss_without_increment(0.0)
            finally:
                _maybe_log_metrics()
            return None, True

        norm_theme = validate_theme(theme)
        key = f"{norm_theme}:{icon_name.lower()}"

        # fast negative cache (unified module)
        if negative_cache.is_negative(key):
            logger.debug("Negative cache HIT: %s", key)
            try:
                _ICON_METRICS.record_not_found()
                _ICON_METRICS.record_miss_without_increment(0.0)
            finally:
                _maybe_log_metrics()
            return None, True

        cached = get_path(icon_name, norm_theme)
        if cached is not None:
            logger.debug("Path cache HIT: %s (%s)", icon_name, norm_theme)
            try:
                _ICON_METRICS.record_hit()
            finally:
                _maybe_log_metrics()
            return cached, True

        logger.debug("Path cache MISS: %s (%s)", icon_name, norm_theme)
        return None, False

    # --- Path search by index/themes ---
    def find_source(self, icon_name: str, theme: str) -> str | None:
        norm_theme = validate_theme(theme)
        idx_hit = _get_indexed_icon(norm_theme, icon_name)
        if idx_hit is not None:
            path_str = str(idx_hit)
            set_path(icon_name, norm_theme, path_str)
            try:
                metrics_record_disk_load()
            finally:
                _maybe_log_metrics()
            return path_str

        if norm_theme != "light":
            light_idx = _get_indexed_icon("light", icon_name)
            if light_idx is not None:
                path_str = str(light_idx)
                set_path(icon_name, norm_theme, path_str)
                try:
                    metrics_record_disk_load()
                finally:
                    _maybe_log_metrics()
                return path_str
        return None

    # --- Icon conversion ---
    def convert_svg(self, icon_name: str, theme: str) -> str | None:  # noqa: C901
        # Local import to avoid circular dependencies
        from .icon_operations.converters import convert_icon_to_png_128

        norm_theme = validate_theme(theme)
        ui_dir = self.service.get_ui_icons_dir()
        themed_path = ui_dir / norm_theme / icon_name

        # themed.svg → themed.png
        themed_svg = themed_path.with_suffix(".svg")
        if themed_svg.is_file() and is_valid_icon_file(themed_svg):
            themed_png = themed_path.with_suffix(".png")
            if themed_png.is_file():
                try:
                    if themed_png.stat().st_mtime >= themed_svg.stat().st_mtime:
                        path_str = str(themed_png)
                        set_path(icon_name, norm_theme, path_str)
                        logger.debug("Using up-to-date PNG: %s", themed_png)
                        try:
                            metrics_record_disk_load()
                        finally:
                            _maybe_log_metrics()
                        return path_str
                except (OSError, PermissionError) as exc:
                    logger.warning(
                        "convert_svg: failed to compare mtimes for themed files (icon=%s, theme=%s, png=%s, svg=%s): %s",
                        icon_name,
                        norm_theme,
                        themed_png,
                        themed_svg,
                        exc,
                    )
            slow_ms = float(
                getattr(app_config, "icon_slow_convert_threshold_ms", 150.0)
            )
            t0 = time.perf_counter()
            if convert_icon_to_png_128(str(themed_svg), str(themed_png)):
                dt_ms = (time.perf_counter() - t0) * 1000.0
                path_str = str(themed_png)
                set_path(icon_name, norm_theme, path_str)
                if dt_ms >= slow_ms:
                    logger.warning(
                        "Slow icon convert (%.1f ms): %s → %s",
                        dt_ms,
                        themed_svg,
                        themed_png,
                    )
                else:
                    logger.debug(
                        "Converted SVG to PNG (%.1f ms): %s → %s",
                        dt_ms,
                        themed_svg,
                        themed_png,
                    )
                try:
                    _ICON_METRICS.record_disk_load()
                    _ICON_METRICS.record_miss_without_increment(dt_ms / 1000.0)
                finally:
                    _maybe_log_metrics()
                return path_str

        # light.svg → themed.png
        if norm_theme != "light":
            light_svg = (ui_dir / "light" / icon_name).with_suffix(".svg")
            if light_svg.is_file() and is_valid_icon_file(light_svg):
                themed_png = themed_path.with_suffix(".png")
                if themed_png.is_file():
                    try:
                        if themed_png.stat().st_mtime >= light_svg.stat().st_mtime:
                            path_str = str(themed_png)
                            set_path(icon_name, norm_theme, path_str)
                            logger.debug(
                                "Using up-to-date PNG (from light SVG): %s", themed_png
                            )
                            try:
                                metrics_record_disk_load()
                            finally:
                                _maybe_log_metrics()
                            return path_str
                    except (OSError, PermissionError) as exc:
                        logger.warning(
                            "convert_svg: failed to compare mtimes for light fallback (icon=%s, theme=%s, png=%s, light_svg=%s): %s",
                            icon_name,
                            norm_theme,
                            themed_png,
                            light_svg,
                            exc,
                        )
                slow_ms = float(
                    getattr(app_config, "icon_slow_convert_threshold_ms", 150.0)
                )
                t0 = time.perf_counter()
                if convert_icon_to_png_128(str(light_svg), str(themed_png)):
                    dt_ms = (time.perf_counter() - t0) * 1000.0
                    path_str = str(themed_png)
                    set_path(icon_name, norm_theme, path_str)
                    if dt_ms >= slow_ms:
                        logger.warning(
                            "Slow icon convert (fallback, %.1f ms): %s → %s",
                            dt_ms,
                            light_svg,
                            themed_png,
                        )
                    else:
                        logger.debug(
                            "Converted fallback SVG to PNG (%.1f ms): %s → %s",
                            dt_ms,
                            light_svg,
                            themed_png,
                        )
                    try:
                        _ICON_METRICS.record_disk_load()
                        _ICON_METRICS.record_miss_without_increment(dt_ms / 1000.0)
                    finally:
                        _maybe_log_metrics()
                    return path_str
        return None


# --- Icon path search and caching ---


def get_icon_path(icon_name: str, theme: str = "light") -> str | None:
    """Get string path to icon. Thin wrapper around IconPathResolver."""
    resolver = IconPathResolver(_icon_path_service)

    # 1) cache/negative cache/validation/metrics
    cached_or_none, terminal = resolver.resolve_from_cache(icon_name, theme)
    if terminal:
        return cached_or_none

    # 2) search by theme indexes
    found = resolver.find_source(icon_name, theme)
    if found is not None:
        return found

    # 3) SVG→PNG conversion
    converted = resolver.convert_svg(icon_name, theme)
    if converted is not None:
        return converted

    # 4) negative caching when completely absent
    norm_theme = validate_theme(theme)
    key = f"{norm_theme}:{icon_name.lower()}"
    set_path(icon_name, norm_theme, None)
    negative_cache.mark_negative(key)
    logger.debug("Icon path not found, cached negative: %s (%s)", icon_name, norm_theme)
    try:
        _ICON_METRICS.record_not_found()
        _ICON_METRICS.record_actual_miss(0.0)
    finally:
        _maybe_log_metrics()
    return None


def get_qss_dir() -> Path:
    """Path to QSS themes directory."""
    return app_config.paths.get_qss_dir()


_CURRENT_THEME_CACHE: str | None = None
_LAST_THEME_CHECK: float = 0.0
_THEME_CACHE_TTL: float = 3.0
_theme_lock = threading.RLock()


def get_current_theme() -> str:
    """Get current theme with cache, return 'light' if unavailable."""
    global _CURRENT_THEME_CACHE, _LAST_THEME_CHECK

    now = time.time()
    # Fast path: read cache under lock
    with _theme_lock:
        if (
            _CURRENT_THEME_CACHE is not None
            and (now - _LAST_THEME_CHECK) < _THEME_CACHE_TTL
        ):
            return _CURRENT_THEME_CACHE

    # Slow path: try to get from GUI without holding lock
    try:
        from typing import cast
        from PyQt6.QtWidgets import QApplication  # local import

        app_instance = QApplication.instance()
        if app_instance:
            app = cast(QApplication, app_instance)
            for widget in app.topLevelWidgets():
                # expect settings.get_theme() to be available
                settings = getattr(widget, "settings", None)
                if settings and hasattr(settings, "get_theme"):
                    theme = validate_theme(settings.get_theme())
                    with _theme_lock:
                        _CURRENT_THEME_CACHE = theme
                        _LAST_THEME_CHECK = now
                    return theme
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not get current theme from GUI: %s", exc)

    # Fallback: write 'light' to cache under lock
    with _theme_lock:
        _CURRENT_THEME_CACHE = "light"
        _LAST_THEME_CHECK = now
    return "light"


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
