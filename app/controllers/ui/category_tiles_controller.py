# app/controllers/ui/category_tiles_controller.py

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CategoryTilesController:
    """Единая точка управления плитками категорий.

    Отвечает за загрузку категорий раздела и обновление плиток без
    дублирования логики в разных местах (TreeManagement, SelectionHandling).
    """

    def __init__(self, ui_state, structure_business, tiles_widget: Optional[object] = None, *, main_window=None):
        # main_window принят для обратной совместимости и не используется
        # В тестах допускается отсутствие зависимостей; методы делают проверки и логируют предупреждения
        self.ui_state = ui_state
        self.business = structure_business
        # tiles_widget хранится для явной зависимости и потенциального использования
        self.tiles = tiles_widget

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

            ui_state = self.ui_state
            if not ui_state:
                logger.warning("CategoryTilesController.refresh: UIStateManager is not available")
                return

            business = self.business
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
            ui_state = self.ui_state
            if ui_state:
                ui_state.switch_to_category_tiles([])
            else:
                logger.warning("CategoryTilesController.clear: UIStateManager is not available")
        except Exception:
            logger.exception("CategoryTilesController.clear: ошибка очистки плиток категорий")
