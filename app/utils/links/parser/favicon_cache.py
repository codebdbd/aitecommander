"""File-backed favicon cache with TTL support and file locking.

Uses ``shelve`` for storage; locking relies on a ``.lock`` file next to the DB.
Data-compatible with the legacy version (keys = URL, values = dict with icon/title/etc.).
"""

from __future__ import annotations

import atexit
import os
import shelve
import threading
import time
from collections import OrderedDict
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

from app.config_data import app_config
from app.utils.cache.base import BaseCache
from app.utils.ui.icon.path_service import icon_path_service

from .constants import CACHE_TTL, SHORT_NEGATIVE_TTL, logger

# Optionally use ``resolve_icon_for_link`` to determine negative TTL, same as before
try:  # noqa: SIM105
    from app.utils.ui.icon.icon_resolver import resolve_icon_for_link  # type: ignore
except Exception:  # noqa: BLE001
    resolve_icon_for_link = None  # type: ignore


def _get_lock_backend() -> str:
    """Returns desired lock backend from config: 'auto'|'portalocker'|'filelock'|'fallback'."""
    try:
        v = getattr(app_config, "FAVICON_LOCK_BACKEND", "auto")
        if not isinstance(v, str):
            return "auto"
        v = v.lower().strip()
        if v in {"auto", "portalocker", "filelock"}:
            return v
    except Exception:  # noqa: BLE001
        pass
    return "auto"


@contextmanager
def _file_lock(lock_path: str, *, timeout: float = 5.0, _poll_interval: float = 0.05):
    """Cross-platform file lock without busy waiting.

    Backend order:
    1) ``portalocker.Lock(..., timeout=timeout)``
    2) ``filelock.FileLock(...).acquire(timeout=timeout)``
    If none of the backends are available, continue without interprocess locking (log a warning).

    Semantics preserved: when timeout expires, log a warning and continue without an actual lock.
    Timeout can be configured via ``app_config.FAVICON_LOCK_TIMEOUT`` (seconds). The function argument
    ``timeout`` takes precedence over config.
    """
    backend = _get_lock_backend()
    # Effective timeout: function argument overrides config value
    try:
        cfg_timeout = getattr(app_config, "FAVICON_LOCK_TIMEOUT", timeout)
        eff_timeout = float(timeout if timeout is not None else cfg_timeout)
        if eff_timeout < 0:
            eff_timeout = 0.0
    except Exception:
        eff_timeout = timeout

    # 1) portalocker (if available and allowed)
    if backend in ("auto", "portalocker"):
        try:
            import portalocker  # type: ignore

            # Blocking attempt with internal timeout — use context manager
            try:
                with portalocker.Lock(lock_path, timeout=max(0.0, float(eff_timeout))):
                    yield
                return
            except Exception as e:
                # portalocker raises LockException on timeout; log as warning
                try:
                    from portalocker import exceptions as _pl_exc  # type: ignore

                    if isinstance(e, getattr(_pl_exc, "LockException", tuple())):
                        logger.warning("favicon lock timeout: %s (%s)", lock_path, e)
                        yield
                        return
                except Exception:
                    pass
                logger.debug("portalocker lock error: %s", e, exc_info=True)
                # Fall through to the next backend
        except Exception:
            if backend == "portalocker":
                # Selected backend unavailable — proceed without locking
                logger.warning(
                    "favicon lock backend unavailable; proceeding without interprocess lock: %s",
                    lock_path,
                )
                yield
                return
            # auto: continue to filelock

    # 2) filelock (if available/allowed; also for auto when portalocker is missing)
    if backend in ("auto", "filelock"):
        try:
            from filelock import FileLock  # type: ignore
            from filelock import Timeout as FileLockTimeout

            lock = FileLock(lock_path)
            try:
                lock.acquire(timeout=max(0.0, float(eff_timeout)))
                try:
                    yield
                finally:
                    try:
                        lock.release()
                    except Exception:
                        pass
                return
            except FileLockTimeout as e:
                logger.warning("favicon lock timeout(filelock): %s (%s)", lock_path, e)
                yield
                return
            except Exception as e:
                logger.debug("filelock error: %s", e, exc_info=True)
                # Do not abort — fall back
        except Exception:
            if backend == "filelock":
                # Selected backend unavailable — proceed without locking
                logger.warning(
                    "favicon lock backend unavailable; proceeding without interprocess lock: %s",
                    lock_path,
                )
                yield
                return

    # No available backends — continue without interprocess locking
    logger.warning(
        "favicon lock backend unavailable; proceeding without interprocess lock: %s",
        lock_path,
    )
    yield


