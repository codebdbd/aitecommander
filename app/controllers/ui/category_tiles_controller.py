# app/controllers/ui/category_tiles_controller.py

import logging
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


class CategoryTilesLike(Protocol):
    def set_categories(self, categories: list[dict]) -> None: ...


class CategoryTilesController:
    """Single control point for category tiles.

    Required dependencies: `ui_state`, `structure_business`.
    Direct interaction with tiles widget is optional and can be attached via
    `attach_tiles_widget()`.
    """

    def __init__(self, ui_state, structure_business, *, main_window=None):
        if ui_state is None or structure_business is None:
            raise ValueError(
                "CategoryTilesController requires ui_state and structure_business"
            )
        self.ui_state = ui_state
        self.business = structure_business
        self._tiles: Optional[CategoryTilesLike] = None

    def attach_tiles_widget(self, tiles_widget: CategoryTilesLike) -> None:
        """Optionally set tiles widget for direct update operations."""
        self._tiles = tiles_widget

    def refresh(self, section_id: int) -> None:
        """Refresh tiles for the specified section."""
        if not isinstance(section_id, int) or section_id <= 0:
            logger.warning(
                "CategoryTilesController.refresh: invalid section_id=%s", section_id
            )
            return

        try:
            categories = self.business.get_categories(int(section_id))
        except (ValueError, RuntimeError):
            # Expected data retrieval errors — log and finish without raising
            logger.exception(
                "CategoryTilesController.refresh: get_categories failed for section #%s",
                section_id,
            )
            return

        # Primary path: via ui_state (centralizes stack switching)
        try:
            self.ui_state.switch_to_category_tiles(categories or [])
        except (ValueError, RuntimeError):
            logger.exception(
                "CategoryTilesController.refresh: ui_state switch failed for section #%s",
                section_id,
            )
            return
        # Optional: direct update if widget is attached
        if self._tiles is not None:
            try:
                self._tiles.set_categories(categories or [])
            except (ValueError, RuntimeError):
                logger.exception(
                    "CategoryTilesController.refresh: tiles.set_categories failed for section #%s",
                    section_id,
                )
                return

    def clear(self) -> None:
        """Clear category tiles (show empty set)."""
        try:
            self.ui_state.switch_to_category_tiles([])
        except (ValueError, RuntimeError):
            logger.exception("CategoryTilesController.clear: ui_state switch failed")
            return
        if self._tiles is not None:
            try:
                self._tiles.set_categories([])
            except (ValueError, RuntimeError):
                logger.exception(
                    "CategoryTilesController.clear: tiles.set_categories failed"
                )
                return
