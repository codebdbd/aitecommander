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
    def set(
        self, key: str, value: Any, *, ttl: Optional[float] = None
    ) -> None:  # pragma: no cover - контракт
        raise NotImplementedError

    @abc.abstractmethod
    def invalidate(
        self, key: Optional[str] = None
    ) -> None:  # pragma: no cover - контракт
        raise NotImplementedError

    def clear(self) -> None:
        """Синоним invalidate(None)."""
        self.invalidate(None)


class InMemoryCache(BaseCache):
    """Простая потокобезопасная in-memory реализация с опциональным дефолтным TTL и лимитом размера (LRU).

    Вытеснение: при вставке, если достигнут ``max_size``, удаляется самый старый ключ по последнему доступу.

    Очистка протухших записей (TTL):
    - При ``get`` протухшие записи удаляются лениво.
    - Дополнительно доступен метод ``prune_expired()``, который удаляет все протухшие записи за один проход.
    - Чтобы не делать полный проход по ключам на каждый вызов, используется оппортунистическая стратегия:
      при ``set``/``invalidate`` очистка вызывается не чаще, чем раз в ``_prune_interval_sec`` секунд.
    - Значение интервала по умолчанию — 60 секунд; можно изменить через свойство ``_prune_interval_sec``.
    """

    def __init__(
        self, *, default_ttl: Optional[float] = None, max_size: Optional[int] = None
    ) -> None:
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
        # Параметры фоновой/периодической очистки
        self._last_prune_ts: float = 0.0
        self._prune_interval_sec: float = 60.0

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
            rec = CacheRecord(
                value=value,
                ts=time.time(),
                ttl=ttl if ttl is not None else self._default_ttl,
            )
            self._store[key] = rec
            # Переместим в конец как самый свежий
            self._store.move_to_end(key, last=True)
            self._evict_if_needed()
            self._maybe_prune_expired_locked()

    def invalidate(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                if self._store:
                    self._store.clear()
                # После полной очистки обновим время последней очистки
                self._last_prune_ts = time.time()
                return
            self._store.pop(key, None)
            self._maybe_prune_expired_locked()

    # --- Очистка протухших записей ---
    def prune_expired(self) -> int:
        """Удаляет все устаревшие записи (TTL истёк). Возвращает число удалённых ключей.

        Выполняет полный проход по ключам под блокировкой. Безопасно вызывать в любое время.
        """
        removed = 0
        with self._lock:
            now = time.time()
            # Собираем список, чтобы не модифицировать dict во время итерации
            for k, rec in list(self._store.items()):
                try:
                    ttl = rec.ttl if rec.ttl is not None else self._default_ttl
                    if ttl is None:
                        continue
                    ttl_f = float(ttl)
                except Exception:
                    ttl_f = 0.0
                if ttl_f <= 0 or (now - rec.ts) >= ttl_f:
                    self._store.pop(k, None)
                    removed += 1
            self._last_prune_ts = now
        return removed

    def _maybe_prune_expired_locked(self) -> None:
        """Оппортунистическая очистка: запускаем ``prune_expired`` не чаще,
        чем раз в ``_prune_interval_sec`` секунд. Требует внешней блокировки ``_lock``.
        """
        try:
            now = time.time()
            if (now - self._last_prune_ts) >= self._prune_interval_sec:
                # Вызов без повторного захвата, так как мы уже под _lock
                removed = 0
                # Лёгкая оптимизация: если мало ключей, просто пройдёмся
                for k, rec in list(self._store.items()):
                    ttl = rec.ttl if rec.ttl is not None else self._default_ttl
                    if ttl is None:
                        continue
                    try:
                        ttl_f = float(ttl)
                    except Exception:
                        ttl_f = 0.0
                    if ttl_f <= 0 or (now - rec.ts) >= ttl_f:
                        self._store.pop(k, None)
                        removed += 1
                self._last_prune_ts = now
        except Exception:
            # Никогда не мешаем пользовательскому коду из-за ошибок в очистке
            pass
