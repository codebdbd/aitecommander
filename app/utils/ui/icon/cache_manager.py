"""Icon cache manager with standard API (paths, QIcon, LRU, TTL, metrics)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtGui import QIcon, QPixmap, QPixmapCache

from app.config_data import app_config

from .lock_manager import LockLevel, acquire_cache_lock, acquire_multiple_locks
from .lru_policy import LRUPolicy

logger = logging.getLogger(__name__)


class _FallbackCacheMetrics:
    """Simple metrics implementation if .metrics is unavailable."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.hits = 0
            self.misses = 0
            self.actual_misses = 0
            self.disk_loads = 0
            self.not_found = 0
            self.total_load_time = 0.0

    def record_hit(self) -> None:
        with self._lock:
            self.hits += 1

    def record_miss(self) -> None:
        with self._lock:
            self.misses += 1

    def record_actual_miss(self, load_time: float = 0.0) -> None:
        with self._lock:
            self.misses += 1
            self.actual_misses += 1
            self.total_load_time += float(load_time)

    def record_miss_without_increment(self, load_time: float = 0.0) -> None:
        with self._lock:
            self.total_load_time += float(load_time)

    def record_disk_load(self) -> None:
        with self._lock:
            self.disk_loads += 1

    def record_not_found(self) -> None:
        with self._lock:
            self.not_found += 1

    def get_stats(self) -> dict[str, int | float]:
        with self._lock:
            return {
                "hits": self.hits,
                "misses": self.misses,
                "actual_misses": self.actual_misses,
                "disk_loads": self.disk_loads,
                "not_found": self.not_found,
                "total_load_time": round(self.total_load_time, 6),
            }


try:
    from .metrics import CacheMetrics as _RuntimeCacheMetrics  # type: ignore
except Exception:  # noqa: BLE001
    _RuntimeCacheMetrics = None  # type: ignore[assignment, misc]

if TYPE_CHECKING:
    # For static typing: mypy will see the correct class
    from .metrics import CacheMetrics as CacheMetrics  # noqa: F401
else:
    if _RuntimeCacheMetrics is not None:
        CacheMetrics = _RuntimeCacheMetrics  # type: ignore[assignment]
    else:

        class CacheMetrics(_FallbackCacheMetrics):
            pass


# --- Cache entry types ---


def _is_entry_valid(timestamp: float, ttl_seconds: float | None) -> bool:
    """Checks entry validity by TTL."""
    if ttl_seconds is None:
        return True
    try:
        ttl = float(ttl_seconds)
    except Exception:  # noqa: BLE001
        return False
    if ttl <= 0:
        return False
    now = time.time()
    return (now - float(timestamp)) < ttl


@dataclass
class PathCacheEntry:
    """Cache entry for icon paths."""

    path: str | None
    timestamp: float
    ttl_override: float | None = None

    def is_valid(self, ttl_seconds: float | None) -> bool:
        return _is_entry_valid(self.timestamp, ttl_seconds)


@dataclass
class IconCacheEntry:
    """Cache entry for QIcon."""

    icon: QIcon | None
    timestamp: float
    negative: bool = False
    ttl_override: float | None = None

    def is_valid(self, ttl_seconds: float | None) -> bool:
        return _is_entry_valid(self.timestamp, ttl_seconds)


# --- Thread-safe cache ---


