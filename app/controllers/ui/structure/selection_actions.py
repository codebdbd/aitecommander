from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QObject

from app.controllers.ui.types import (
    CategoryTilesControllerProtocol,
    LinksTableControllerProtocol,
    UIStateManagerProtocol,
)

logger = logging.getLogger(__name__)


class SelectionActions(QObject):
    """Encapsulates side effects when selecting structure items."""

    def __init__(
        self,
        *,
        controller,
        tree,
        tiles_controller: CategoryTilesControllerProtocol,
        main_window,
    ) -> None:
        parent = controller if isinstance(controller, QObject) else None
        super().__init__(parent=parent)
        self._controller = controller
        self._tree = tree
        self._tiles_controller = tiles_controller
        self._main = main_window

    # --- Tiles and business reactions ---
    def refresh_tiles(self, section_id: int) -> None:
        try:
            self._tiles_controller.refresh(int(section_id))
        except Exception:  # pragma: no cover - UI protection
            logger.exception("SelectionActions.refresh_tiles: controller refresh failed")

    def load_category_via_ui_state(self, category_id: int, *, source: str) -> None:
        ui_state = getattr(self._main, "ui_state", None)
        if isinstance(ui_state, UIStateManagerProtocol):
            try:
                ui_state.load_category(category_id, source=source)
            except Exception:  # pragma: no cover - UI protection
                logger.exception(
                    "SelectionActions.load_category_via_ui_state: ui_state.load_category failed"
                )
        else:
            logger.error(
                "UIStateManager not available in SelectionActions.load_category_via_ui_state"
            )

    # --- Table / focus helpers ---
    def clear_table_selection(self) -> None:
        table = getattr(self._main, "table", None)
        if table and hasattr(table, "clearSelection"):
            try:
                table.clearSelection()
            except Exception:  # pragma: no cover - UI protection
                logger.debug(
                    "SelectionActions.clear_table_selection: clearSelection failed",
                    exc_info=True,
                )

    def reload_links_without_stack_switch(self, category_id: int) -> None:
        controller = getattr(self._main, "links_table_controller", None)
        if isinstance(controller, LinksTableControllerProtocol):
            try:
                controller.reload(category_id)
            except Exception:  # pragma: no cover - UI protection
                logger.debug(
                    "SelectionActions.reload_links_without_stack_switch: reload failed",
                    exc_info=True,
                )
        else:
            logger.warning(
                "LinksTableController not available; skip reload for category #%s",
                category_id,
            )

    def focus_tree(self, *, use_scheduler: bool = True) -> None:
        from app.controllers.ui.state.task_scheduler import schedule_focus

        if use_scheduler:
            try:
                schedule_focus(lambda: self._tree.setFocus(), "structure_tree")
                return
            except Exception:  # pragma: no cover - UI protection
                logger.debug(
                    "SelectionActions.focus_tree: schedule_focus failed",
                    exc_info=True,
                )
        try:
            self._tree.setFocus()
        except Exception:  # pragma: no cover - UI protection
            logger.debug("SelectionActions.focus_tree: setFocus failed", exc_info=True)

    # --- Fallback utilities ---
    def current_ui_state(self) -> Optional[UIStateManagerProtocol]:
        ui_state = getattr(self._main, "ui_state", None)
        return ui_state if isinstance(ui_state, UIStateManagerProtocol) else None

    def links_table_controller(self) -> Optional[LinksTableControllerProtocol]:
        ctrl = getattr(self._main, "links_table_controller", None)
        return ctrl if isinstance(ctrl, LinksTableControllerProtocol) else None
