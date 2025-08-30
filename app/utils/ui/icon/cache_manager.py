# cache_manager.py
"""Менеджер кэша иконок (стандартизированный API).

Особенности:
- Разделены записи кэша путей и QIcon (без смешения типов).
- Потокобезопасность через централизованные блокировки.
- LRU-политика для каждого кэша.
- TTL для обычных иконок и отдельный TTL для абсолютных путей.
- Отрицательное кэширование (см. negative_cache.py).
- Метрики с fallback, если нет модуля .metrics.

Публичный API (функции модуля):
- get_icon(name, theme) / set_icon(name, theme, qicon)
- get_path(name, theme) / set_path(name, theme, path)
- clear_icon_cache(), get_icon_cache_stats(), reset_icon_cache_stats(), log_icon_cache_stats()

Устаревшие алиасы удалены: get_qicon_from_cache, cache_qicon, get_path_from_cache, cache_path.
"""

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


# --- Метрики: используем проектную реализацию, либо fallback ---

try:
    # если у вас есть отдельный модуль metrics.py
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

    # базовые операции
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


def _is_entry_valid(
    timestamp: float, negative: bool, ttl_seconds: Optional[float]
) -> bool:
    """Проверка валидности записи по TTL.

    minimal, предсказуемая логика: запись валидна, если ttl не задан или
    текущее время минус timestamp меньше ttl. Флаг negative зарезервирован
    для возможной дифференциации, но сейчас на логику не влияет.
    """
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
    negative: bool = False

    def is_valid(self, ttl_seconds: Optional[float]) -> bool:
        return _is_entry_valid(self.timestamp, self.negative, ttl_seconds)


@dataclass
class IconCacheEntry:
    """Запись кэша для QIcon."""

    icon: QIcon
    timestamp: float
    negative: bool = False

    def is_valid(self, ttl_seconds: Optional[float]) -> bool:
        return _is_entry_valid(self.timestamp, self.negative, ttl_seconds)


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

        # Используем централизованную систему блокировок
        # self._lock заменен на lock_manager
        self.metrics: CacheMetrics = CacheMetrics()
        self._capacity = capacity

    # --- ключи ---

    @staticmethod
    def _key(icon_name: str, theme: str) -> str:
        return f"{icon_name}::{theme}"

    # --- служебное для ресинхронизации ---

    def _sync_path_structs(self) -> None:
        self._path_lru.sync_with_cache(self._path_cache)

    def _sync_qicon_structs(self) -> None:
        self._qicon_lru.sync_with_cache(self._qicon_cache)

    # --- PATH API ---

    def get_path(self, icon_name: str, theme: str) -> Optional[str]:
        """Получить путь к иконке из кэша путей."""
        with acquire_cache_lock():
            self._sync_path_structs()
            key = self._key(icon_name, theme)
            entry = self._path_cache.get(key)
            if entry is None:
                return None

            ttl = app_config.get_icon_cache_ttl()
            if not entry.is_valid(ttl):
                # Удаляем устаревшую запись
                self._path_cache.pop(key, None)
                self._path_lru.remove(key)
                return None

            # Обновляем порядок доступа
            self._path_lru.access(key)
            return entry.path

    def set_path(self, icon_name: str, theme: str, path: Optional[str]) -> None:
        """Сохранить путь к иконке в кэше путей."""
        with acquire_cache_lock():
            self._sync_path_structs()
            key = self._key(icon_name, theme)

            # Проверяем необходимость вытеснения
            should_evict, old_key = self._path_lru.evict_if_needed(
                self._path_cache, key
            )
            if should_evict and old_key:
                self._path_cache.pop(old_key, None)

            # Добавляем новую запись
            entry = PathCacheEntry(path=path, timestamp=time.time())
            self._path_cache[key] = entry
            self._path_lru.access(key)
            logger.debug("Set PATH: %s", key)

    # --- QICON API ---

    def get_qicon(self, icon_name: str, theme: str) -> Optional[QIcon]:
        """Получить QIcon из кэша иконок."""
        with acquire_cache_lock():
            self._sync_qicon_structs()
            key = self._key(icon_name, theme)
            entry = self._qicon_cache.get(key)
            if entry is None:
                return None

            ttl = (
                app_config.get_abs_icon_cache_ttl()
                if theme == "__abs__"
                else app_config.get_icon_cache_ttl()
            )
            if not entry.is_valid(ttl):
                # Удаляем устаревшую запись
                self._qicon_cache.pop(key, None)
                self._qicon_lru.remove(key)
                return None

            # Обновляем порядок доступа
            self._qicon_lru.access(key)
            return entry.icon

    def set_qicon(
        self,
        icon_name: str,
        theme: str,
        icon: Optional[QIcon],
        *,
        negative: bool = False,
    ) -> None:
        """Сохранить QIcon в кэше иконок."""
        with acquire_cache_lock():
            self._sync_qicon_structs()
            key = self._key(icon_name, theme)

            # Проверяем необходимость вытеснения
            should_evict, old_key = self._qicon_lru.evict_if_needed(
                self._qicon_cache, key
            )
            if should_evict and old_key:
                self._qicon_cache.pop(old_key, None)

            # Добавляем новую запись
            entry = IconCacheEntry(icon=icon, timestamp=time.time(), negative=negative)
            self._qicon_cache[key] = entry
            self._qicon_lru.access(key)
            logger.debug("Set QICON: %s", key)

    # --- сервисные методы ---

    def clear(self) -> None:
        """Полная очистка кэшей и метрик."""
        with acquire_multiple_locks(LockLevel.CACHE, LockLevel.METRICS):
            self._path_cache.clear()
            self._qicon_cache.clear()
            # Перечитываем capacity из конфигурации (поддержка monkeypatch в тестах)
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


# Глобальный экземпляр менеджера
_icon_manager = IconManager()


# --- Публичный API: функции-обёртки ---


def clear_icon_cache() -> None:
    """Очистить кэш иконок."""
    _icon_manager.clear_cache()


def get_icon_cache_stats() -> Dict[str, Union[int, float]]:
    """Получить статистику кэша."""
    return _icon_manager.get_cache_stats()


def reset_icon_cache_stats() -> None:
    """Сбросить метрики."""
    _icon_manager._cache.metrics.reset()


def log_icon_cache_stats() -> None:
    """Залогировать статистику кэша."""
    logger.info("Icon Cache Stats: %s", get_icon_cache_stats())


# Метрики (используются из icon_operations.py)
def record_miss_without_increment(load_time: float = 0.0) -> None:
    _icon_manager.record_miss_without_increment(load_time)


def record_actual_miss(load_time: float = 0.0) -> None:
    _icon_manager.record_actual_miss(load_time)


def record_disk_load() -> None:
    _icon_manager.record_disk_load()


def record_not_found() -> None:
    _icon_manager.record_not_found()


# Доступ к данным кэша
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

# Обратная совместимость (deprecated): модульные функции-алиасы
def get_qicon_from_cache(icon_name: str, theme: str) -> Optional[QIcon]:
    return get_icon(icon_name, theme)

def cache_qicon(
    icon_name: str,
    theme: str,
    icon: Optional[QIcon],
    *,
    negative: bool = False,
) -> None:
    set_icon(icon_name, theme, icon, negative=negative)

def get_path_from_cache(icon_name: str, theme: str) -> Optional[str]:
    return get_path(icon_name, theme)

def cache_path(icon_name: str, theme: str, path: Optional[str]) -> None:
    set_path(icon_name, theme, path)


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