class ThreadSafeIconCache:
    """Thread-safe LRU cache for paths and QIcon."""

    def __init__(self, maxsize: int | None = None) -> None:
        capacity = (
            int(maxsize)
            if maxsize is not None
            else int(app_config.get_icon_cache_size())
        )
        if capacity <= 0:
            capacity = 1

        self._path_cache: dict[str, PathCacheEntry] = {}
        self._qicon_cache: dict[str, IconCacheEntry] = {}
        self._path_lru = LRUPolicy(capacity)
        self._qicon_lru = LRUPolicy(capacity)

        self.metrics: CacheMetrics = CacheMetrics()
        self._capacity = capacity

        # Cache TTL values and refresh them without holding locks
        object.__setattr__(self, "_ttl_lock", threading.RLock())
        object.__setattr__(self, "_suspend_ttl_override_tracking", False)
        object.__setattr__(self, "_ttl_icon_manual_override", False)
        object.__setattr__(self, "_ttl_abs_manual_override", False)
        object.__setattr__(self, "_ttl_negative_manual_override", False)
        object.__setattr__(self, "_ttl_icon", None)
        object.__setattr__(self, "_ttl_abs", None)
        object.__setattr__(self, "_ttl_negative", None)
        self._refresh_ttls_unlocked()

        # Initialize QPixmapCache with reasonable limit (in KB)
        # Qt's QPixmapCache is shared globally, so set a reasonable limit
        try:
            pixmap_cache_kb = int(getattr(app_config, "pixmap_cache_size_kb", 10240))
            QPixmapCache.setCacheLimit(pixmap_cache_kb)
            logger.debug("QPixmapCache limit set to %d KB", pixmap_cache_kb)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to set QPixmapCache limit: %s", exc)

    # --- keys ---

    @staticmethod
    def _key(icon_name: str, theme: str) -> str:
        return f"{icon_name}::{theme}"

    @staticmethod
    def _parse_unified_key(key: str) -> tuple[str, str, str]:
        """Parse a unified key in the format 'path:icon::theme' or 'qicon:icon::theme'.

        Returns a tuple (prefix, icon_name, theme). Raises ValueError on invalid format.
        """
        if ":" not in key:
            raise ValueError("Unified key must contain prefix 'path:' or 'qicon:'")
        prefix, rest = key.split(":", 1)
        if "::" not in rest:
            raise ValueError(
                "Unified key must be in form '<prefix>:<icon_name>::<theme>'"
            )
        icon_name, theme = rest.split("::", 1)
        if prefix not in {"path", "qicon"}:
            raise ValueError("Unsupported prefix, expected 'path' or 'qicon'")
        return prefix, icon_name, theme

    # --- utility for resynchronization ---

    def _sync_path_structs(self) -> None:
        self._path_lru.sync_with_cache(self._path_cache)

    def _sync_qicon_structs(self) -> None:
        self._qicon_lru.sync_with_cache(self._qicon_cache)

    # --- TTL update during monkeypatch ---

    def __setattr__(self, name, value):
        if name in {"_ttl_icon", "_ttl_abs", "_ttl_negative"}:
            if not getattr(self, "_suspend_ttl_override_tracking", False):
                object.__setattr__(
                    self,
                    f"{name}_manual_override",
                    True,
                )
        object.__setattr__(self, name, value)

    def reset_ttl_overrides(self) -> None:
        """Clears manual TTL overrides and reloads values from config."""
        with self._ttl_lock:
            object.__setattr__(self, "_ttl_icon_manual_override", False)
            object.__setattr__(self, "_ttl_abs_manual_override", False)
            object.__setattr__(self, "_ttl_negative_manual_override", False)
            self._refresh_ttls_unlocked()

    def _refresh_ttls_unlocked(
        self,
        refresh_icon: bool = True,
        refresh_abs: bool = True,
        refresh_negative: bool = True,
    ) -> None:
        """Refresh TTL values from config without holding cache lock."""
        object.__setattr__(self, "_suspend_ttl_override_tracking", True)
        try:
            if refresh_icon and not self._ttl_icon_manual_override:
                try:
                    value = app_config.get_icon_cache_ttl()
                except Exception:  # noqa: BLE001
                    value = None
                object.__setattr__(self, "_ttl_icon", value)
            if refresh_abs and not self._ttl_abs_manual_override:
                try:
                    value = app_config.get_abs_icon_cache_ttl()
                except Exception:  # noqa: BLE001
                    value = None
                object.__setattr__(self, "_ttl_abs", value)
            if refresh_negative and not self._ttl_negative_manual_override:
                try:
                    value = app_config.get_negative_cache_ttl()
                except Exception:  # noqa: BLE001
                    value = None
                object.__setattr__(self, "_ttl_negative", value)
        finally:
            object.__setattr__(self, "_suspend_ttl_override_tracking", False)

    def _ensure_fresh_ttls(self) -> None:
        """Updates cached TTLs when getters change in app_config.

        This method checks if config getters changed and refreshes TTLs
        WITHOUT holding the cache lock to avoid contention.
        """
        refresh_icon = not self._ttl_icon_manual_override
        refresh_abs = not self._ttl_abs_manual_override
        refresh_negative = not self._ttl_negative_manual_override
        if not any((refresh_icon, refresh_abs, refresh_negative)):
            return
        try:
            with self._ttl_lock:
                self._refresh_ttls_unlocked(
                    refresh_icon, refresh_abs, refresh_negative
                )
        except Exception as exc:
            logger.debug(
                "IconCache: TTL refresh failed, using previous values: %s",
                exc,
                exc_info=True,
            )

    def _get_ttls_snapshot(self) -> tuple[float | None, float | None, float | None]:
        """Get a thread-safe snapshot of current TTL values."""
        with self._ttl_lock:
            return self._ttl_icon, self._ttl_abs, self._ttl_negative

    # --- PATH API ---

    def get_path(self, icon_name: str, theme: str) -> str | None:
        """Returns the path to an icon from the path cache."""
        # Refresh TTLs outside cache lock to reduce contention
        self._ensure_fresh_ttls()
        ttl_icon, _, _ = self._get_ttls_snapshot()

        with acquire_cache_lock():
            self._sync_path_structs()
            key = self._key(icon_name, theme)
            entry = self._path_cache.get(key)
            if entry is None:
                try:
                    self.metrics.record_miss()
                except Exception as exc:  # noqa: BLE001
                    logger.debug(
                        "IconCache.metrics.record_miss failed: %s", exc, exc_info=True
                    )
                return None

            # Personal TTL takes precedence over global TTL for paths
            ttl = entry.ttl_override if entry.ttl_override is not None else ttl_icon
            if not entry.is_valid(ttl):
                self._path_cache.pop(key, None)
                self._path_lru.remove(key)
                try:
                    self.metrics.record_miss()
                except Exception:  # noqa: BLE001
                    pass
                return None

            try:
                self.metrics.record_hit()
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "IconCache.metrics.record_hit failed: %s", exc, exc_info=True
                )
            return entry.path

    def set_path(self, icon_name: str, theme: str, path: str | None) -> None:
        """Stores the path to an icon in the path cache."""
        with acquire_cache_lock():
            self._sync_path_structs()
            key = self._key(icon_name, theme)

            should_evict, old_key = self._path_lru.evict_if_needed(
                self._path_cache, key
            )
            if should_evict and old_key:
                self._path_cache.pop(old_key, None)

            entry = PathCacheEntry(path=path, timestamp=time.time(), ttl_override=None)
            self._path_cache[key] = entry
            self._path_lru.access(key)
            logger.debug("Set PATH: %s", key)

    # --- QICON API ---

    def get_qicon(self, icon_name: str, theme: str) -> QIcon | None:
        """Returns QIcon from the icon cache."""
        # Refresh TTLs outside cache lock to reduce contention
        self._ensure_fresh_ttls()
        ttl_icon, ttl_abs, ttl_negative = self._get_ttls_snapshot()

        with acquire_cache_lock():
            self._sync_qicon_structs()
            key = self._key(icon_name, theme)
            entry = self._qicon_cache.get(key)
            if entry is None:
                try:
                    self.metrics.record_miss()
                except Exception:  # noqa: BLE001
                    pass
                return None

            # Base TTL by entry type, then per-entry override priority
            if entry.negative:
                base_ttl = ttl_negative
            else:
                base_ttl = ttl_abs if theme == "__abs__" else ttl_icon
            ttl = entry.ttl_override if entry.ttl_override is not None else base_ttl
            if not entry.is_valid(ttl):
                self._qicon_cache.pop(key, None)
                self._qicon_lru.remove(key)
                try:
                    self.metrics.record_miss()
                except Exception:  # noqa: BLE001
                    pass
                return None

            try:
                self.metrics.record_hit()
            except Exception:  # noqa: BLE001
                pass
            return entry.icon

    def set_qicon(
        self,
        icon_name: str,
        theme: str,
        icon: QIcon | None = None,
        *,
        negative: bool = False,
    ) -> None:
        """Stores QIcon in the icon cache."""
        with acquire_cache_lock():
            self._sync_qicon_structs()
            key = self._key(icon_name, theme)
            should_evict, old_key = self._qicon_lru.evict_if_needed(
                self._qicon_cache, key
            )
            if should_evict and old_key:
                self._qicon_cache.pop(old_key, None)
                # Also remove from QPixmapCache
                self._remove_from_qpixmapcache(old_key)

            entry = IconCacheEntry(
                icon=icon, timestamp=time.time(), negative=negative, ttl_override=None
            )
            self._qicon_cache[key] = entry
            self._qicon_lru.access(key)

            # Store pixmap in Qt's QPixmapCache for better integration
            if icon is not None and not icon.isNull() and not negative:
                self._store_in_qpixmapcache(key, icon)

            logger.debug("Set QICON: %s", key)

    # --- BaseCache-compatible API (unified keys) ---

    def get(self, key: str) -> str | QIcon | None:  # noqa: C901
        """Returns the value by key 'path:...'/ 'qicon:...'."""
        # Refresh TTLs outside cache lock to reduce contention
        self._ensure_fresh_ttls()
        ttl_icon, ttl_abs, ttl_negative = self._get_ttls_snapshot()

        with acquire_cache_lock():
            prefix, icon_name, theme = self._parse_unified_key(key)
            k = self._key(icon_name, theme)
            if prefix == "path":
                self._sync_path_structs()
                entry = self._path_cache.get(k)
                if entry is None:
                    try:
                        self.metrics.record_miss()
                    except Exception as exc:  # noqa: BLE001
                        logger.debug(
                            "IconCache.metrics.record_miss failed: %s",
                            exc,
                            exc_info=True,
                        )
                    return None
                ttl = entry.ttl_override if entry.ttl_override is not None else ttl_icon
                if not entry.is_valid(ttl):
                    self._path_cache.pop(k, None)
                    self._path_lru.remove(k)
                    try:
                        self.metrics.record_miss()
                    except Exception:  # noqa: BLE001
                        pass
                    return None
                self._path_lru.access(k)
                try:
                    self.metrics.record_hit()
                except Exception as exc:  # noqa: BLE001
                    logger.debug(
                        "IconCache.metrics.record_hit failed: %s", exc, exc_info=True
                    )
                return entry.path
            else:  # qicon
                self._sync_qicon_structs()
                qicon_entry: IconCacheEntry | None = self._qicon_cache.get(k)
                if qicon_entry is None:
                    try:
                        self.metrics.record_miss()
                    except Exception:  # noqa: BLE001
                        pass
                    return None
                if qicon_entry.negative:
                    base_ttl = ttl_negative
                else:
                    base_ttl = ttl_abs if theme == "__abs__" else ttl_icon
                ttl = (
                    qicon_entry.ttl_override
                    if qicon_entry.ttl_override is not None
                    else base_ttl
                )
                if not qicon_entry.is_valid(ttl):
                    self._qicon_cache.pop(k, None)
                    self._qicon_lru.remove(k)
                    try:
                        self.metrics.record_miss()
                    except Exception:  # noqa: BLE001
                        pass
                    return None
                self._qicon_lru.access(k)
                try:
                    self.metrics.record_hit()
                except Exception as exc:  # noqa: BLE001
                    logger.debug(
                        "IconCache.metrics.record_hit failed: %s", exc, exc_info=True
                    )
                return qicon_entry.icon

    def set(
        self,
        key: str,
        value: str | QIcon | None,
        *,
        ttl: float | None = None,
    ) -> None:
        """Sets the value by key (for qicon, None means a negative entry)."""
        prefix, icon_name, theme = self._parse_unified_key(key)
        with acquire_cache_lock():
            if prefix == "path":
                self._sync_path_structs()
                k = self._key(icon_name, theme)
                should_evict, old_key = self._path_lru.evict_if_needed(
                    self._path_cache, k
                )
                if should_evict and old_key:
                    self._path_cache.pop(old_key, None)
                path_entry = PathCacheEntry(
                    path=value if isinstance(value, (str, type(None))) else None,
                    timestamp=time.time(),
                    ttl_override=ttl,
                )
                self._path_cache[k] = path_entry
                self._path_lru.access(k)
            else:
                self._sync_qicon_structs()
                k = self._key(icon_name, theme)
                should_evict, old_key = self._qicon_lru.evict_if_needed(
                    self._qicon_cache, k
                )
                if should_evict and old_key:
                    self._qicon_cache.pop(old_key, None)
                negative = value is None
                icon_val: QIcon | None = value if isinstance(value, QIcon) else None
                icon_entry = IconCacheEntry(
                    icon=icon_val,
                    timestamp=time.time(),
                    negative=negative,
                    ttl_override=ttl,
                )
                self._qicon_cache[k] = icon_entry
                self._qicon_lru.access(k)

    def invalidate(self, key: str | None = None) -> None:
        """Invalidates an entry by key or the entire cache when key=None."""
        with acquire_cache_lock():
            if key is None:
                # Complete cleanup without recreating LRU and metrics
                self._path_cache.clear()
                self._qicon_cache.clear()
                self._path_lru.sync_with_cache(self._path_cache)
                self._qicon_lru.sync_with_cache(self._qicon_cache)
                return
            try:
                prefix, icon_name, theme = self._parse_unified_key(key)
            except ValueError:
                self._path_cache.pop(key, None)
                self._qicon_cache.pop(key, None)
                self._path_lru.remove(key)
                self._qicon_lru.remove(key)
                return
            k = self._key(icon_name, theme)
            if prefix == "path":
                self._path_cache.pop(k, None)
                self._path_lru.remove(k)
            else:
                self._qicon_cache.pop(k, None)
                self._qicon_lru.remove(k)

    def _store_in_qpixmapcache(self, key: str, icon: QIcon) -> None:
        """Store icon's pixmap in Qt's QPixmapCache for better integration."""
        try:
            # Get the first available pixmap from the icon
            sizes = icon.availableSizes()
            if sizes:
                pixmap = icon.pixmap(sizes[0])
                if not pixmap.isNull():
                    # Use our cache key for QPixmapCache
                    QPixmapCache.insert(f"icon:{key}", pixmap)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to store pixmap in QPixmapCache for %s: %s", key, exc)

    def _remove_from_qpixmapcache(self, key: str) -> None:
        """Remove pixmap from Qt's QPixmapCache."""
        try:
            QPixmapCache.remove(f"icon:{key}")
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Failed to remove pixmap from QPixmapCache for %s: %s", key, exc
            )

    def _get_from_qpixmapcache(self, key: str) -> QPixmap | None:
        """Try to retrieve pixmap from Qt's QPixmapCache."""
        try:
            pixmap = QPixmapCache.find(f"icon:{key}")
            return pixmap if pixmap and not pixmap.isNull() else None
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to get pixmap from QPixmapCache for %s: %s", key, exc)
            return None

    def clear(self) -> None:
        """Complete cache and metrics cleanup."""
        with acquire_multiple_locks(LockLevel.CACHE, LockLevel.METRICS):
            self._path_cache.clear()
            self._qicon_cache.clear()
            # Clear Qt's pixmap cache for our icons
            QPixmapCache.clear()
            try:
                new_capacity = int(app_config.get_icon_cache_size())
            except Exception:  # noqa: BLE001
                new_capacity = self._capacity
            if new_capacity <= 0:
                new_capacity = 1
            self._capacity = new_capacity
            self._path_lru = LRUPolicy(self._capacity)
            self._qicon_lru = LRUPolicy(self._capacity)
            self.metrics.reset()
            with self._ttl_lock:
                self._refresh_ttls_unlocked()

    def get_cache_stats(self) -> dict[str, int | float]:
        """Aggregated cache and metrics statistics."""
        with acquire_multiple_locks(LockLevel.CACHE, LockLevel.METRICS):
            base = self.metrics.get_stats()
            more = {
                "path_cache_size": len(self._path_cache),
                "qicon_cache_size": len(self._qicon_cache),
                "max_cache_size": self._capacity,
                "path_cache_usage_percent": round(
                    len(self._path_cache) / self._capacity * 100, 2
                ),
                "qicon_cache_usage_percent": round(
                    len(self._qicon_cache) / self._capacity * 100, 2
                ),
            }
            return {**base, **more}


