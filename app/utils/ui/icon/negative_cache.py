"""
Единый модуль негативного кэширования путей иконок.

API:
- is_negative(key) -> bool
- mark_negative(key) -> None
- maybe_decay_strikes(key) -> None
- get_ttl(strikes) -> float
- clear() -> None

Ключ формируется на верхнем уровне (например, f"{theme}:{icon_name.lower()}").
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from app.config_data import app_config

_NEGATIVE_CACHE: dict[str, float] = {}
_NEG_STRIKES: dict[str, int] = {}
_LOCK = threading.Lock()

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


def is_negative(key: str) -> bool:
    now = time.time()
    with _LOCK:
        ts = _NEGATIVE_CACHE.get(key)
        if ts is None:
            return False
        strikes = _NEG_STRIKES.get(key, 0)
        if now - ts < get_ttl(strikes):
            return True
        # Протухло — мягкая декрементация strike и очистка отметки
        if strikes > 0:
            _NEG_STRIKES[key] = strikes - 1
        _NEGATIVE_CACHE.pop(key, None)
        return False


def mark_negative(key: str) -> None:
    now = time.time()
    with _LOCK:
        # Периодическая очистка протухших ключей (дешёвая, по месту записи)
        if _NEGATIVE_CACHE:
            expired = []
            for k, ts in _NEGATIVE_CACHE.items():
                strikes = _NEG_STRIKES.get(k, 0)
                if now - ts >= get_ttl(strikes):
                    expired.append(k)
            if expired:
                for k in expired:
                    # мягкая декрементация strikes, как и в is_negative()
                    s = _NEG_STRIKES.get(k, 0)
                    if s > 0:
                        _NEG_STRIKES[k] = s - 1
                    _NEGATIVE_CACHE.pop(k, None)

        # Обновляем текущий ключ
        _NEGATIVE_CACHE[key] = now
        _NEG_STRIKES[key] = min(_NEG_STRIKES.get(key, 0) + 1, _max_strikes())

        # Контроль размера: при переполнении вытесняем самые старые записи
        max_size = _max_size()
        if len(_NEGATIVE_CACHE) > max_size:
            # Отсортировать по времени (старые первыми)
            to_evict = len(_NEGATIVE_CACHE) - max_size
            for k, _ in sorted(_NEGATIVE_CACHE.items(), key=lambda kv: kv[1])[:to_evict]:
                _NEGATIVE_CACHE.pop(k, None)
                # strikes можно слегка уменьшить, чтобы ускорить исчезновение шума
                s = _NEG_STRIKES.get(k, 0)
                if s > 0:
                    _NEG_STRIKES[k] = s - 1


def maybe_decay_strikes(key: str) -> None:
    # Хелпер для внешних модулей, если нужно мягко уменьшить strikes
    with _LOCK:
        strikes = _NEG_STRIKES.get(key, 0)
        if strikes > 0:
            _NEG_STRIKES[key] = strikes - 1


def clear() -> None:
    with _LOCK:
        _NEGATIVE_CACHE.clear()
        _NEG_STRIKES.clear()
