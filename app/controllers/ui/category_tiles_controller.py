# app/controllers/ui/category_tiles_controller.py

import logging
from typing import Optional, Protocol, List, Dict

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
        try:
            if not isinstance(section_id, int) or section_id <= 0:
                logger.warning("CategoryTilesController.refresh: invalid section_id=%s", section_id)
                return

            categories = self.business.get_categories(int(section_id))
            # Основной путь: через ui_state (централизует переключение стека)
            self.ui_state.switch_to_category_tiles(categories or [])
            # Опционально: прямое обновление, если виджет подключён
            if self._tiles is not None:
                self._tiles.set_categories(categories or [])
        except Exception:
            logger.exception(
                "CategoryTilesController.refresh: ошибка обновления плиток раздела #%s",
                section_id,
            )

    def clear(self) -> None:
        """Очистить плитки категорий (показать пустой набор)."""
        try:
            self.ui_state.switch_to_category_tiles([])
            if self._tiles is not None:
                self._tiles.set_categories([])
        except Exception:
            logger.exception("CategoryTilesController.clear: ошибка очистки плиток категорий")
