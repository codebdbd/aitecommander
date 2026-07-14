# path_service.py
"""Centralized path service for icons and resources."""

from __future__ import annotations

import logging
import tempfile
import threading
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Union

# Third-party imports
try:
    from PyQt6.QtCore import QDir, QDirIterator, QFile, QFileInfo
except ImportError:  # pragma: no cover - optional at runtime
    QFile = None
    QFileInfo = None
    QDir = None
    QDirIterator = None

# First-party imports
from app.config_data import app_config

from .cache_manager import get_path, set_path
from .metrics_recorder import IconMetricsRecorder
from .negative_cache import negative_cache
from .validation import (
    _validate_icon_name,
    is_valid_icon_file,
    validate_theme,
)

# Import QRC resources if available (for packaged apps)
try:
    import app.resources.icons_rc  # noqa: F401
    _QRC_AVAILABLE = True
except ImportError:
    _QRC_AVAILABLE = False

USE_QRC_ICONS = True

logger = logging.getLogger(__name__)


Pathish = Union[Path, PurePosixPath]


def _is_qrc_path(path: Pathish | str) -> bool:
    return str(path).startswith(":/")


def _path_exists(path: Pathish) -> bool:
    if _is_qrc_path(path):
        if not _QRC_AVAILABLE or QFile is None:
            return False
        return QFile.exists(str(path))
    return Path(str(path)).exists()


def _path_is_file(path: Pathish) -> bool:
    if _is_qrc_path(path):
        if not _QRC_AVAILABLE or QFileInfo is None:
            return False
        return QFileInfo(str(path)).isFile()
    return Path(str(path)).is_file()


def _safe_mtime(path: Pathish) -> float | None:
    if _is_qrc_path(path):
        return None
    try:
        return Path(str(path)).stat().st_mtime
    except OSError:
        return None


def _read_qrc_bytes(path: Pathish) -> bytes | None:
    """Read Qt resource into memory."""
    if not _is_qrc_path(path) or not _QRC_AVAILABLE or QFile is None:
        return None
    file = QFile(str(path))
    if not file.exists() or not file.open(QFile.OpenModeFlag.ReadOnly):
        return None
    try:
        data = bytes(file.readAll())
    finally:
        file.close()
    return data


# Negative cache moved to unified negative_cache module

# Note: Icon index and metrics are now encapsulated in IconPathService class
# Global variables removed for better encapsulation and testability


# Helper functions moved to IconPathService class methods


