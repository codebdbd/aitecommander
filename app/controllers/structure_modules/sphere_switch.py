# app/controllers/structure_modules/sphere_switch.py

from __future__ import annotations

import logging
import time
from typing import Optional


class SphereSwitchCoordinator:
    """Инкапсулирует логику переключения текущей сферы.

    Отвечает за:
    - метрики времени переключения
    - токен переключения (отбрасывание устаревших задач)
    - установку флага подавления восстановления категории
    - частичную инвалидацию по старой сфере
    - эмиссию сигнала active_sphere_changed
    """

    def __init__(self, controller, logger: Optional[logging.Logger] = None) -> None:
        self.controller = controller
        self.logger = logger or logging.getLogger(__name__)

    def set_current_sphere(self, sphere_id: int) -> None:
        try:
            old_sphere_id = getattr(self.controller, "current_sphere_id", None)
            # Если сфера не меняется — ничего не делаем
            if old_sphere_id == sphere_id:
                self.logger.debug("set_current_sphere: сфера не изменилась; пропуск")
                return

            # Метрика: момент старта переключения
            try:
                self.controller._last_switch_started_ms = time.monotonic()
            except (RuntimeError, OverflowError):
                self.controller._last_switch_started_ms = None

            # Устанавливаем новую сферу
            self.controller.current_sphere_id = sphere_id

            # Обновляем токен переключения сферы
            try:
                self.controller._switch_token = int(getattr(self.controller, "_switch_token", 0)) + 1
            except (ValueError, TypeError):
                self.controller._switch_token = 1

            # Подавляем разовое восстановление категории (тяжёлая загрузка)
            setattr(self.controller, "_suppress_category_restore_once", True)

            # Частичная инвалидация по старой сфере (если уместно)
            if old_sphere_id != sphere_id:
                try:
                    self.controller.cache_manager.invalidate(f"sphere_{old_sphere_id}")
                except Exception:
                    # Инвалидация носит вспомогательный характер
                    self.logger.debug("sphere_switch: invalidate old sphere cache failed", exc_info=True)

            self.logger.info("Установлена текущая сфера: %s", sphere_id)
            # Эмиссия сигнала
            try:
                self.controller.active_sphere_changed.emit(sphere_id)
            except Exception:
                # Не ломаем переключение при проблемах со слотами
                self.logger.debug("sphere_switch: failed to emit active_sphere_changed", exc_info=True)
        except Exception as e:
            # Пробрасывать не будем, пусть обработает общий слой ошибок контроллера при вызове
            self.logger.error("Ошибка переключения сферы: %s", e, exc_info=True)
            raise
