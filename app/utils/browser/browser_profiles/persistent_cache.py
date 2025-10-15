"""
Persistent browser profile cache based on BaseCache.
- In-memory storage with TTL (record validity)
- Persistence in JSON file: one common file for all browsers
Compatible with previous `profile_cache.py` format.
"""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from app.config_data import app_config
from app.utils.cache.base import BaseCache, CacheRecord


def get_cache_path() -> Path:
    """Returns path to browser profile cache file.

    Remains compatible with previous location: browser_profiles.json
    in user config directory.
    """
    return app_config.paths.get_config_dir() / "browser_profiles.json"


class PersistentProfileCache(BaseCache, AbstractContextManager["PersistentProfileCache"]):
    def __init__(self, *, default_ttl: float | None = None) -> None:
        self._default_ttl = default_ttl
        self._lock = threading.RLock()
        self._store: dict[str, CacheRecord] = {}
        self._path: Path = get_cache_path()
        # Deferred/batch writing
        try:
            _delay = getattr(app_config, "get_profile_cache_flush_delay", None)
            self._flush_delay_sec: float = float(_delay()) if callable(_delay) else 0.5
        except Exception:
            self._flush_delay_sec = 0.5
        self._dirty: bool = False
        self._next_flush_ts: float = 0.0
        self._load_from_disk()

    @property
    def timeout(self) -> float | None:
        """Returns default TTL (seconds) if set for cache.

        Compatibility: previously consumers might expect `timeout` field to exist on cache.
        Now we provide property proxying `_default_ttl`.
        """
        return self._default_ttl

    # --- file operations ---
    def _load_from_disk(self) -> None:
        try:
            if not self._path.exists():
                return
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            now = time.time()
            for key, profiles in data.items():
                if not isinstance(key, str):
                    continue
                # При старте считаем загруженные данные свежими
                self._store[key] = CacheRecord(
                    value=profiles, ts=now, ttl=self._default_ttl
                )
        except Exception:
            # Quietly ignore loading problems, as before
            pass

    def _ensure_dirs(self) -> None:
        try:
            app_config.paths.ensure_user_data_dirs()
        except Exception:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def _dump_to_disk(self) -> None:
        # Save only values (without internal fields) atomically
        data: dict[str, Any] = {key: rec.value for key, rec in self._store.items()}
        self._ensure_dirs()
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            # 1) Write to temporary file
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                try:
                    f.flush()
                    os.fsync(f.fileno())  # synchronize to disk when possible
                except Exception:
                    # On some FS/OS fsync may be unnecessary/unavailable — ignore
                    pass
            # 2) Atomically replace main file
            os.replace(str(tmp_path), str(self._path))
        except Exception:
            # On any error try to delete temporary file, don't touch main file
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass
            raise

    # --- deferred flush mechanics ---
    def _mark_dirty_locked(self) -> None:
        self._dirty = True
        now = time.time()
        # if not scheduled, schedule
        if self._next_flush_ts <= 0:
            self._next_flush_ts = now + self._flush_delay_sec

    def _maybe_flush_locked(self, *, force: bool = False) -> None:
        if not self._dirty:
            return
        now = time.time()
        if force or (self._next_flush_ts > 0 and now >= self._next_flush_ts):
            try:
                self._dump_to_disk()
            except Exception:
                # Don't fail on disk error
                pass
            finally:
                # Reset flags regardless of result to avoid infinite writing
                self._dirty = False
                self._next_flush_ts = 0.0

    # --- BaseCache API ---
    def get(self, key: str) -> Any | None:
        with self._lock:
            rec = self._store.get(key)
            if rec is None:
                return None
            # check TTL
            if not rec.is_valid():
                # Expired — remove from memory and mark need for deferred write
                self._store.pop(key, None)
                self._mark_dirty_locked()
                self._maybe_flush_locked()
                return None
            return rec.value

    def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        with self._lock:
            self._store[key] = CacheRecord(
                value=value,
                ts=time.time(),
                ttl=self._default_ttl if ttl is None else ttl,
            )
            # Mark dirty state and defer writing
            self._mark_dirty_locked()
            self._maybe_flush_locked()

    def invalidate(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)
            self._mark_dirty_locked()
            self._maybe_flush_locked()

    def keys(self) -> list[str]:
        """Return list of all valid keys in cache."""
        with self._lock:
            time.time()
            valid_keys = []
            for key, rec in self._store.items():
                if rec is not None and rec.is_valid():
                    valid_keys.append(key)
            return valid_keys

    def __len__(self) -> int:
        """Return number of valid entries in cache."""
        return len(self.keys())

    # --- public flush control methods ---
    def flush(self) -> None:
        """Force flush changes to disk."""
        with self._lock:
            self._maybe_flush_locked(force=True)

    def periodic_flush(self) -> None:
        """External periodic point: flush if time has come."""
        with self._lock:
            self._maybe_flush_locked(force=False)

    # Context manager for guaranteed flush
    def __enter__(self) -> "PersistentProfileCache":
        self._lock.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb,
    ) -> bool | None:  # noqa: D401
        try:
            self._maybe_flush_locked(force=True)
        except Exception:
            pass
        finally:
            self._lock.release()
        return None
