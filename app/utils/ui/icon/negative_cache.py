"""
Негативный кэш для путей иконок, реализованный как класс `NegativeCache`,
совместимый с общим API `BaseCache`.

Публичный API модуля:
- объект `negative_cache: NegativeCache`
- функции-обёртки: `is_negative(key)`, `mark_negative(key)`, `clear()`

Контракт `BaseCache`:
- get(key) -> Optional[Any]   # возвращает True, если ключ негативен и ещё валиден; иначе None
- set(key, value, *, ttl: Optional[float] = None) -> None  # помечает ключ как негативный (value игнорируется)
- invalidate(key: Optional[str] = None) -> None            # снять метку для ключа или очистить всё
- clear() -> None                                          # синоним invalidate(None)

Ключ формируется на верхнем уровне (например, f"{theme}:{icon_name.lower()}").
"""

from __future__ import annotations

import heapq
import threading
import time
from typing import Any

from app.config_data import app_config
from app.utils.cache.base import BaseCache

_DEFAULT_TTL: float = 60.0
_MAX_TTL: float = 600.0
_MAX_STRIKES: int = 5  # дефолт на случай отсутствия конфига
_DEFAULT_MAX_SIZE: int = 1000  # предохранитель от неограниченного роста


def _base_ttl() -> float:
    try:
        return float(getattr(app_config, "icon_negative_cache_ttl", _DEFAULT_TTL))
    except Exception:
        return _DEFAULT_TTL


def _max_ttl() -> float:
    try:
        return float(getattr(app_config, "icon_negative_cache_ttl_max", _MAX_TTL))
    except Exception:
        return _MAX_TTL


def _max_size() -> int:
    """Максимальный размер негативного кэша.

    Пытаемся получить из конфига, если доступен метод/атрибут
    `get_negative_cache_max_size` или `negative_cache_max_size`.
    Иначе используем дефолт.
    """
    try:
        getter = getattr(app_config, "get_negative_cache_max_size", None)
        if callable(getter):
            return max(1, int(getter()))
        raw = getattr(app_config, "negative_cache_max_size", _DEFAULT_MAX_SIZE)
        return max(1, int(raw))
    except Exception:
        return _DEFAULT_MAX_SIZE


def _max_strikes() -> int:
    """Максимальное число накапливаемых промахов (strikes) на ключ.

    Управляет ростом эффективного TTL. Делается конфигурируемым, чтобы
    ограничить агрессивность негативного кэширования.
    """
    try:
        getter = getattr(app_config, "get_negative_cache_max_strikes", None)
        if callable(getter):
            return max(1, int(getter()))
        raw = getattr(app_config, "negative_cache_max_strikes", _MAX_STRIKES)
        return max(1, int(raw))
    except Exception:
        return _MAX_STRIKES


def get_ttl(strikes: int) -> float:
    base = _base_ttl()
    max_t = _max_ttl()
    # Первый strike использует базовый TTL; рост начинается со второго
    ttl = base * (2 ** max(0, strikes - 1))
    return min(ttl, max_t)


