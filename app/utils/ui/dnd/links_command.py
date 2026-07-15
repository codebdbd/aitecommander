"""Команда перемещения ссылок с использованием нового базового класса."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from app.utils.ui.dnd.base_bulk_command import BaseBulkCommand
from app.utils.ui.dnd.error_handler import BulkOperationErrorHandler
from app.utils.ui.dnd.command_utils import (
    _require_main,
    _require_structure_business,
    _get_structure_business,
)
from app.utils.common import get_value
from app.config_data.runtime_config import get_table_selection_restore_delay_ms

if TYPE_CHECKING:
    from app.controllers.business.structure_business import StructureBusinessLogic
    from app.views.windows.main_window_protocol import MainWindowProtocol

import logging

logger = logging.getLogger(__name__)
error_handler = BulkOperationErrorHandler()


def _reload_links_via_controller(main_window, category_ids) -> None:
    ctrl = getattr(main_window, "links_table_controller", None)
    if ctrl is None or not hasattr(ctrl, "reload"):
        logger.warning("LinksTableController unavailable for reload")
        return
    for cat_id in set(category_ids or []):
        if isinstance(cat_id, int) and cat_id > 0:
            try:
                ctrl.reload(cat_id)
            except Exception as exc:
                logger.warning(
                    "LinksTableController.reload failed for category %s: %s",
                    cat_id,
                    exc,
                )


class MoveLinksCommand(BaseBulkCommand):
    """Move one or more links to another category with undo/redo support."""

    def __init__(self, link_ids, new_category_id, main_window) -> None:
        super().__init__(f"Moving {len(list(link_ids))} links", main_window, "link")
        self.link_ids = [int(lid) for lid in link_ids]
        self.new_category_id = int(new_category_id)
        self._old_states: list[dict[str, Any]] = []
        self._new_states: list[dict[str, Any]] = []
        self.old_category_id: int | None = None
        self._old_category_ids: set[int] = set()
        self._prepared = False

    def _prepare_data(self) -> None:
        if self._prepared:
            return
        links_business = getattr(self.main, "links_business", None)
        if not links_business:
            raise RuntimeError("links_business is not available in main window")
        links_service = getattr(links_business, "links", None)
        if not links_service:
            raise RuntimeError("links_business.links service is unavailable")

        self._old_states.clear()
        for lid in self.link_ids:
            try:
                link_data = links_service.get_link_by_id(int(lid)) or {}
            except Exception as exc:
                context = {"link_id": lid, "operation": "get_link", "attempted_operation": "move"}
                error_handler.handle_error(exc, context)
                raise ValueError(f"Failed to load link #{lid}: {exc}") from exc
            if not link_data:
                raise ValueError(f"Link with id {lid} not found")
            self._old_states.append(dict(link_data))

        if not self._old_states:
            raise ValueError("No valid links supplied for move operation")

        origin_category_raw = self._old_states[0].get("category_id")
        self.old_category_id = int(origin_category_raw) if origin_category_raw else None
        self._old_category_ids = {
            int(link.get("category_id"))
            for link in self._old_states
            if isinstance(link.get("category_id"), int)
        }

        try:
            start_pos = links_business.get_next_position(self.new_category_id)
        except Exception:
            start_pos = 0

        try:
            existing = links_business.get_links(self.new_category_id) or []
            existing_links = [dict(row) for row in existing]
        except Exception:
            existing_links = []

        prepared: list[dict[str, Any]] = []
        for offset, original in enumerate(self._old_states):
            candidate = dict(original)
            candidate["category_id"] = self.new_category_id
            candidate["position"] = start_pos + offset
            if not self._is_duplicate(candidate, existing_links):
                prepared.append(candidate)
                existing_links.append(candidate)
        self._new_states = prepared
        self._prepared = True

    def _is_duplicate(self, candidate, links):
        for link in links:
            if (
                get_value(link, "name", "") == get_value(candidate, "name", "")
                and get_value(link, "url", "") == get_value(candidate, "url", "")
                and get_value(link, "args", "") == get_value(candidate, "args", "")
            ):
                return True
        return False

    def _execute_operation(self) -> bool:
        """Выполнение перемещения ссылок."""
        try:
            self._execute_batch_operation(self._new_states)
            return True
        except Exception as exc:
            context = {
                "operation": "move_links",
                "link_ids": self.link_ids,
                "target_category": self.new_category_id
            }
            error_handler.handle_error(exc, context)
            return False

    def _restore_original_state(self) -> bool:
        """Восстановление исходного состояния ссылок."""
        try:
            self._execute_batch_operation(self._old_states)
            return True
        except Exception as exc:
            context = {
                "operation": "undo_move_links",
                "link_ids": self.link_ids,
                "original_category": self.old_category_id
            }
            error_handler.handle_error(exc, context)
            return False

    def _execute_batch_operation(self, states):
        if not states:
            return
        links_business = getattr(self.main, "links_business", None)
        if not links_business or not hasattr(links_business, "links"):
            raise RuntimeError("links_business is not available in main window")
        
        try:
            # Use batch_update to preserve positions and avoid duplicate issues.
            links_business.links.batch_update(states)
        except Exception as exc:
            logger.error("Error during batch link operation: %s", exc, exc_info=True)
            raise

    def _refresh_ui(self, affected_items: list = None) -> None:
        """Обновление UI после перемещения ссылок."""
        categories_to_update = set(self._old_category_ids)
        categories_to_update.add(self.new_category_id)

        operation = getattr(self, "_last_operation", "redo")
        focus_category_id = self.new_category_id
        if operation == "undo":
            if isinstance(self.old_category_id, int):
                focus_category_id = int(self.old_category_id)
            elif self._old_states:
                first_old_category = self._old_states[0].get("category_id")
                if isinstance(first_old_category, int):
                    focus_category_id = int(first_old_category)

        # Switch to focus category and focus on moved link
        if focus_category_id and self.link_ids:
            first_link_id = self.link_ids[0] if self.link_ids else None
            if first_link_id:
                # Switch category in tree and load links
                structure_business = getattr(self.main, 'structure_business', None)
                if structure_business and hasattr(structure_business, 'select_category'):
                    try:
                        # Load links for new category
                        structure_business.select_category(int(focus_category_id))
                        
                        # Set visual selection in tree
                        struct = getattr(self.main, 'structure', None)
                        if struct:
                            tree = getattr(struct, 'tree', None)
                            if tree and hasattr(tree, 'model'):
                                model = tree.model()
                                if model and hasattr(model, 'index_for'):
                                    cat_index = model.index_for('category', int(focus_category_id))
                                    if cat_index and cat_index.isValid():
                                        tree.setCurrentIndex(cat_index)
                        
                        # Then focus on the moved link in table
                        self._schedule_focus_on_link(first_link_id)
                        return
                    except Exception as e:
                        logger.debug(
                            "Failed to select category %s: %s", focus_category_id, e
                        )
        
        # Fallback: just reload categories without focus
        try:
            if categories_to_update:
                _reload_links_via_controller(self.main, categories_to_update)
        except Exception as exc:
            logger.debug(
                "Failed to refresh links for categories %s: %s", categories_to_update, exc
            )

    def _schedule_focus_on_link(self, link_id: int) -> None:
        """Schedule focus on link after category is loaded."""
        if not link_id:
            return
        
        if not hasattr(self.main, 'links_actions'):
            return
        
        if not hasattr(self.main.links_actions, 'focus_on_link'):
            return
        
        try:
            from app.controllers.ui.state.task_scheduler import (
                schedule_selection_restore,
            )
            delay_ms = get_table_selection_restore_delay_ms(100)
            schedule_selection_restore(
                lambda: self.main.links_actions.focus_on_link(link_id),
                link_id,
                delay=delay_ms,
            )
        except Exception as e:
            logger.debug("Failed to schedule focus on link %s: %s", link_id, e)
