# lru_policy.py
"""
LRU-политика кэширования для иконок.

Назначение:
- Отслеживает порядок использования ключей.
- Удаляет наименее недавно использованные при переполнении.
- Синхронизируется с внешним словарём кэша.

Соответствует PEP 8.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

from .lock_manager import acquire_lru_lock


class LRUPolicy:
    """Потокобезопасная реализация LRU-политики."""

    def __init__(self, maxsize: int) -> None:
        self.maxsize = max(1, int(maxsize))  # защита от 0 и отрицательных
        self.access_order: OrderedDict[str, None] = OrderedDict()
        # Используем централизованную систему блокировок
        # self._lock заменен на lock_manager

    # --- API доступа ---

    def access(self, key: str) -> None:
        """Зарегистрировать обращение к ключу (перенести в конец)."""
        with acquire_lru_lock():
            self.access_order[key] = None
            self.access_order.move_to_end(key)

    def evict_if_needed(
        self, cache: Dict[str, Any], key: str
    ) -> Tuple[bool, Optional[str]]:
        """Проверить переполнение и вернуть ключ для удаления.

        Возвращает:
            (True, ключ) — если надо удалить элемент.
            (False, None) — если удаление не требуется.
        """
        with acquire_lru_lock():
            if len(cache) >= self.maxsize and key not in cache:
                try:
                    old_key, _ = self.access_order.popitem(last=False)
                    return True, old_key
                except KeyError:
                    # рассинхрон между cache и access_order
                    return True, None
            return False, None

    def remove(self, key: str) -> None:
        """Удалить ключ из порядка доступа."""
        with acquire_lru_lock():
            self.access_order.pop(key, None)

    def sync_with_cache(self, cache: Dict[str, Any]) -> None:
        """Синхронизировать порядок доступа с фактическим содержимым кэша."""
        with acquire_lru_lock():
            # удалить отсутствующие
            keys_to_remove = [k for k in self.access_order if k not in cache]
            for k in keys_to_remove:
                self.access_order.pop(k, None)

            # добавить новые
            for k in cache:
                if k not in self.access_order:
                    self.access_order[k] = None

    def size(self) -> int:
        """Текущее количество отслеживаемых ключей."""
        with acquire_lru_lock():
            return len(self.access_order)