class IconPathService:
    """Service for managing icon and resource paths.
    
    Supports both singleton pattern (for backward compatibility) and dependency injection.
    
    Args:
        user_icons_dir: Optional user icons directory. If None, uses app_config.
        ui_icons_dir: Optional UI icons directory. If None, uses app_config.
        config: Optional config object. If None, uses global app_config.
    """

    _instance: IconPathService | None = None

    def __new__(cls, *args, **kwargs) -> IconPathService:
        # If called without arguments, return singleton
        if not args and not kwargs:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
        # If called with arguments, create new instance (DI mode)
        return super().__new__(cls)

    def __init__(
        self,
        user_icons_dir: Path | None = None,
        ui_icons_dir: Path | None = None,
        config: Any | None = None,
    ) -> None:
        # Skip re-initialization for singleton
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self._user_icons_dir = user_icons_dir
        self._ui_icons_dir = ui_icons_dir
        self._config = config if config is not None else app_config
        
        # Icon index by themes: theme -> {lower_name: Path}
        self._theme_index: dict[str, dict[str, Path]] = {}
        self._index_lock = threading.RLock()
        self._index_ttl: float = 60.0
        self._theme_index_ts: dict[str, float] = {}
        self._theme_dir_mtime: dict[str, float] = {}
        # Cached listing of QRC resources per theme (only used when QRC is available)
        self._qrc_index: dict[str, set[str]] = {}
        self._user_data_dir: Path | None = None
        
        # Metrics recorder
        self._metrics = IconMetricsRecorder(use_qtimer=True)

    # --- User and UI folders ---

    def get_user_icons_dir(self) -> Path:
        """Path to user icons folder (delegates to PathConfig)."""
        if self._user_icons_dir is None:
            # Single source of truth - PathConfig
            self._user_icons_dir = self._config.paths.get_link_icons_dir()
        return self._user_icons_dir

    def ensure_user_icons_dir(self) -> Path:
        """Create user icons folder (delegates to PathConfig)."""
        self._config.paths.ensure_user_data_dirs()
        return self.get_user_icons_dir()

    def get_user_icon_path(self, filename: str) -> Path:
        """Full path to user icon."""
        return self.get_user_icons_dir() / filename

    def get_ui_icons_dir(self) -> Path:
        """Path to UI icons directory (delegates to PathConfig)."""
        if self._ui_icons_dir is None:
            self._ui_icons_dir = self._config.paths.get_ui_icons_dir()
        return self._ui_icons_dir

    def _get_theme_definition(self, theme: str):
        try:
            from app.services.theme_registry import theme_registry

            return theme_registry.get_theme(theme)
        except Exception:
            return None

    def _use_qrc_for_theme(self, theme: str) -> bool:
        if not _QRC_AVAILABLE or not USE_QRC_ICONS:
            return False
        info = self._get_theme_definition(theme)
        return bool(info and info.source == "bundled")

    def _get_icons_dir_for_theme(self, theme: str) -> Path:
        info = self._get_theme_definition(theme)
        if info and isinstance(info.icons_dir, Path):
            return info.icons_dir
        return self.get_ui_icons_dir() / theme

    # --- Helper addresses ---

    def get_themed_icon_path(self, icon_name: str, theme: str = "light") -> Path:
        """Path to icon in specified theme.
        
        Returns QRC path (:/icons/...) if resources are compiled,
        otherwise filesystem path.
        """
        norm_theme = validate_theme(theme)
        if self._use_qrc_for_theme(norm_theme):
            return PurePosixPath(f":/icons/{norm_theme}/{icon_name}")
        return self._get_icons_dir_for_theme(norm_theme) / icon_name

    def get_ui_icon_path(self, icon_name: str, theme: str = "light") -> Path | None:
        """Path to existing UI icon for the specified theme."""
        themed_path = self.get_themed_icon_path(icon_name, theme)
        if _path_exists(themed_path):
            return themed_path
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
        if not _path_exists(folder_icon):
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
        with self._index_lock:
            self._theme_index.clear()
            self._theme_index_ts.clear()
            self._theme_dir_mtime.clear()
            if hasattr(self, "_qrc_index"):
                self._qrc_index.clear()
        logger.debug("Icon path service caches cleared")

    # --- Metrics helpers (internal) ---

    def _maybe_log_metrics(self) -> None:
        """Safely attempt to log metrics while swallowing errors."""
        try:
            self._metrics.maybe_log_metrics(self._config)
        except Exception:
            logger.debug("Icon metrics logging failed", exc_info=True)

    # --- Index helpers ---

    def _get_theme_dir(self, theme: str) -> Pathish | None:
        if self._use_qrc_for_theme(theme):
            return PurePosixPath(f":/icons/{theme}")
        try:
            return self._get_icons_dir_for_theme(theme)
        except Exception:
            return None

    def _get_cache_root(self) -> Path:
        cache_root = self._get_user_data_dir() / "icon_cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        return cache_root

    def _get_qrc_index(self, theme: str) -> set[str]:
        if not self._use_qrc_for_theme(theme) or QDirIterator is None:
            return set()
        cached = self._qrc_index.get(theme)
        if cached is not None:
            return cached
        entries: set[str] = set()
        if QDir is not None:
            base = QDir(f":/icons/{theme}")
            if base.exists():
                iterator = QDirIterator(base, QDirIterator.IteratorFlag.Subdirectories)
                while iterator.hasNext():
                    entry_path = iterator.next()
                    if not entry_path:
                        continue
                    name = PurePosixPath(entry_path).name.lower()
                    if name:
                        entries.add(name)
        self._qrc_index[theme] = entries
        return entries

    def _prune_cache(self, theme: str) -> None:
        cache_root = self._get_cache_root()
        theme_dir = cache_root / theme
        if not theme_dir.exists():
            return
        ttl_seconds = float(getattr(app_config, "icon_cache_ttl_seconds", 3600.0) or 0)
        max_files = int(getattr(app_config, "icon_cache_max_files", 500) or 0)
        max_total_mb = float(getattr(app_config, "icon_cache_max_total_mb", 50.0) or 0)
        now = time.time()

        entries = self._collect_cache_entries(theme_dir, ttl_seconds, now)
        if not entries:
            self._remove_empty_theme_dir(theme_dir)
            return

        if max_files > 0 and len(entries) > max_files:
            entries = self._delete_oldest_over_max_files(entries, max_files)

        if max_total_mb > 0:
            self._enforce_total_size_limit(entries, max_total_mb)

        self._remove_empty_theme_dir(theme_dir)

    def _collect_cache_entries(
        self, theme_dir: Path, ttl_seconds: float, now: float
    ) -> list[tuple[float, Path, int]]:
        """Collect valid cache entries after TTL pruning."""
        entries: list[tuple[float, Path, int]] = []
        for candidate in theme_dir.glob('*.png'):
            try:
                stat = candidate.stat()
            except OSError:
                continue
            if ttl_seconds > 0 and now - stat.st_mtime > ttl_seconds:
                try:
                    candidate.unlink(missing_ok=True)
                except OSError:
                    pass
                continue
            entries.append((stat.st_mtime, candidate, stat.st_size))
        return entries

    def _delete_oldest_over_max_files(
        self, entries: list[tuple[float, Path, int]], max_files: int
    ) -> list[tuple[float, Path, int]]:
        """Delete oldest files to keep total count under max_files."""
        entries.sort(key=lambda item: item[0])
        excess = len(entries) - max_files
        if excess > 0:
            for _, candidate, _ in entries[:excess]:
                try:
                    candidate.unlink(missing_ok=True)
                except OSError:
                    pass
            return entries[excess:]
        return entries

    def _enforce_total_size_limit(
        self, entries: list[tuple[float, Path, int]], max_total_mb: float
    ) -> None:
        """Keep newest files under total size limit; delete the rest."""
        limit_bytes = max_total_mb * 1024 * 1024
        entries.sort(key=lambda item: item[0], reverse=True)
        current_size = 0
        kept: list[tuple[float, Path, int]] = []
        for entry in entries:
            if current_size + entry[2] <= limit_bytes:
                kept.append(entry)
                current_size += entry[2]
        if len(kept) != len(entries):
            protected = {entry[1] for entry in kept}
            for _, candidate, _ in entries:
                if candidate not in protected:
                    try:
                        candidate.unlink(missing_ok=True)
                    except OSError:
                        pass

    def _remove_empty_theme_dir(self, theme_dir: Path) -> None:
        """Remove theme cache directory if it is empty."""
        try:
            if not any(theme_dir.iterdir()):
                theme_dir.rmdir()
        except OSError:
            pass

    def _get_cached_png_path(self, icon_name: str, theme: str) -> Path:
        cache_dir = self._get_cache_root() / theme
        cache_dir.mkdir(parents=True, exist_ok=True)
        name = Path(icon_name).name
        if Path(name).suffix.lower() != ".png":
            name = f"{Path(name).stem}.png"
        return cache_dir / name

    def _should_refresh_index(self, theme: str, now: float) -> bool:
        if self._use_qrc_for_theme(theme):
            # Resources are immutable at runtime; rebuild only if absent
            return theme not in self._theme_index

        if theme not in self._theme_index:
            return True

        last_ts = self._theme_index_ts.get(theme, 0.0)
        if now - last_ts >= self._index_ttl:
            return True

        dir_path = self._get_theme_dir(theme)
        if dir_path is None:
            return True

        previous_mtime = self._theme_dir_mtime.get(theme)
        current_mtime = _safe_mtime(dir_path)
        return current_mtime != previous_mtime

    def _build_theme_index(self, theme: str) -> dict[str, Path]:
        if self._use_qrc_for_theme(theme):
            # Listing Qt resources requires QDir; rely on runtime lookups instead.
            return {}

        index: dict[str, Path] = {}
        dir_path = self._get_theme_dir(theme)
        if dir_path is None:
            return index

        dir_path = Path(str(dir_path))
        if not dir_path.is_dir():
            return index

        try:
            for entry in dir_path.iterdir():
                if not entry.is_file():
                    continue
                index[entry.name.lower()] = entry
        except OSError as exc:
            logger.debug("Failed to build icon index for theme %s: %s", theme, exc)
        return index

    def get_indexed_icon(self, theme: str, icon_name: str) -> Path | None:
        norm_theme = validate_theme(theme)
        now = time.time()
        # Check if refresh needed (fast, under lock)
        needs_refresh = False
        with self._index_lock:
            needs_refresh = self._should_refresh_index(norm_theme, now)
        # Build index outside lock (slow disk I/O)
        if needs_refresh:
            new_index = self._build_theme_index(norm_theme)
            dir_path = self._get_theme_dir(norm_theme)
            new_mtime = _safe_mtime(dir_path) if dir_path is not None else None
            # Update cache under lock (fast)
            with self._index_lock:
                # Double-check: another thread may have refreshed while we were building
                if self._should_refresh_index(norm_theme, now):
                    self._theme_index[norm_theme] = new_index
                    self._theme_index_ts[norm_theme] = now
                    self._theme_dir_mtime[norm_theme] = new_mtime
        with self._index_lock:
            index = self._theme_index.get(norm_theme, {})
            return index.get(icon_name.lower())


