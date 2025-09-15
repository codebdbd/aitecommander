# app/controllers/structure_modules/batch_manager.py

from __future__ import annotations

import logging
from typing import Callable, Optional, Set


class BatchUpdateCoordinator:
    """Координатор batch-режима для консолидации множественных обновлений.

    Обязанности:
    - Вести состояние batch-режима
    - Накапливать затронутые разделы (для дозагрузки категорий)
    - По завершении: выполнить дозагрузки и одну коалесцированную перезагрузку структуры

    Все эффекты передаются через коллбеки (DI), чтобы не зависеть от Qt/бизнес-слоя напрямую.
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        *,
        on_load_categories: Optional[Callable[[int], None]] = None,
        on_invalidate: Optional[Callable[[], None]] = None,
        on_schedule_reload: Optional[Callable[[int], None]] = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._in_batch: bool = False
        self._touched_sections: Set[int] = set()
        self._on_load_categories = on_load_categories
        self._on_invalidate = on_invalidate
        self._on_schedule_reload = on_schedule_reload

    # --- Состояние ---
    @property
    def in_batch(self) -> bool:
        return self._in_batch

    def begin(self) -> None:
        self._in_batch = True
        self._touched_sections.clear()

    def touch_section(self, section_id: Optional[int]) -> None:  # type: ignore[name-defined]
        try:
            if isinstance(section_id, int) and section_id > 0:
                self._touched_sections.add(int(section_id))
        except Exception as ex:
            self._logger.debug(
                "batch: failed to add touched section id=%s: %s", section_id, ex, exc_info=True
            )

    def end(self) -> None:
        # Единожды загрузим категории для всех затронутых разделов
        try:
            if self._on_load_categories:
                for sid in list(self._touched_sections):
                    try:
                        self._on_load_categories(sid)
                    except Exception as exc:
                        self._logger.debug(
                            "batch: load_categories_async failed for %s: %s", sid, exc, exc_info=True
                        )
        except Exception as exc:
            self._logger.debug("batch: iteration failed: %s", exc, exc_info=True)
        finally:
            self._touched_sections.clear()
            self._in_batch = False

        # Одна коалесцированная перезагрузка структуры сферы
        try:
            if self._on_invalidate:
                self._on_invalidate()
            if self._on_schedule_reload:
                self._on_schedule_reload(0)
        except Exception as exc:
            self._logger.debug("batch: schedule structure reload failed: %s", exc, exc_info=True)
