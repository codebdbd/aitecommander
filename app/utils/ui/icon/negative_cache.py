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
_MAX_STRIKES: int = 5


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
    with _LOCK:
        _NEGATIVE_CACHE[key] = time.time()
        _NEG_STRIKES[key] = min(_NEG_STRIKES.get(key, 0) + 1, _MAX_STRIKES)


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
