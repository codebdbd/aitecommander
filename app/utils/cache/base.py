"""
Базовые абстракции для кэширования.

Единый API:
- get(key) -> Optional[Any]
- set(key, value, *, ttl: Optional[float] = None) -> None
- invalidate(key: Optional[str] = None) -> None
- clear() -> None

Примечания:
- TTL (секунды) можно задавать на запись; реализация может также иметь дефолтный TTL.
- Реализации должны быть потокобезопасны, если предполагается многопоточность.
"""
from __future__ import annotations

import abc
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CacheRecord:
    value: Any
    ts: float
    ttl: Optional[float] = None

    def is_valid(self) -> bool:
        if self.ttl is None:
            return True
        try:
            ttl = float(self.ttl)
        except Exception:
            return False
        if ttl <= 0:
            return False
        return (time.time() - self.ts) < ttl


class BaseCache(abc.ABC):
    """Абстрактный базовый класс кэша."""

    @abc.abstractmethod
    def get(self, key: str) -> Optional[Any]:  # pragma: no cover - контракт
        raise NotImplementedError

    @abc.abstractmethod
    def set(self, key: str, value: Any, *, ttl: Optional[float] = None) -> None:  # pragma: no cover - контракт
        raise NotImplementedError

    @abc.abstractmethod
    def invalidate(self, key: Optional[str] = None) -> None:  # pragma: no cover - контракт
        raise NotImplementedError

    def clear(self) -> None:
        """Синоним invalidate(None)."""
        self.invalidate(None)


class InMemoryCache(BaseCache):
    """Простая потокобезопасная in-memory реализация с опциональным дефолтным TTL и лимитом размера (LRU).

    Вытеснение: при вставке, если достигнут max_size, удаляется самый старый ключ по последнему доступу.
    """

    def __init__(self, *, default_ttl: Optional[float] = None, max_size: Optional[int] = None) -> None:
        self._default_ttl = default_ttl
        self._max_size = int(max_size) if max_size is not None else None
        self._lock = threading.RLock()
        # key -> CacheRecord
        self._store: dict[str, CacheRecord] = {}
        # Порядок LRU: самый свежий справа
        self._lru: list[str] = []

    def _touch(self, key: str) -> None:
        try:
            self._lru.remove(key)
        except ValueError:
            pass
        self._lru.append(key)

    def _evict_if_needed(self) -> None:
        if self._max_size is None:
            return
        while len(self._store) > self._max_size:
            # удалить самый старый (слева)
            oldest = self._lru.pop(0)
            self._store.pop(oldest, None)

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            rec = self._store.get(key)
            if rec is None:
                return None
            if not rec.is_valid():
                # устарело — удалить
                self._store.pop(key, None)
                try:
                    self._lru.remove(key)
                except ValueError:
                    pass
                return None
            self._touch(key)
            return rec.value

    def set(self, key: str, value: Any, *, ttl: Optional[float] = None) -> None:
        with self._lock:
            rec = CacheRecord(value=value, ts=time.time(), ttl=ttl if ttl is not None else self._default_ttl)
            self._store[key] = rec
            self._touch(key)
            self._evict_if_needed()

    def invalidate(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                if self._store:
                    self._store.clear()
                    self._lru.clear()
                return
            self._store.pop(key, None)
            try:
                self._lru.remove(key)
            except ValueError:
                pass