class NegativeCache(BaseCache):
    """Расширяемый негативный кэш, совместимый с BaseCache.

    Поведение:
    - set(key, value, ttl=None): помечает ключ как негативный; value игнорируется.
    - get(key): возвращает True, если ключ негативен и TTL не истёк; иначе None.
    - invalidate(key): снимает метку с ключа; invalidate(None)/clear() — очистка всего кэша.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ts: dict[str, float] = {}  # ключ -> timestamp последней отметки
        self._strikes: dict[str, int] = {}  # ключ -> количество накопленных промахов
        # Генерации для предотвращения эффекта "висячих" элементов в кучах
        self._gen: dict[str, int] = {}  # ключ -> текущая версия записи
        # Куча по сроку истечения: (expire_ts, key, gen)
        self._expire_heap: list[tuple[float, str, int]] = []
        # Куча по времени отметки (для вытеснения самых старых при переполнении): (ts, key, gen)
        self._ts_heap: list[tuple[float, str, int]] = []

    # --- Конфиг ---
    @staticmethod
    def base_ttl() -> float:  # для тестов и ясности
        return _base_ttl()

    @staticmethod
    def max_ttl() -> float:
        return _max_ttl()

    @staticmethod
    def max_size() -> int:
        return _max_size()

    @staticmethod
    def max_strikes() -> int:
        return _max_strikes()

    @staticmethod
    def calc_ttl(strikes: int) -> float:
        return get_ttl(strikes)

    # --- BaseCache API ---
    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            ts = self._ts.get(key)
            if ts is None:
                return None
            strikes = self._strikes.get(key, 0)
            if now - ts < get_ttl(strikes):
                return True
            # Протухло — мягкая декрементация strike и очистка отметки
            # Инвалидируем все запланированные события через bump generation
            self._gen[key] = self._gen.get(key, 0) + 1
            if strikes > 0:
                self._strikes[key] = strikes - 1
            self._ts.pop(key, None)
            return None

    def set(self, key: str, value: Any, *, ttl: float | None = None) -> None:
        # ttl игнорируется: TTL управляется на основе strike и конфигурации
        now = time.time()
        with self._lock:
            # Инкрементальная очистка просроченных по куче истечений
            while self._expire_heap:
                exp_ts, k, g = self._expire_heap[0]
                if exp_ts > now:
                    break
                heapq.heappop(self._expire_heap)
                # Проверяем актуальность записи
                if self._gen.get(k) != g:
                    continue
                # Просрочено: удаляем отметку и мягко уменьшаем strikes
                self._ts.pop(k, None)
                s = self._strikes.get(k, 0)
                if s > 0:
                    self._strikes[k] = s - 1

            # Обновляем текущий ключ
            new_gen = self._gen.get(key, 0) + 1
            self._gen[key] = new_gen
            self._ts[key] = now
            self._strikes[key] = min(self._strikes.get(key, 0) + 1, _max_strikes())
            # Планируем срок истечения и добавляем в кучу
            expire_ts = now + get_ttl(self._strikes[key])
            heapq.heappush(self._expire_heap, (expire_ts, key, new_gen))
            # Добавляем в кучу по времени отметки для вытеснения самых старых
            heapq.heappush(self._ts_heap, (now, key, new_gen))

            # Контроль размера: вытесняем самые старые по ts при переполнении
            max_size = _max_size()
            while len(self._ts) > max_size and self._ts_heap:
                ts_old, k_old, g_old = heapq.heappop(self._ts_heap)
                if self._gen.get(k_old) != g_old:
                    continue  # устаревшая запись в куче
                # Удаляем ключ
                # Сначала bump generation, чтобы инвалидировать отложенные события
                self._gen[k_old] = self._gen.get(k_old, 0) + 1
                self._ts.pop(k_old, None)
                s = self._strikes.get(k_old, 0)
                if s > 0:
                    self._strikes[k_old] = s - 1

    def invalidate(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._ts.clear()
                self._strikes.clear()
                self._gen.clear()
                self._expire_heap.clear()
                self._ts_heap.clear()
                return
            # bump generation для инвалидизации событий
            self._gen[key] = self._gen.get(key, 0) + 1
            self._ts.pop(key, None)
            self._strikes.pop(key, None)

    # удобные методы
    def is_negative(self, key: str) -> bool:
        return bool(self.get(key))

    def mark_negative(self, key: str) -> None:
        self.set(key, True)

    def clear(self) -> None:
        self.invalidate(None)


# --- Глобальный экземпляр и функции-обёртки ---
negative_cache = NegativeCache()


def is_negative(key: str) -> bool:
    return negative_cache.is_negative(key)


def mark_negative(key: str) -> None:
    negative_cache.mark_negative(key)


def clear() -> None:
    negative_cache.clear()
