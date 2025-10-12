"""Icon cache manager with standard API (paths, QIcon, LRU, TTL, metrics)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtGui import QIcon

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
    _RuntimeCacheMetrics = None  # type: ignore[assignment]

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

        try:
            self._ttl_icon: float | None = app_config.get_icon_cache_ttl()
        except Exception:  # noqa: BLE001
            self._ttl_icon = None
        try:
            self._ttl_abs: float | None = app_config.get_abs_icon_cache_ttl()
        except Exception:  # noqa: BLE001
            self._ttl_abs = None
        try:
            self._ttl_negative: float | None = app_config.get_negative_cache_ttl()
        except Exception:  # noqa: BLE001
            self._ttl_negative = None

        self._getter_icon = getattr(app_config, "get_icon_cache_ttl", None)
        self._getter_abs = getattr(app_config, "get_abs_icon_cache_ttl", None)
        self._getter_negative = getattr(app_config, "get_negative_cache_ttl", None)

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

    def _ensure_fresh_ttls(self) -> None:
        """Updates cached TTLs when getters change in app_config."""
        try:
            if getattr(app_config, "get_icon_cache_ttl", None) is not self._getter_icon:
                self._getter_icon = getattr(app_config, "get_icon_cache_ttl", None)
                try:
                    self._ttl_icon = app_config.get_icon_cache_ttl()
                except Exception:  # noqa: BLE001
                    self._ttl_icon = None
            if (
                getattr(app_config, "get_abs_icon_cache_ttl", None)
                is not self._getter_abs
            ):
                self._getter_abs = getattr(app_config, "get_abs_icon_cache_ttl", None)
                try:
                    self._ttl_abs = app_config.get_abs_icon_cache_ttl()
                except Exception:  # noqa: BLE001
                    self._ttl_abs = None
            if (
                getattr(app_config, "get_negative_cache_ttl", None)
                is not self._getter_negative
            ):
                self._getter_negative = getattr(
                    app_config, "get_negative_cache_ttl", None
                )
                try:
                    self._ttl_negative = app_config.get_negative_cache_ttl()
                except Exception:  # noqa: BLE001
                    self._ttl_negative = None
        except Exception as exc:
            # Never interfere with the main execution path due to configuration errors
            logger.debug(
                "IconCache: TTL refresh failed, using previous values: %s",
                exc,
                exc_info=True,
            )

    # --- PATH API ---

    def get_path(self, icon_name: str, theme: str) -> str | None:
        """Returns the path to an icon from the path cache."""
        with acquire_cache_lock():
            self._ensure_fresh_ttls()
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
            ttl = (
                entry.ttl_override if entry.ttl_override is not None else self._ttl_icon
            )
            if not entry.is_valid(ttl):
                self._path_cache.pop(key, None)
                self._path_lru.remove(key)
                try:
                    self.metrics.record_miss()
                except Exception:  # noqa: BLE001
                    pass
                return None

            self._path_lru.access(key)
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
        with acquire_cache_lock():
            self._ensure_fresh_ttls()
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
                base_ttl = self._ttl_negative
            else:
                base_ttl = self._ttl_abs if theme == "__abs__" else self._ttl_icon
            ttl = entry.ttl_override if entry.ttl_override is not None else base_ttl
            if not entry.is_valid(ttl):
                self._qicon_cache.pop(key, None)
                self._qicon_lru.remove(key)
                try:
                    self.metrics.record_miss()
                except Exception:  # noqa: BLE001
                    pass
                return None

            self._qicon_lru.access(key)
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

            entry = IconCacheEntry(
                icon=icon, timestamp=time.time(), negative=negative, ttl_override=None
            )
            self._qicon_cache[key] = entry
            self._qicon_lru.access(key)
            logger.debug("Set QICON: %s", key)

    # --- BaseCache-compatible API (unified keys) ---

    def get(self, key: str) -> str | QIcon | None:  # noqa: C901
        """Returns the value by key 'path:...'/ 'qicon:...'."""
        with acquire_cache_lock():
            self._ensure_fresh_ttls()
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
                ttl = (
                    entry.ttl_override
                    if entry.ttl_override is not None
                    else self._ttl_icon
                )
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
                entry = self._qicon_cache.get(k)
                if entry is None:
                    try:
                        self.metrics.record_miss()
                    except Exception:  # noqa: BLE001
                        pass
                    return None
                if entry.negative:
                    base_ttl = self._ttl_negative
                else:
                    base_ttl = self._ttl_abs if theme == "__abs__" else self._ttl_icon
                ttl = entry.ttl_override if entry.ttl_override is not None else base_ttl
                if not entry.is_valid(ttl):
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
                return entry.icon

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
                entry = PathCacheEntry(
                    path=value if isinstance(value, (str, type(None))) else None,
                    timestamp=time.time(),
                    ttl_override=ttl,
                )
                self._path_cache[k] = entry
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
                entry = IconCacheEntry(
                    icon=icon_val,
                    timestamp=time.time(),
                    negative=negative,
                    ttl_override=ttl,
                )
                self._qicon_cache[k] = entry
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

    def clear(self) -> None:
        """Complete cache and metrics cleanup."""
        with acquire_multiple_locks(LockLevel.CACHE, LockLevel.METRICS):
            self._path_cache.clear()
            self._qicon_cache.clear()
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
            try:
                self._ttl_icon = app_config.get_icon_cache_ttl()
            except Exception:  # noqa: BLE001
                self._ttl_icon = None
            try:
                self._ttl_abs = app_config.get_abs_icon_cache_ttl()
            except Exception:  # noqa: BLE001
                self._ttl_abs = None
            try:
                self._ttl_negative = app_config.get_negative_cache_ttl()
            except Exception:  # noqa: BLE001
                self._ttl_negative = None
            self._getter_icon = getattr(app_config, "get_icon_cache_ttl", None)
            self._getter_abs = getattr(app_config, "get_abs_icon_cache_ttl", None)
            self._getter_negative = getattr(app_config, "get_negative_cache_ttl", None)

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
    """Singleton wrapper over ThreadSafeIconCache."""

    _instance: IconManager | None = None
    _lock = threading.Lock()

    def __new__(cls) -> IconManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, cache: ThreadSafeIconCache | None = None) -> None:
        if getattr(self, "_initialized", False):
            return
        self._cache = cache if cache is not None else ThreadSafeIconCache()
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
    """Get a cached category icon from the general cache without dependencies on icon_operations."""
    cache_key = f"category::{path}"
    cached_icon = _icon_manager.get_icon(cache_key, "__category__")
    if cached_icon is not None:
        return cached_icon

    # Create QIcon directly by path, without calling create_icon_from_path, to avoid import cycles
    icon = QIcon(str(path)) if Path(path).exists() else QIcon()

    _icon_manager.set_icon(cache_key, "__category__", icon)
    return icon