def _db_path() -> str:
    return str(icon_path_service.get_user_icons_dir() / "favicon_cache.db")


class FaviconCache(BaseCache):
    def __init__(self, *, default_ttl: float | None = CACHE_TTL) -> None:
        self._default_ttl = default_ttl
        self._lock = threading.RLock()
        # Cache default icon lookup to avoid repeated resolver calls
        self._default_icon_cached: str | None = None
        # Cleanup parameters (interval fixed, max_size read dynamically from config)
        self._cleanup_interval_sec = self._get_cleanup_interval()
        # Persistent shelve connection (enabled via configuration)
        self._db_path_str: str | None = None
        self._db: shelve.Shelf | None = None
        try:
            self._persistent_enabled: bool = bool(
                getattr(app_config, "FAVICON_CACHE_PERSISTENT", False)
            )
        except Exception:
            self._persistent_enabled = False
        try:
            atexit.register(self._safe_shutdown)
        except Exception:
            pass

    # Shelve handling
    def _get_db_path(self) -> str:
        # Always compute path from current icon_path_service (important for tests/dynamic usage)
        return str(icon_path_service.get_user_icons_dir() / "favicon_cache.db")

    def _open_db(self) -> None:
        current_path = self._get_db_path()
        # If path changed, close and reopen
        if self._db_path_str and self._db_path_str != current_path:
            self._close_db()
        if self._db is None:
            try:
                # Ensure directory exists before opening
                try:
                    icon_path_service.ensure_user_icons_dir()
                except Exception:
                    pass
                self._db = shelve.open(current_path)
                self._db_path_str = current_path
            except Exception as exc:  # noqa: BLE001
                self._db = None
                self._db_path_str = current_path
                logger.debug("favicon_cache: failed to open db: %s", exc, exc_info=True)

    def _close_db(self) -> None:
        db = self._db
        self._db = None
        if db is not None:
            try:
                db.close()
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "favicon_cache: failed to close db: %s", exc, exc_info=True
                )

    def _safe_shutdown(self) -> None:  # pragma: no cover - atexit path
        try:
            self._close_db()
        except Exception:
            pass

    # Helpers
    def _get_default_icon(self) -> str:
        if self._default_icon_cached is not None:
            return self._default_icon_cached
        if resolve_icon_for_link is None:
            self._default_icon_cached = ""
            return self._default_icon_cached
        try:
            self._default_icon_cached = (
                resolve_icon_for_link({"type": "web", "icon_path": ""}) or ""
            )
        except Exception:  # noqa: BLE001
            self._default_icon_cached = ""
        return self._default_icon_cached

    def _compute_effective_ttl(self, item: dict[str, Any]) -> float:
        # Compatibility with legacy logic: missing "ttl" and default icon => short negative TTL
        if "ttl" not in item and item.get("icon", "") == self._get_default_icon():
            return float(SHORT_NEGATIVE_TTL)
        return float(item.get("ttl", self._default_ttl or CACHE_TTL))

    # --- Configuration & cleanup ---
    @staticmethod
    def _get_max_size() -> int:
        """Maximum cache DB size (>=1).

        Attempt to read from `app_config` via `get_favicon_cache_max_size()` or attribute `favicon_cache_max_size`.
        Defaults to 5000.
        """
        default = 5000
        try:
            getter = getattr(app_config, "get_favicon_cache_max_size", None)
            if callable(getter):
                return max(1, int(getter()))
            raw = getattr(app_config, "favicon_cache_max_size", default)
            return max(1, int(raw))
        except Exception:  # noqa: BLE001
            return default

    @staticmethod
    def _get_cleanup_interval() -> float:
        """Periodic cleanup interval in seconds (default 5 minutes)."""
        default = 300.0
        try:
            getter = getattr(app_config, "get_favicon_cache_cleanup_interval", None)
            if callable(getter):
                return max(30.0, float(getter()))
            raw = getattr(app_config, "favicon_cache_cleanup_interval", default)
            return max(30.0, float(raw))
        except Exception:  # noqa: BLE001
            return default

    @staticmethod
    def _now() -> float:
        return float(time.time())

    def _should_cleanup(self, db, now):
        """Check if cleanup is needed."""
        try:
            last_ts = float(db.get("__last_cleanup_ts__", 0.0))
        except Exception as exc:
            last_ts = 0.0
            logger.debug(
                "favicon_cache: failed to read last cleanup ts: %s", exc, exc_info=True
            )
        return (now - last_ts) >= self._cleanup_interval_sec

    def _remove_entry(self, db, index, k):
        """Remove entry from cache and index."""
        index.pop(k, None)
        try:
            if k in db:
                del db[k]
                return 1
        except Exception:
            pass
        return 0

    def _cleanup_expired_entries(self, db, index, now):
        """Remove expired or inconsistent entries."""
        removed = 0
        for k, ts in list(index.items()):
            try:
                item = db.get(k)
                if not isinstance(item, dict):
                    removed += self._remove_entry(db, index, k)
                    continue
                ttl = self._compute_effective_ttl(item)
                if ttl <= 0 or (now - ts) >= ttl:
                    removed += self._remove_entry(db, index, k)
            except Exception as exc:
                removed += self._remove_entry(db, index, k)
                logger.debug(
                    "favicon_cache: failed to inspect entry '%s' during cleanup: %s",
                    k,
                    exc,
                    exc_info=True,
                )
        return removed

    def _enforce_max_size(self, db, index):
        """Enforce max size by removing oldest entries."""
        removed = 0
        max_size = self._get_max_size()
        while len(index) > max_size:
            try:
                oldest_key = min(index.items(), key=lambda kv: kv[1])[0]
            except ValueError:
                break
            removed += self._remove_entry(db, index, oldest_key)
        return removed

    def _finalize_cleanup(self, db, index, now, removed):
        """Save cleanup state to database."""
        try:
            db["__last_cleanup_ts__"] = now
            db["__ts_index__"] = index
            try:
                sync = getattr(db, "sync", None)
                if callable(sync):
                    sync()
            except Exception:
                pass
            if removed:
                logger.debug("[cache] CLEANUP removed=%s", removed)
        except Exception as exc:
            logger.debug(
                "favicon_cache: failed to write last cleanup ts or log removed count: %s",
                exc,
                exc_info=True,
            )

    def _maybe_cleanup(self, db: shelve.Shelf, *, now: float | None = None) -> None:
        """Periodic cleanup: purge expired entries and, if needed, oldest records.

        To avoid frequent full scans, store timestamp of last cleanup in ``__last_cleanup_ts__``.
        """
        now = self._now() if now is None else float(now)
        if not self._should_cleanup(db, now):
            return

        removed = 0
        try:
            index: OrderedDict[str, float] = db.get("__ts_index__") or OrderedDict()
            removed += self._cleanup_expired_entries(db, index, now)
            removed += self._enforce_max_size(db, index)
        finally:
            self._finalize_cleanup(db, index, now, removed)

    # BaseCache implementation
    def _is_item_expired(self, item):
        """Check if cache item is expired."""
        if not item:
            return True
        ts = float(item.get("timestamp", 0.0))
        ttl = self._compute_effective_ttl(item)
        return ttl <= 0 or (self._now() - ts) >= ttl

    def _delete_expired_item(self, db, key):
        """Delete expired item from database."""
        try:
            del db[key]
            self._remove_key_from_index(db, key)
            self._sync_db(db)
        except Exception as exc:
            logger.debug(
                "favicon_cache: failed to delete expired key '%s' in get(): %s",
                key,
                exc,
                exc_info=True,
            )

    def _get_from_persistent(self, key):
        """Get item from persistent cache."""
        if self._db is None:
            self._open_db()
        db = self._db
        if db is None:
            return None

        item = db.get(key)
        if self._is_item_expired(item):
            self._delete_expired_item(db, key)
            return None
        return item

    def _get_from_non_persistent(self, key, current_path):
        """Get item from non-persistent cache."""
        try:
            icon_path_service.ensure_user_icons_dir()
        except Exception:
            pass

        with closing(shelve.open(current_path)) as db2:
            item = db2.get(key)
            if self._is_item_expired(item):
                self._delete_expired_item(db2, key)
                return None
            return item

    def get(self, key: str) -> Any | None:
        with self._lock:
            current_path = self._get_db_path()
            lock_path = f"{current_path}.lock"
            with _file_lock(lock_path):
                if self._persistent_enabled:
                    return self._get_from_persistent(key)
                else:
                    return self._get_from_non_persistent(key, current_path)

    def _prepare_cache_entry(
        self, value: Any, ttl: float | None, ts_now: float
    ) -> dict:
        """Prepare cache entry with timestamp and TTL."""
        if isinstance(value, dict):
            to_store = dict(value)
        else:
            to_store = {"value": value}
        to_store.setdefault("timestamp", ts_now)
        if ttl is not None:
            to_store["ttl"] = float(ttl)
        return to_store

    def _update_timestamp_index(self, db, key: str, timestamp: float) -> None:
        """Update timestamp index with new entry."""
        try:
            idx: OrderedDict[str, float] = db.get("__ts_index__") or OrderedDict()
            if key in idx:
                idx.pop(key, None)
            idx[key] = float(timestamp)
            db["__ts_index__"] = idx
        except Exception:
            pass

    def _sync_db(self, db) -> None:
        """Sync database to disk."""
        try:
            sync = getattr(db, "sync", None)
            if callable(sync):
                sync()
        except Exception:
            pass

    def _clean_phantom_keys(self, db, idx: OrderedDict) -> None:
        """Remove phantom keys from index that don't exist in DB."""
        for idx_key in list(idx.keys()):
            if idx_key not in db or idx_key.startswith("__"):
                idx.pop(idx_key, None)

    def _evict_by_index(self, db, idx: OrderedDict, max_size: int) -> None:
        """Evict oldest entries using index."""
        while len(idx) > max_size:
            try:
                oldest_key = min(idx.items(), key=lambda kv: kv[1])[0]
            except ValueError:
                break
            idx.pop(oldest_key, None)
            try:
                if oldest_key in db:
                    del db[oldest_key]
            except Exception:
                pass

    def _fallback_evict_by_scan(self, db, idx: OrderedDict, max_size: int) -> None:
        """Fallback eviction by scanning DB if index is incomplete."""
        try:
            non_service = [k for k in db.keys() if not k.startswith("__")]
            if len(non_service) <= max_size:
                return

            items: list[tuple[str, float]] = []
            for candidate_key in non_service:
                try:
                    entry = db.get(candidate_key)
                    ts_val = (
                        float(entry.get("timestamp", 0.0))
                        if isinstance(entry, dict)
                        else 0.0
                    )
                except Exception:
                    ts_val = 0.0
                items.append((candidate_key, ts_val))

            items.sort(key=lambda kv: kv[1])
            for victim_key, _ in items[max_size:]:
                try:
                    if victim_key in db:
                        del db[victim_key]
                    if victim_key in idx:
                        idx.pop(victim_key, None)
                except Exception:
                    pass
            db["__ts_index__"] = idx
        except Exception:
            pass

    def _enforce_size_limit(self, db) -> None:
        """Enforce cache size limit using index-based eviction."""
        try:
            max_size = self._get_max_size()
            idx: OrderedDict[str, float] = db.get("__ts_index__") or OrderedDict()

            # Clean phantom keys
            self._clean_phantom_keys(db, idx)

            # Evict by index
            self._evict_by_index(db, idx, max_size)
            db["__ts_index__"] = idx

            # Fallback eviction if needed
            self._fallback_evict_by_scan(db, idx, max_size)

            # Sync changes
            self._sync_db(db)
        except Exception:
            pass

    def _store_entry_in_db(self, db, key: str, value: Any, ttl: float | None) -> None:
        """Store entry in database with size enforcement."""
        ts_now = self._now()
        to_store = self._prepare_cache_entry(value, ttl, ts_now)

        db[key] = to_store
        self._update_timestamp_index(db, key, to_store.get("timestamp", ts_now))
        logger.debug("[cache] SAVE %s", key)
        self._sync_db(db)
        self._enforce_size_limit(db)

    def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        """Set cache entry with optional TTL."""
        with self._lock:
            current_path = self._get_db_path()
            lock_path = f"{current_path}.lock"
            with _file_lock(lock_path):
                if self._persistent_enabled:
                    # Persistent mode: use already-open DB
                    if self._db is None:
                        self._open_db()
                    db = self._db
                    if db is None:
                        return
                    self._store_entry_in_db(db, key, value, ttl)
                else:
                    # Non-persistent mode: open/close on every operation
                    try:
                        icon_path_service.ensure_user_icons_dir()
                    except Exception:
                        pass
                    with closing(shelve.open(current_path)) as db:
                        self._store_entry_in_db(db, key, value, ttl)
                        # Set last cleanup marker
                        try:
                            db["__last_cleanup_ts__"] = self._now()
                        except Exception:
                            pass

    def _clear_all_cache(self):
        """Clear all cache files."""
        try:
            self._close_db()
            base = self._get_db_path()
            for suffix in ("", ".bak", ".dat", ".dir"):
                p = f"{base}{suffix}"
                if Path(p).exists():
                    os.remove(p)
            logger.debug("[cache] CLEAR ALL")
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "favicon_cache: failed to clear db files: %s",
                exc,
                exc_info=True,
            )
        finally:
            if self._persistent_enabled:
                self._open_db()

    def _remove_key_from_index(self, db, key):
        """Remove key from timestamp index."""
        try:
            idx: OrderedDict[str, float] = db.get("__ts_index__") or OrderedDict()
            if key in idx:
                idx.pop(key, None)
                db["__ts_index__"] = idx
        except Exception:
            pass

    def _invalidate_persistent_key(self, key):
        """Invalidate key in persistent mode."""
        if self._db is None:
            self._open_db()
        db = self._db
        if db is None:
            return
        if key in db:
            try:
                del db[key]
                logger.debug("[cache] INVALIDATE %s", key)
                self._remove_key_from_index(db, key)
                self._sync_db(db)
            except Exception as exc:
                logger.debug(
                    "favicon_cache: failed to invalidate key '%s': %s",
                    key,
                    exc,
                    exc_info=True,
                )

    def _invalidate_non_persistent_key(self, key, current_path):
        """Invalidate key in non-persistent mode."""
        try:
            icon_path_service.ensure_user_icons_dir()
        except Exception:
            pass
        with closing(shelve.open(current_path)) as db2:
            if key in db2:
                try:
                    del db2[key]
                    logger.debug("[cache] INVALIDATE %s", key)
                    self._remove_key_from_index(db2, key)
                except Exception as exc:
                    logger.debug(
                        "favicon_cache: failed to invalidate key '%s': %s",
                        key,
                        exc,
                        exc_info=True,
                    )

    def invalidate(self, key: str | None = None) -> None:
        with self._lock:
            current_path = self._get_db_path()
            lock_path = f"{current_path}.lock"
            with _file_lock(lock_path):
                if key is None:
                    self._clear_all_cache()
                    return

                if self._persistent_enabled:
                    self._invalidate_persistent_key(key)
                else:
                    self._invalidate_non_persistent_key(key, current_path)


# Глобальный экземпляр
favicon_cache = FaviconCache()


__all__ = ["FaviconCache", "favicon_cache"]
