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
from collections import OrderedDict
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
        # Валидируем max_size: допускаем None или целое число >= 0; отрицательные — ошибка
        if max_size is None:
            self._max_size = None
        else:
            try:
                ms = int(max_size)
            except Exception as exc:  # noqa: BLE001
                raise ValueError("max_size must be an integer or None") from exc
            if ms < 0:
                raise ValueError("max_size must be >= 0 or None")
            self._max_size = ms
        self._lock = threading.RLock()
        # Порядок LRU хранится в OrderedDict: самый свежий справа (конце)
        # key -> CacheRecord
        self._store: OrderedDict[str, CacheRecord] = OrderedDict()

    def _touch(self, key: str) -> None:
        # Перемещаем ключ в конец как самый недавно использованный
        if key in self._store:
            self._store.move_to_end(key, last=True)

    def _evict_if_needed(self) -> None:
        if self._max_size is None:
            return
        while len(self._store) > self._max_size:
            # Удалить самый старый (слева)
            try:
                self._store.popitem(last=False)
            except KeyError:
                break

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            rec = self._store.get(key)
            if rec is None:
                return None
            if not rec.is_valid():
                # устарело — удалить
                self._store.pop(key, None)
                return None
            self._touch(key)
            return rec.value

    def set(self, key: str, value: Any, *, ttl: Optional[float] = None) -> None:
        with self._lock:
            rec = CacheRecord(value=value, ts=time.time(), ttl=ttl if ttl is not None else self._default_ttl)
            self._store[key] = rec
            # Переместим в конец как самый свежий
            self._store.move_to_end(key, last=True)
            self._evict_if_needed()

    def invalidate(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                if self._store:
                    self._store.clear()
                return
            self._store.pop(key, None)