# --- Global instance and convenient proxy functions ---

_icon_path_service = IconPathService()


# --- Separation of responsibilities: Resolver for cache/search/conversion ---


class IconPathResolver:
    """Responsible for stages: cache/negative cache/metrics, search by theme indexes, SVG->PNG conversion.

    Methods:
    - resolve_from_cache: name validation, negative cache, hits/misses in path cache.
      Returns (path_or_none, terminal). If terminal=True - result is final.
    - find_source: fast search for icon files by theme indexes.
    - convert_svg: attempt to convert SVG to PNG within the current theme.
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
        use_qrc = self.service._use_qrc_for_theme(norm_theme)

        if use_qrc:
            theme_entries = self.service._get_qrc_index(norm_theme)
            if "." in icon_name:
                candidates = [icon_name.lower()]
            else:
                candidates = [f"{icon_name.lower()}.svg", f"{icon_name.lower()}.png"]
            for candidate in candidates:
                if candidate not in theme_entries:
                    continue
                themed_path = self.service.get_themed_icon_path(candidate, norm_theme)
                if _path_exists(themed_path):
                    path_str = str(themed_path)
                    set_path(icon_name, norm_theme, path_str)
                    metrics_record_hit()
                    self.service._maybe_log_metrics()
                    return path_str
            return None

        idx_hit = self.service.get_indexed_icon(norm_theme, icon_name)
        if idx_hit is not None and _path_exists(idx_hit):
            path_str = str(idx_hit)
            set_path(icon_name, norm_theme, path_str)
            metrics_record_disk_load()
            self.service._maybe_log_metrics()
            return path_str
        return None

    # --- Icon conversion ---
    def convert_svg(self, icon_name: str, theme: str) -> str | None:  # noqa: C901
        # Local import to avoid circular dependencies
        from .icon_operations.converters import convert_icon_to_png_128
        from PyQt6.QtWidgets import QApplication

        try:
            app = QApplication.instance()
            if app and app.closingDown():
                return None
        except Exception:
            pass

        norm_theme = validate_theme(theme)
        use_qrc = self.service._use_qrc_for_theme(norm_theme)

        if use_qrc:
            svg_resource = self.service.get_themed_icon_path(icon_name, norm_theme)
            if svg_resource.suffix.lower() != ".svg":
                svg_resource = svg_resource.with_suffix(".svg")

            if not _path_is_file(svg_resource):
                return None

            cached_png = self.service._get_cached_png_path(icon_name, norm_theme)
            if cached_png.exists():
                path_str = str(cached_png)
                set_path(icon_name, norm_theme, path_str)
                metrics_record_disk_load()
                self.service._maybe_log_metrics()
                return path_str

            data = _read_qrc_bytes(svg_resource)
            if not data:
                return None

            def _convert_resource() -> bool:
                tmp_svg = Path(tempfile.gettempdir()) / f"icon_{uuid.uuid4().hex}.svg"
                try:
                    tmp_svg.write_bytes(data)
                except OSError as exc:
                    logger.warning("Failed to materialize QRC SVG for %s: %s", icon_name, exc)
                    return False

                try:
                    start = time.perf_counter()
                    success_local = convert_icon_to_png_128(str(tmp_svg), str(cached_png))
                    duration_local = time.perf_counter() - start
                finally:
                    try:
                        tmp_svg.unlink()
                    except FileNotFoundError:
                        pass
                    except OSError as exc:
                        logger.debug("Could not remove temp SVG %s: %s", tmp_svg, exc)

                if success_local and cached_png.exists():
                    path_str_local = str(cached_png)
                    set_path(icon_name, norm_theme, path_str_local)
                    metrics_record_disk_load(duration_local)
                    self.service._maybe_log_metrics()
                    self.service._prune_cache(norm_theme)
                    return True

                logger.warning("Failed to convert QRC SVG %s to PNG", svg_resource)
                return False

            # Run directly in worker thread — set_path() is just a dict+lock,
            # no GUI thread required. Avoids blocking GUI with disk I/O.
            if _convert_resource():
                return str(cached_png)
            return None

        themed_path = Path(str(self.service.get_themed_icon_path(icon_name, norm_theme)))

        # themed.svg -> themed.png
        themed_svg = themed_path.with_suffix(".svg")
        if _path_is_file(themed_svg) and is_valid_icon_file(themed_svg):
            themed_png = themed_path.with_suffix(".png")
            if _path_is_file(themed_png):
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
            slow_ms = float(getattr(app_config, "icon_slow_convert_threshold_ms", 150.0))
            t0 = time.perf_counter()
            if convert_icon_to_png_128(str(themed_svg), str(themed_png)):
                dt_ms = (time.perf_counter() - t0) * 1000.0
                path_str = str(themed_png)
                set_path(icon_name, norm_theme, path_str)
                if dt_ms >= slow_ms:
                    logger.warning(
                        "Slow icon convert (%.1f ms): %s -> %s",
                        dt_ms,
                        themed_svg,
                        themed_png,
                    )
                else:
                    logger.debug(
                        "Converted SVG to PNG (%.1f ms): %s -> %s",
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
        return None


# --- Icon path search and caching ---


def get_icon_path(icon_name: str, theme: str = "light") -> str | None:
    """Get string path to icon. Thin wrapper around IconPathResolver."""
    return _get_icon_path_impl(icon_name, theme)


def _fallback_theme_for(current: str) -> str | None:
    """Return a fallback theme for the given theme, preferring 'light'."""
    if current == "light":
        return None
    try:
        from app.services.theme_registry import theme_registry
        if theme_registry.get_theme("light") is not None:
            return "light"
        fallback_local = theme_registry.get_default_theme_id()
        return fallback_local if fallback_local != current else None
    except Exception:
        return "light"


def _resolve_in_theme_local(
    resolver: IconPathResolver, icon_name: str, target_theme: str
) -> str | None:
    """Resolve icon path or convert SVG within a specific theme."""
    found_local = resolver.find_source(icon_name, target_theme)
    if found_local is not None:
        return found_local
    return resolver.convert_svg(icon_name, target_theme)


def _resolve_via_fallback(
    resolver: IconPathResolver, icon_name: str, norm_theme: str
) -> str | None:
    """Try to resolve in a fallback theme and update caches on success."""
    fb = _fallback_theme_for(norm_theme)
    if not fb:
        return None
    fb_path = _resolve_in_theme_local(resolver, icon_name, fb)
    if fb_path is not None:
        set_path(icon_name, norm_theme, fb_path)
        key_local = f"{norm_theme}:{icon_name.lower()}"
        try:
            negative_cache.invalidate(key_local)
        except Exception:
            pass
        return fb_path
    return None


def _cache_terminal_case(
    resolver: IconPathResolver, icon_name: str, theme: str, is_valid_name: bool
) -> tuple[str | None, bool]:
    """Handle terminal cache outcomes: hit or negative path with fallback."""
    cached_or_none, terminal = resolver.resolve_from_cache(icon_name, theme)
    if not terminal:
        return None, False
    if cached_or_none is not None:
        return cached_or_none, True
    if not is_valid_name:
        return None, True
    norm_theme = validate_theme(theme)
    fb_path = _resolve_via_fallback(resolver, icon_name, norm_theme)
    return fb_path, True


def _try_primary_sources(
    resolver: IconPathResolver, icon_name: str, theme: str
) -> str | None:
    """Try primary resolution in the requested theme (index, then SVG)."""
    found = resolver.find_source(icon_name, theme)
    if found is not None:
        return found
    converted = resolver.convert_svg(icon_name, theme)
    if converted is not None:
        return converted
    return None


def _try_secondary_fallback(
    resolver: IconPathResolver, icon_name: str, theme: str, is_valid_name: bool
) -> str | None:
    """Try resolving via fallback theme if icon name is valid."""
    if not is_valid_name:
        return None
    norm_theme = validate_theme(theme)
    return _resolve_via_fallback(resolver, icon_name, norm_theme)


def _commit_negative(icon_name: str, theme: str) -> None:
    """Commit negative cache entry and record metrics."""
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


def _get_icon_path_impl(icon_name: str, theme: str) -> str | None:
    """Resolve icon path with cache, theme search, conversion and fallbacks."""
    resolver = IconPathResolver(_icon_path_service)
    is_valid_name = _validate_icon_name(icon_name)

    value, done = _cache_terminal_case(resolver, icon_name, theme, is_valid_name)
    if done:
        return value
    value = _try_primary_sources(resolver, icon_name, theme)
    if value is not None:
        return value
    value = _try_secondary_fallback(resolver, icon_name, theme, is_valid_name)
    if value is not None:
        return value
    _commit_negative(icon_name, theme)
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

    fallback = "light"
    try:
        from app.services.theme_registry import theme_registry

        fallback = theme_registry.get_default_theme_id()
    except Exception:
        pass

    # Fallback: write default to cache under lock
    with _theme_lock:
        _CURRENT_THEME_CACHE = fallback
        _LAST_THEME_CHECK = now
    return fallback


# Global service export
icon_path_service = _icon_path_service


# --- Legacy global variables for backward compatibility ---

# Legacy global metrics instance (proxies to icon_path_service._metrics)
_ICON_METRICS = _icon_path_service._metrics

# Legacy global metrics logging function (proxies to icon_path_service._maybe_log_metrics)
def _maybe_log_metrics() -> None:
    """Log metrics if interval has passed (proxies to icon_path_service)."""
    _icon_path_service._maybe_log_metrics()


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











