"""Менеджер кэша иконок со стандартным API (пути, QIcon, LRU, TTL, метрики)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Union

from PyQt6.QtGui import QIcon

from app.config_data import app_config

from .lock_manager import LockLevel, acquire_cache_lock, acquire_multiple_locks
from .lru_policy import LRUPolicy

logger = logging.getLogger(__name__)


try:
    from .metrics import CacheMetrics as _ExternalCacheMetrics  # type: ignore
except Exception:  # noqa: BLE001
    _ExternalCacheMetrics = None


class _FallbackCacheMetrics:
    """Простая реализация метрик, если .metrics недоступен."""

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

    def get_stats(self) -> Dict[str, Union[int, float]]:
        with self._lock:
            return {
                "hits": self.hits,
                "misses": self.misses,
                "actual_misses": self.actual_misses,
                "disk_loads": self.disk_loads,
                "not_found": self.not_found,
                "total_load_time": round(self.total_load_time, 6),
            }


CacheMetrics = _ExternalCacheMetrics or _FallbackCacheMetrics

# --- Типы записей кэша ---

def _is_entry_valid(timestamp: float, ttl_seconds: Optional[float]) -> bool:
    """Проверяет валидность записи по TTL."""
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
    """Запись кэша для путей к иконкам."""

    path: Optional[str]
    timestamp: float
    ttl_override: Optional[float] = None

    def is_valid(self, ttl_seconds: Optional[float]) -> bool:
        return _is_entry_valid(self.timestamp, ttl_seconds)


@dataclass
class IconCacheEntry:
    """Запись кэша для QIcon."""

    icon: QIcon
    timestamp: float
    negative: bool = False
    ttl_override: Optional[float] = None

    def is_valid(self, ttl_seconds: Optional[float]) -> bool:
        return _is_entry_valid(self.timestamp, ttl_seconds)


# --- Потокобезопасный кэш ---


class ThreadSafeIconCache:
    """Потокобезопасный LRU-кэш путей и QIcon."""

    def __init__(self, maxsize: Optional[int] = None) -> None:
        capacity = (
            int(maxsize)
            if maxsize is not None
            else int(app_config.get_icon_cache_size())
        )
        if capacity <= 0:
            capacity = 1

        self._path_cache: Dict[str, PathCacheEntry] = {}
        self._qicon_cache: Dict[str, IconCacheEntry] = {}
        self._path_lru = LRUPolicy(capacity)
        self._qicon_lru = LRUPolicy(capacity)

        self.metrics: CacheMetrics = CacheMetrics()
        self._capacity = capacity

        try:
            self._ttl_icon: Optional[float] = app_config.get_icon_cache_ttl()
        except Exception:  # noqa: BLE001
            self._ttl_icon = None
        try:
            self._ttl_abs: Optional[float] = app_config.get_abs_icon_cache_ttl()
        except Exception:  # noqa: BLE001
            self._ttl_abs = None
        try:
            self._ttl_negative: Optional[float] = app_config.get_negative_cache_ttl()
        except Exception:  # noqa: BLE001
            self._ttl_negative = None

        self._getter_icon = getattr(app_config, "get_icon_cache_ttl", None)
        self._getter_abs = getattr(app_config, "get_abs_icon_cache_ttl", None)
        self._getter_negative = getattr(app_config, "get_negative_cache_ttl", None)

    # --- ключи ---

    @staticmethod
    def _key(icon_name: str, theme: str) -> str:
        return f"{icon_name}::{theme}"

    @staticmethod
    def _parse_unified_key(key: str) -> tuple[str, str, str]:
        """Разобрать единый ключ формата 'path:icon::theme' или 'qicon:icon::theme'.

        Возвращает кортеж (prefix, icon_name, theme). Бросает ValueError при неверном формате.
        """
        if ":" not in key:
            raise ValueError("Unified key must contain prefix 'path:' or 'qicon:'")
        prefix, rest = key.split(":", 1)
        if "::" not in rest:
            raise ValueError("Unified key must be in form '<prefix>:<icon_name>::<theme>'")
        icon_name, theme = rest.split("::", 1)
        if prefix not in {"path", "qicon"}:
            raise ValueError("Unsupported prefix, expected 'path' or 'qicon'")
        return prefix, icon_name, theme

    # --- служебное для ресинхронизации ---

    def _sync_path_structs(self) -> None:
        self._path_lru.sync_with_cache(self._path_cache)

    def _sync_qicon_structs(self) -> None:
        self._qicon_lru.sync_with_cache(self._qicon_cache)

    # --- обновление TTL при monkeypatch ---

    def _ensure_fresh_ttls(self) -> None:
        """Обновляет кешированные TTL при изменении геттеров в app_config."""
        try:
            if getattr(app_config, "get_icon_cache_ttl", None) is not self._getter_icon:
                self._getter_icon = getattr(app_config, "get_icon_cache_ttl", None)
                try:
                    self._ttl_icon = app_config.get_icon_cache_ttl()
                except Exception:  # noqa: BLE001
                    self._ttl_icon = None
            if getattr(app_config, "get_abs_icon_cache_ttl", None) is not self._getter_abs:
                self._getter_abs = getattr(app_config, "get_abs_icon_cache_ttl", None)
                try:
                    self._ttl_abs = app_config.get_abs_icon_cache_ttl()
                except Exception:  # noqa: BLE001
                    self._ttl_abs = None
            if getattr(app_config, "get_negative_cache_ttl", None) is not self._getter_negative:
                self._getter_negative = getattr(app_config, "get_negative_cache_ttl", None)
                try:
                    self._ttl_negative = app_config.get_negative_cache_ttl()
                except Exception:  # noqa: BLE001
                    self._ttl_negative = None
        except Exception as exc:
            # Никогда не мешаем основному пути исполнения из-за ошибок конфигурации
            logger.debug("IconCache: TTL refresh failed, using previous values: %s", exc, exc_info=True)

    # --- PATH API ---

    def get_path(self, icon_name: str, theme: str) -> Optional[str]:
        """Возвращает путь к иконке из кэша путей."""
        with acquire_cache_lock():
            self._ensure_fresh_ttls()
            self._sync_path_structs()
            key = self._key(icon_name, theme)
            entry = self._path_cache.get(key)
            if entry is None:
                try:
                    self.metrics.record_miss()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("IconCache.metrics.record_miss failed: %s", exc, exc_info=True)
                return None

            # Персональный TTL имеет приоритет над глобальным TTL для путей
            ttl = entry.ttl_override if entry.ttl_override is not None else self._ttl_icon
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
                logger.debug("IconCache.metrics.record_hit failed: %s", exc, exc_info=True)
            return entry.path

    def set_path(self, icon_name: str, theme: str, path: Optional[str]) -> None:
        """Сохраняет путь к иконке в кэше путей."""
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

    def get_qicon(self, icon_name: str, theme: str) -> Optional[QIcon]:
        """Возвращает QIcon из кэша иконок."""
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

            # Базовый TTL по типу записи, затем приоритет per-entry override
            if entry.negative:
                base_ttl = self._ttl_negative
            else:
                base_ttl = (self._ttl_abs if theme == "__abs__" else self._ttl_icon)
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
        icon: Optional[QIcon],
        *,
        negative: bool = False,
    ) -> None:
        """Сохраняет QIcon в кэше иконок."""
        with acquire_cache_lock():
            self._sync_qicon_structs()
            key = self._key(icon_name, theme)

            should_evict, old_key = self._qicon_lru.evict_if_needed(
                self._qicon_cache, key
            )
            if should_evict and old_key:
                self._qicon_cache.pop(old_key, None)

            entry = IconCacheEntry(icon=icon, timestamp=time.time(), negative=negative, ttl_override=None)
            self._qicon_cache[key] = entry
            self._qicon_lru.access(key)
            logger.debug("Set QICON: %s", key)

    # --- BaseCache-совместимый API (унифицированные ключи) ---

    def get(self, key: str) -> Optional[Union[str, QIcon]]:
        """Возвращает значение по ключу 'path:...'/ 'qicon:...'."""
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
                        logger.debug("IconCache.metrics.record_miss failed: %s", exc, exc_info=True)
                    return None
                ttl = entry.ttl_override if entry.ttl_override is not None else self._ttl_icon
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
                    logger.debug("IconCache.metrics.record_hit failed: %s", exc, exc_info=True)
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
                    logger.debug("IconCache.metrics.record_hit failed: %s", exc, exc_info=True)
                return entry.icon

    def set(self, key: str, value: Optional[Union[str, QIcon]], *, ttl: Optional[float] = None) -> None:
        """Устанавливает значение по ключу (для qicon None означает негативную запись)."""
        prefix, icon_name, theme = self._parse_unified_key(key)
        with acquire_cache_lock():
            if prefix == "path":
                self._sync_path_structs()
                k = self._key(icon_name, theme)
                should_evict, old_key = self._path_lru.evict_if_needed(self._path_cache, k)
                if should_evict and old_key:
                    self._path_cache.pop(old_key, None)
                entry = PathCacheEntry(path=value if isinstance(value, (str, type(None))) else None, timestamp=time.time(), ttl_override=ttl)
                self._path_cache[k] = entry
                self._path_lru.access(k)
            else:
                self._sync_qicon_structs()
                k = self._key(icon_name, theme)
                should_evict, old_key = self._qicon_lru.evict_if_needed(self._qicon_cache, k)
                if should_evict and old_key:
                    self._qicon_cache.pop(old_key, None)
                negative = value is None
                icon_val: Optional[QIcon] = value if isinstance(value, QIcon) else None
                entry = IconCacheEntry(icon=icon_val, timestamp=time.time(), negative=negative, ttl_override=ttl)
                self._qicon_cache[k] = entry
                self._qicon_lru.access(k)

    def invalidate(self, key: Optional[str] = None) -> None:
        """Инвалидирует запись по ключу или весь кэш при key=None."""
        with acquire_cache_lock():
            if key is None:
                # Полная очистка без пересоздания LRU и метрик
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
        """Полная очистка кэшей и метрик."""
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

    def get_cache_stats(self) -> Dict[str, Union[int, float]]:
        """Агрегированная статистика по кэшу и метрикам."""
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


# --- Менеджер (Singleton) ---


class IconManager:
    """Синглтон-обёртка над ThreadSafeIconCache."""

    _instance: Optional["IconManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "IconManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, cache: Optional[ThreadSafeIconCache] = None) -> None:
        if getattr(self, "_initialized", False):
            return
        self._cache = cache if cache is not None else ThreadSafeIconCache()
        self._initialized = True

    # Унифицированный API (совместимый с BaseCache)
    def get(self, key: str) -> Optional[Union[str, QIcon]]:
        return self._cache.get(key)

    def set(self, key: str, value: Optional[Union[str, QIcon]], *, ttl: Optional[float] = None) -> None:
        self._cache.set(key, value, ttl=ttl)

    def invalidate(self, key: Optional[str] = None) -> None:
        self._cache.invalidate(key)

    # PATH (новые стандартизированные имена)
    def get_path(self, icon_name: str, theme: str) -> Optional[str]:
        return self._cache.get_path(icon_name, theme)

    def set_path(self, icon_name: str, theme: str, path: Optional[str]) -> None:
        self._cache.set_path(icon_name, theme, path)

    # QICON (новые стандартизированные имена)
    def get_icon(self, icon_name: str, theme: str) -> Optional[QIcon]:
        return self._cache.get_qicon(icon_name, theme)

    def set_icon(
        self,
        icon_name: str,
        theme: str,
        icon: Optional[QIcon],
        *,
        negative: bool = False,
    ) -> None:
        self._cache.set_qicon(icon_name, theme, icon, negative=negative)

    # Admin
    def clear_cache(self) -> None:
        self._cache.clear()

    def get_cache_stats(self) -> Dict[str, Union[int, float]]:
        return self._cache.get_cache_stats()

    # Метрики (без прямого доступа к внутренним локам)
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
    """Очищает кэш иконок."""
    _icon_manager.clear_cache()


def get_icon_cache_stats() -> Dict[str, Union[int, float]]:
    """Возвращает статистику кэша."""
    return _icon_manager.get_cache_stats()


def reset_icon_cache_stats() -> None:
    """Сбрасывает метрики."""
    _icon_manager._cache.metrics.reset()


def log_icon_cache_stats() -> None:
    """Логирует статистику кэша."""
    logger.info("Icon Cache Stats: %s", get_icon_cache_stats())


def record_miss_without_increment(load_time: float = 0.0) -> None:
    _icon_manager.record_miss_without_increment(load_time)


def record_actual_miss(load_time: float = 0.0) -> None:
    _icon_manager.record_actual_miss(load_time)


def record_disk_load() -> None:
    _icon_manager.record_disk_load()


def record_not_found() -> None:
    _icon_manager.record_not_found()


def get_icon(icon_name: str, theme: str) -> Optional[QIcon]:
    return _icon_manager.get_icon(icon_name, theme)


def set_icon(
    icon_name: str,
    theme: str,
    icon: Optional[QIcon],
    *,
    negative: bool = False,
) -> None:
    _icon_manager.set_icon(icon_name, theme, icon, negative=negative)


def get_path(icon_name: str, theme: str) -> Optional[str]:
    return _icon_manager.get_path(icon_name, theme)


def set_path(icon_name: str, theme: str, path: Optional[str]) -> None:
    _icon_manager.set_path(icon_name, theme, path)

def get(key: str) -> Optional[Union[str, QIcon]]:
    return _icon_manager.get(key)


def set(key: str, value: Optional[Union[str, QIcon]], *, ttl: Optional[float] = None) -> None:
    _icon_manager.set(key, value, ttl=ttl)


def invalidate(key: Optional[str] = None) -> None:
    _icon_manager.invalidate(key)


def clear() -> None:
    clear_icon_cache()


def get_cached_category_icon(path: str) -> QIcon:
    """Получить кэшированную иконку категории из общего кэша без зависимостей от icon_operations."""
    cache_key = f"category::{path}"
    cached_icon = get_icon(cache_key, "__category__")
    if cached_icon is not None:
        return cached_icon

    # Создаем QIcon напрямую по пути, без вызова create_icon_from_path, чтобы избежать циклов импорта
    icon = QIcon(str(path)) if Path(path).exists() else QIcon()

    set_icon(cache_key, "__category__", icon)
    return icon
