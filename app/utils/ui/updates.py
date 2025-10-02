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
        Для уже показанных top-level окон обновления *не* отключаются, чтобы избежать
        визуальных артефактов (например, фантомного контура при разворачивании).
    """

    should_suspend = True
    try:
        is_window_fn = getattr(window, "isWindow", None)
        is_visible_fn = getattr(window, "isVisible", None)
        is_window = bool(is_window_fn()) if callable(is_window_fn) else False
        is_visible = bool(is_visible_fn()) if callable(is_visible_fn) else False
        if is_window and is_visible:
            should_suspend = False
    except Exception:
        # Если проверка не удалась, по умолчанию пытаемся отключить обновления
        should_suspend = True

    if not should_suspend:
        yield
        return

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
