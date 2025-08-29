# app/utils/ui/updates.py
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from app.interfaces import SupportsUpdates


@contextmanager
def suspend_updates(window: SupportsUpdates) -> Iterator[None]:
    """Временно отключает обновления окна/виджета на время блока `with`.

    Пример:
        with suspend_updates(self.window):
            ...  # тяжелая операция обновления UI
    """
    window.setUpdatesEnabled(False)
    try:
        yield
    finally:
        try:
            window.setUpdatesEnabled(True)
        except Exception:
            # Безопасность: не даем упасть при восстановлении
            pass