# --- Manager (Singleton) ---


class IconManager:
    """Manager for icon caching.
    
    Supports both singleton pattern (for backward compatibility) and dependency injection.
    
    Args:
        cache: Optional ThreadSafeIconCache instance. If None, creates default.
        capacity: Optional cache capacity (maxsize). Only used if cache is None.
    """

    _instance: IconManager | None = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs) -> IconManager:
        # If called without arguments, return singleton
        if not args and not kwargs:
            if cls._instance is None:
                with cls._lock:
                    if cls._instance is None:
                        cls._instance = super().__new__(cls)
                        cls._instance._initialized = False
            return cls._instance
        # If called with arguments, create new instance (DI mode)
        return super().__new__(cls)

    def __init__(
        self,
        cache: ThreadSafeIconCache | None = None,
        capacity: int | None = None,
    ) -> None:
        if getattr(self, "_initialized", False):
            return
        
        if cache is not None:
            self._cache = cache
        else:
            # Create cache with optional capacity (maxsize parameter)
            if capacity is not None:
                self._cache = ThreadSafeIconCache(maxsize=capacity)
            else:
                self._cache = ThreadSafeIconCache()
        
        self._initialized = True

    # Unified API (compatible with BaseCache)
    def get(self, key: str) -> str | QIcon | None:
        return self._cache.get(key)

    def set(
        self,
        key: str,
        value: str | QIcon | None,
        *,
        ttl: float | None = None,
    ) -> None:
        self._cache.set(key, value, ttl=ttl)

    def invalidate(self, key: str | None = None) -> None:
        self._cache.invalidate(key)

    # PATH (new standardized names)
    def get_path(self, icon_name: str, theme: str) -> str | None:
        return self._cache.get_path(icon_name, theme)

    def set_path(self, icon_name: str, theme: str, path: str | None) -> None:
        self._cache.set_path(icon_name, theme, path)

    # QICON (new standardized names)
    def get_icon(self, icon_name: str, theme: str) -> QIcon | None:
        return self._cache.get_qicon(icon_name, theme)

    def set_icon(
        self,
        icon_name: str,
        theme: str,
        icon: QIcon | None,
        *,
        negative: bool = False,
    ) -> None:
        self._cache.set_qicon(icon_name, theme, icon, negative=negative)

    # Admin
    def clear_cache(self) -> None:
        self._cache.clear()

    def get_cache_stats(self) -> dict[str, int | float]:
        return self._cache.get_cache_stats()

    # Metrics (without direct access to internal locks)
    def record_miss_without_increment(self, load_time: float = 0.0) -> None:
        self._cache.metrics.record_miss_without_increment(load_time)

    def record_actual_miss(self, load_time: float = 0.0) -> None:
        self._cache.metrics.record_actual_miss(load_time)

    def record_disk_load(self) -> None:
        self._cache.metrics.record_disk_load()

    def record_not_found(self) -> None:
        self._cache.metrics.record_not_found()


