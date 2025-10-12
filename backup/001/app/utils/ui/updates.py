# app/utils/ui/updates.py
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
import logging

from app.interfaces import SupportsUpdates

logger = logging.getLogger(__name__)


@contextmanager
def suspend_updates(window: SupportsUpdates) -> Iterator[None]:
    """Временно отключает обновления окна/виджета на время блока `with`.

    Пример:
        with suspend_updates(self.window):
            ...  # тяжелая операция обновления UI

    Примечание:
        Ошибки при восстановлении обновлений (вызове `setUpdatesEnabled(True)`) не
        прокидываются наверх, но логируются на уровне ERROR для последующей диагностики.
    """
    window.setUpdatesEnabled(False)
    try:
        yield
    finally:
        try:
            window.setUpdatesEnabled(True)
        except Exception as exc:
            # Логируем, чтобы не терять информацию о потенциально "замороженном" UI
            logger.error(
                "Failed to restore updates via setUpdatesEnabled(True): %s", exc
            )
