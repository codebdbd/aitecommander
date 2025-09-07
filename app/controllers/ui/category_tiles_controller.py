# app/controllers/ui/category_tiles_controller.py

import logging
from typing import Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


class CategoryTilesLike(Protocol):
    def set_categories(self, categories: List[Dict]) -> None: ...


class CategoryTilesController:
    """Единая точка управления плитками категорий.

    Обязательные зависимости: `ui_state`, `structure_business`.
    Прямая работа с виджетом плиток опциональна и может быть подключена через
    `attach_tiles_widget()`.
    """

    def __init__(self, ui_state, structure_business, *, main_window=None):
        if ui_state is None or structure_business is None:
            raise ValueError("CategoryTilesController requires ui_state and structure_business")
        self.ui_state = ui_state
        self.business = structure_business
        self._tiles: Optional[CategoryTilesLike] = None

    def attach_tiles_widget(self, tiles_widget: CategoryTilesLike) -> None:
        """Опционально задать виджет плиток для прямых операций обновления."""
        self._tiles = tiles_widget

    def refresh(self, section_id: int) -> None:
        """Обновить плитки для указанного раздела."""
        if not isinstance(section_id, int) or section_id <= 0:
            logger.warning("CategoryTilesController.refresh: invalid section_id=%s", section_id)
            return

        try:
            categories = self.business.get_categories(int(section_id))
        except (ValueError, RuntimeError):
            # Ожидаемые ошибки получения данных — журналируем и завершаем без исключения
            logger.exception("CategoryTilesController.refresh: get_categories failed for section #%s", section_id)
            return

        # Основной путь: через ui_state (централизует переключение стека)
        try:
            self.ui_state.switch_to_category_tiles(categories or [])
        except (ValueError, RuntimeError):
            logger.exception("CategoryTilesController.refresh: ui_state switch failed for section #%s", section_id)
            return
        # Опционально: прямое обновление, если виджет подключён
        if self._tiles is not None:
            try:
                self._tiles.set_categories(categories or [])
            except (ValueError, RuntimeError):
                logger.exception("CategoryTilesController.refresh: tiles.set_categories failed for section #%s", section_id)
                return

    def clear(self) -> None:
        """Очистить плитки категорий (показать пустой набор)."""
        try:
            self.ui_state.switch_to_category_tiles([])
        except (ValueError, RuntimeError):
            logger.exception("CategoryTilesController.clear: ui_state switch failed")
            return
        if self._tiles is not None:
            try:
                self._tiles.set_categories([])
            except (ValueError, RuntimeError):
                logger.exception("CategoryTilesController.clear: tiles.set_categories failed")
                return
