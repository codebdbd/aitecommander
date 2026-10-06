"""Команда перемещения ссылок с использованием нового базового класса."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QItemSelectionModel

from app.config_data.runtime_config import get_table_selection_restore_delay_ms
from app.utils.common import get_value
from app.utils.ui.dnd.base_bulk_command import BaseBulkCommand
from app.utils.ui.dnd.error_handler import BulkOperationErrorHandler

if TYPE_CHECKING:
    pass

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

    def __init__(
        self,
        link_ids,
        new_category_id,
        main_window,
        *,
        name_overrides: dict[int, str] | None = None,
        replacements: dict[int, int] | None = None,
    ) -> None:
        super().__init__(f"Moving {len(list(link_ids))} links", main_window, "link")
        self.link_ids = [int(lid) for lid in link_ids]
        self.new_category_id = int(new_category_id)
        self.name_overrides: dict[int, str] = dict(name_overrides or {})
        self.replacements: dict[int, int] = dict(replacements or {})
        self._old_states: list[dict[str, Any]] = []
        self._new_states: list[dict[str, Any]] = []
        self._replaced_states: dict[int, dict[str, Any]] = {}
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
            lid = candidate.get("id")
            if lid is not None and int(lid) in self.replacements:
                target_id = self.replacements[int(lid)]
                target_row = next((r for r in existing_links if r.get("id") == target_id), None)
                if target_row:
                    self._replaced_states[target_id] = dict(target_row)
                    candidate["position"] = target_row.get("position", start_pos + offset)
                else:
                    candidate["position"] = start_pos + offset
            else:
                candidate["position"] = start_pos + offset
            if lid is not None and int(lid) in self.name_overrides:
                candidate["name"] = self.name_overrides[int(lid)]
            elif lid is not None and int(lid) in self.replacements:
                pass
            elif self._is_duplicate(candidate, existing_links):
                from app.services.structure_share_service import generate_unique_name
                existing_names = [get_value(l, "name", "") for l in existing_links]
                candidate["name"] = generate_unique_name(existing_names, candidate.get("name", ""))
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
            if self._replaced_states:
                links_business = getattr(self.main, "links_business", None)
                del_ids = list(self._replaced_states.keys())
                if links_business and hasattr(links_business, "links"):
                    links_business.links.batch_delete_links(del_ids)
            self._execute_batch_operation(self._new_states)
            self._invalidate_links_cache()
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
            if self._replaced_states:
                links_business = getattr(self.main, "links_business", None)
                restore_rows = list(self._replaced_states.values())
                if links_business and hasattr(links_business, "links"):
                    links_business.links.batch_create_or_update_links(restore_rows)
            self._invalidate_links_cache()
            return True
        except Exception as exc:
            context = {
                "operation": "undo_move_links",
                "link_ids": self.link_ids,
                "original_category": self.old_category_id
            }
            error_handler.handle_error(exc, context)
            return False

    def _invalidate_links_cache(self) -> None:
        lb = getattr(self.main, "links_business", None)
        if lb is not None and hasattr(lb, "invalidate_cache"):
            try:
                lb.invalidate_cache()
            except Exception:
                pass

    def _execute_batch_operation(self, states):
        if not states:
            return
        links_business = getattr(self.main, "links_business", None)
        if not links_business or not hasattr(links_business, "links"):
            raise RuntimeError("links_business is not available in main window")
        
        try:
            # Use batch_update to preserve positions and avoid duplicate issues.
            links_business.links.batch_update(states)
            for st in states:
                lid = st.get("id")
                st_name = st.get("name")
                if isinstance(lid, int) and st_name and hasattr(links_business.links, "repo"):
                    try:
                        links_business.links.repo.connection.execute(
                            "UPDATE link SET name = ? WHERE id = ?", (st_name, lid)
                        )
                    except Exception:
                        pass
        except Exception as exc:
            logger.error("Error during batch link operation: %s", exc, exc_info=True)
            raise

    def _refresh_ui(self, affected_items: list = None) -> None:
        """Обновление UI после перемещения ссылок."""
        self._invalidate_links_cache()
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
                target_sphere = None
                current_sphere = getattr(structure_business, 'current_sphere_id', None) if structure_business else None
                if structure_business and hasattr(structure_business, 'get_category_hierarchy'):
                    hierarchy = structure_business.get_category_hierarchy(int(focus_category_id))
                    if hierarchy and isinstance(hierarchy, dict):
                        target_sphere = hierarchy.get("sphere_id")

                if (
                    isinstance(target_sphere, int)
                    and target_sphere > 0
                    and target_sphere != current_sphere
                ):
                    struct_ctrl = getattr(self.main, "structure_controller", None) or getattr(
                        self.main, "structure", None
                    )
                    if struct_ctrl and hasattr(struct_ctrl, "switch_sphere"):
                        struct_ctrl.switch_sphere(
                            target_sphere, item_to_select=("category", int(focus_category_id))
                        )
                        self._schedule_focus_on_links(self.link_ids)
                        return

                if structure_business and hasattr(structure_business, 'select_category'):
                    try:
                        ui_state = getattr(self.main, "ui_state", None) or getattr(self.main, "ui_state_manager", None)
                        if ui_state and hasattr(ui_state, "load_category"):
                            ui_state.load_category(
                                int(focus_category_id),
                                source="MoveLinksCommand._refresh_ui",
                                force_reload=True,
                            )
                        else:
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
                                        sel_model = tree.selectionModel()
                                        if sel_model:
                                            # Clear old selection first, then select new one
                                            sel_model.setCurrentIndex(
                                                cat_index,
                                                QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
                                            )
                                        else:
                                            tree.setCurrentIndex(cat_index)

                        # Then focus on the moved link in table
                        self._schedule_focus_on_links(self.link_ids)
                        links_ctrl = getattr(self.main, "links", None) or getattr(self.main, "links_controller", None)
                        if links_ctrl and hasattr(links_ctrl, "table"):
                            table = getattr(links_ctrl, "table", None)
                            if table and hasattr(table, "load_links"):
                                lb = getattr(self.main, "links_business", None)
                                fresh_links = lb.get_links(int(focus_category_id)) if lb else []
                                table.load_links(fresh_links)
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

    def _schedule_focus_on_links(self, link_ids: list[int]) -> None:
        """Schedule focus on links after category is loaded."""
        if not link_ids:
            return
        
        if not hasattr(self.main, 'links_actions'):
            return
            
        if hasattr(self.main.links_actions, 'focus_on_links'):
            try:
                from app.controllers.ui.state.task_scheduler import (
                    schedule_selection_restore,
                )
                delay_ms = get_table_selection_restore_delay_ms(100)
                schedule_selection_restore(
                    lambda: self.main.links_actions.focus_on_links(link_ids),
                    f"batch_focus_{link_ids[0]}",
                    delay=delay_ms,
                )
            except Exception as e:
                logger.debug("Failed to schedule focus on links %s: %s", link_ids, e)
        else:
            self._schedule_focus_on_link(link_ids[0])

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
                f"focus_link_{link_id}",
                delay=delay_ms,
            )
        except Exception as e:
            logger.debug("Failed to schedule focus on link %s: %s", link_id, e)