_icon_manager = IconManager()


def clear_icon_cache() -> None:
    """Clears the icon cache."""
    _icon_manager.clear_cache()


def get_icon_cache_stats() -> dict[str, int | float]:
    """Returns cache statistics."""
    return _icon_manager.get_cache_stats()


def reset_icon_cache_stats() -> None:
    """Resets metrics."""
    _icon_manager._cache.metrics.reset()


def log_icon_cache_stats() -> None:
    """Logs cache statistics."""
    logger.info("Icon Cache Stats: %s", get_icon_cache_stats())


def record_miss_without_increment(load_time: float = 0.0) -> None:
    _icon_manager.record_miss_without_increment(load_time)


def record_actual_miss(load_time: float = 0.0) -> None:
    _icon_manager.record_actual_miss(load_time)


def record_disk_load() -> None:
    _icon_manager.record_disk_load()


def record_not_found() -> None:
    _icon_manager.record_not_found()


def get_icon(icon_name: str, theme: str) -> QIcon | None:
    return _icon_manager.get_icon(icon_name, theme)


def set_icon(
    icon_name: str,
    theme: str,
    icon: QIcon | None,
    *,
    negative: bool = False,
) -> None:
    _icon_manager.set_icon(icon_name, theme, icon, negative=negative)


def get_path(icon_name: str, theme: str) -> str | None:
    return _icon_manager.get_path(icon_name, theme)


