"""
In-memory кэш профилей браузеров с учётом таймаута актуальности.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional


class ProfileCache:
    """Простой in-memory кэш профилей с таймаутом актуальности.

    Хранит профили по ключу браузера и метку времени последнего обновления.
    """

    def __init__(self, timeout_seconds: int = 300):
        self._cache: Dict[str, List[Dict]] = {}
        self._last_update: Dict[str, float] = {}
        self._timeout = timeout_seconds

    # Базовые операции
    def set(self, browser_key: str, profiles: List[Dict]) -> None:
        self._cache[browser_key] = profiles
        self._last_update[browser_key] = time.time()

    def get(self, browser_key: str) -> Optional[List[Dict]]:
        """Возвращает кэш без проверки свежести (может быть устаревшим)."""
        return self._cache.get(browser_key)

    def get_if_fresh(self, browser_key: str) -> Optional[List[Dict]]:
        """Возвращает список профилей, если он ещё свежий, иначе None."""
        if browser_key not in self._cache or browser_key not in self._last_update:
            return None
        if time.time() - self._last_update[browser_key] >= self._timeout:
            return None
        return self._cache[browser_key]

    def clear(self) -> None:
        self._cache.clear()
        self._last_update.clear()

    def load_initial(self, data: Optional[Dict[str, List[Dict]]]) -> None:
        """Инициализирует кэш готовыми данными (считает их свежими на текущий момент)."""
        if not data:
            return
        now = time.time()
        for key, profiles in data.items():
            if isinstance(profiles, list):
                self._cache[key] = profiles
                self._last_update[key] = now

    # Вспомогательные
    @property
    def timeout(self) -> int:
        return self._timeout

    def is_fresh(self, browser_key: str) -> bool:
        if browser_key not in self._last_update:
            return False
        return time.time() - self._last_update[browser_key] < self._timeout
