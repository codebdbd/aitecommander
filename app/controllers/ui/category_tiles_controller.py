# app/controllers/ui/category_tiles_controller.py

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CategoryTilesController:
    """Единая точка управления плитками категорий.

    Отвечает за загрузку категорий раздела и обновление плиток без
    дублирования логики в разных местах (TreeManagement, SelectionHandling).
    """

    def __init__(self, main_window, structure_business):
        self.main = main_window
        self.business = structure_business

    def refresh(self, section_id: int) -> None:
        """Обновить плитки для указанного раздела.

        - Получает категории раздела из бизнес-логики
        - Передает их в UI через UIStateManager
        - Не эмитит бизнес-сигналы (не вызывает select_section)
        """
        try:
            if not isinstance(section_id, int) or section_id <= 0:
                logger.warning("CategoryTilesController.refresh: invalid section_id=%s", section_id)
                return

            ui_state = getattr(self.main, "ui_state", None)
            if not ui_state:
                logger.warning("CategoryTilesController.refresh: UIStateManager is not available")
                return

            business = self.business or getattr(self.main, "structure_business", None)
            if not business:
                logger.warning("CategoryTilesController.refresh: StructureBusinessLogic is not available")
                return

            categories = business.get_categories(int(section_id))
            ui_state.switch_to_category_tiles(categories or [])
        except Exception:
            logger.exception(
                "CategoryTilesController.refresh: ошибка обновления плиток раздела #%s",
                section_id,
            )

    def clear(self) -> None:
        """Очистить плитки категорий (показать пустой набор)."""
        try:
            ui_state = getattr(self.main, "ui_state", None)
            if ui_state:
                ui_state.switch_to_category_tiles([])
            else:
                logger.warning("CategoryTilesController.clear: UIStateManager is not available")
        except Exception:
            logger.exception("CategoryTilesController.clear: ошибка очистки плиток категорий")