def set_path(icon_name: str, theme: str, path: str | None) -> None:
    _icon_manager.set_path(icon_name, theme, path)


def get(key: str) -> str | QIcon | None:
    return _icon_manager.get(key)


def set(key: str, value: str | QIcon | None, *, ttl: float | None = None) -> None:
    _icon_manager.set(key, value, ttl=ttl)


def invalidate(key: str | None = None) -> None:
    _icon_manager.invalidate(key)


def clear() -> None:
    clear_icon_cache()


def get_cached_category_icon(path: str) -> QIcon:
    """Get a cached category icon from the general cache without dependencies on icon_operations.
    
    Note:
        Must be called from GUI thread as it creates QIcon.
        Returns empty QIcon if called from non-GUI thread.
    """
    # ✅ FIX: Thread safety check BEFORE any QIcon creation
    from PyQt6.QtCore import QThread
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication.instance()
    current_thread = QThread.currentThread() if app else None
    gui_thread = app.thread() if app else None
    
    # Check thread affinity BEFORE creating any Qt objects
    if not app or not current_thread or not gui_thread or current_thread != gui_thread:
        logger.warning(
            "get_cached_category_icon called from non-GUI thread for %s, returning empty icon",
            path
        )
        # Create empty QIcon in a thread-safe way - this is safe even in wrong thread
        # because QIcon() without arguments doesn't load resources
        try:
            return QIcon()
        except Exception as exc:
            logger.error("Failed to create empty QIcon: %s", exc)
            # Last resort: return None and let caller handle it
            return QIcon()  # type: ignore[return-value]
    
    cache_key = f"category::{path}"
    cached_icon = _icon_manager.get_icon(cache_key, "__category__")
    if cached_icon is not None:
        return cached_icon

    # ✅ Safe to create QIcon here - we verified GUI thread above
    try:
        icon = QIcon(str(path)) if Path(path).exists() else QIcon()
    except Exception as exc:
        logger.warning("Failed to create QIcon from path %s: %s", path, exc)
        icon = QIcon()

    _icon_manager.set_icon(cache_key, "__category__", icon)
    return icon
