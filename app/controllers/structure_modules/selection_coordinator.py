# app/controllers/structure_modules/selection_coordinator.py

from __future__ import annotations

import logging
from typing import Optional


class SelectionCoordinator:
    """Инкапсулирует выбор раздела/категории и связанные побочные эффекты (сигналы, лог)."""

    def __init__(self, controller, logger: Optional[logging.Logger] = None) -> None:
        self.controller = controller
        self.logger = logger or logging.getLogger(__name__)

    def select_section(self, section_id: int) -> None:
        # Получаем категории через публичный API контроллера, чтобы сохранить возможные декораторы и кэш-политику
        categories = self.controller.get_categories(section_id)
        try:
            self.controller.section_selected.emit(section_id)
        except Exception:
            # Не ломаем выбор из‑за проблем со слотами
            self.logger.debug("selection: failed to emit section_selected", exc_info=True)
        self.logger.debug(
            "Выбран раздел %s с %s категориями", section_id, len(categories or [])
        )

    def select_category(self, category_id: int) -> None:
        try:
            self.controller.category_selected.emit(category_id)
        except Exception:
            self.logger.debug("selection: failed to emit category_selected", exc_info=True)
        self.logger.debug("Выбрана категория %s", category_id)
