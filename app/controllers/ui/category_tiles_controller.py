# app/controllers/ui/category_tiles_controller.py

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CategoryTilesController:
    """Единая точка управления плитками категорий."""

    def __init__(self, ui_state, structure_business, tiles_widget: Optional[object] = None, *, main_window=None):
        if ui_state is None or structure_business is None:
            raise ValueError("CategoryTilesController requires ui_state and structure_business")
        self.ui_state = ui_state
        self.business = structure_business
        self.tiles = tiles_widget

    def refresh(self, section_id: int) -> None:
        """Обновить плитки для указанного раздела."""
        try:
            if not isinstance(section_id, int) or section_id <= 0:
                logger.warning("CategoryTilesController.refresh: invalid section_id=%s", section_id)
                return

            categories = self.business.get_categories(int(section_id))
            self.ui_state.switch_to_category_tiles(categories or [])
        except Exception:
            logger.exception(
                "CategoryTilesController.refresh: ошибка обновления плиток раздела #%s",
                section_id,
            )

    def clear(self) -> None:
        """Очистить плитки категорий (показать пустой набор)."""
        try:
            self.ui_state.switch_to_category_tiles([])
        except Exception:
            logger.exception("CategoryTilesController.clear: ошибка очистки плиток категорий")
