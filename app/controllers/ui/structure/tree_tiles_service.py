from __future__ import annotations

import logging
from typing import TYPE_CHECKING


from app.utils.ui.qt.roles import get_tree_tuple

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from .tree_management import TreeManagement


class TreeTilesService:
    """Grouped operations for updating category tiles."""

    def __init__(self, manager: "TreeManagement") -> None:
        self._manager = manager

    # --- Public API -----------------------------------------------------
    def refresh_section_tiles(self, section_id: int) -> None:
        try:
            self._manager.tiles_controller.refresh(int(section_id))
        except (ValueError, RuntimeError):
            logger.exception(
                "TreeTilesService.refresh_section_tiles: controller refresh failed (expected)"
            )

    def clear_tiles(self) -> None:
        try:
            self._manager.tiles_controller.clear()
        except Exception:
            logger.exception(
                "TreeTilesService.clear_tiles: clear failed",
                exc_info=True,
            )

    def refresh_by_current_tree_selection(self) -> None:
        try:
            current = self._manager.tree.currentIndex()
            meta = get_tree_tuple(current, 0) if current and current.isValid() else None
            if meta and meta[0] == "section":
                self.refresh_section_tiles(meta[1])
            else:
                self.clear_tiles()
        except Exception:
            logger.exception(
                "TreeTilesService.refresh_by_current_tree_selection: failed to refresh"
            )

    def refresh_after_category_edit(self) -> None:
        try:
            cur = self._manager.tree.currentIndex()
            if cur and cur.isValid():
                meta = get_tree_tuple(cur, 0)
                if meta and meta[0] == "category":
                    parent = cur.parent()
                else:
                    parent = cur
                section_meta = (
                    get_tree_tuple(parent, 0)
                    if parent and parent.isValid()
                    else None
                )
                if section_meta and section_meta[0] == "section":
                    self.refresh_section_tiles(section_meta[1])
        except Exception:
            logger.exception(
                "TreeTilesService.refresh_after_category_edit: refresh failed"
            )

    def refresh_after_section_edit(self) -> None:
        try:
            cur = self._manager.tree.currentIndex()
            if cur and cur.isValid():
                meta = get_tree_tuple(cur, 0)
                if meta and meta[0] == "section":
                    self.refresh_section_tiles(meta[1])
        except Exception:
            logger.exception(
                "TreeTilesService.refresh_after_section_edit: refresh failed"
            )

