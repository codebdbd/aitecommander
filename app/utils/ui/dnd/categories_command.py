"""Команда перемещения нескольких категорий с использованием нового базового класса."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtCore import QItemSelectionModel, QTimer

from app.core.constants import AppConstants
from app.controllers.ui.undo.base import BaseCommand
from app.utils.ui.dnd.base_bulk_command import BaseBulkCommand
from app.utils.ui.dnd.command_utils import (
    _get_structure_business,
    _require_main,
    _require_structure_business,
)
from app.utils.ui.dnd.error_handler import BulkOperationErrorHandler

if TYPE_CHECKING:
    from app.controllers.business.structure_business import StructureBusinessLogic

import logging

logger = logging.getLogger(__name__)
error_handler = BulkOperationErrorHandler()


class MoveCategoriesCommand(BaseBulkCommand):
    """Batch moving multiple categories to one section with unified undo/redo."""

    def __init__(
        self,
        category_ids,
        new_section_id,
        base_row,
        main_window,
        *,
        name_overrides: dict[int, str] | None = None,
    ) -> None:
        super().__init__(f"Moving {len(category_ids)} categories", main_window, "category")
        self.category_ids = list(category_ids or [])
        if not isinstance(new_section_id, int):
            raise ValueError(f"new_section_id must be int, got {type(new_section_id).__name__}")
        self.new_section_id = new_section_id
        if not isinstance(base_row, int):
            raise ValueError(f"base_row must be int, got {type(base_row).__name__}")
        self.base_row = base_row
        self.name_overrides: dict[int, str] = dict(name_overrides or {})
        self._old_states: list[dict[str, Any]] = []  # [{id, name, section_id, position, icon_path}]
        self._new_states: list[dict[str, Any]] = []  # same format but with target section/position
        self._prepared = False
        self._last_moved_ids: set[int] = set()
        self._last_target_states: list[dict[str, Any]] = []
        self._preload_suspended = False

    def _prepare_data(self) -> None:
        """Prepare data for operation."""
        if self._prepared:
            return

        sb = _require_structure_business(self.main)

        # Load original states
        categories = sb.get_categories_by_ids(self.category_ids)
        category_map = {int(cat["id"]): cat for cat in categories}
        old_states = []

        for cid in self.category_ids:
            data = category_map.get(cid)

            if not data:
                logger.debug("Category %s not found, skipping", cid)
                continue

            old_states.append(
                {
                    "id": data["id"],
                    "name": data.get("name", ""),
                    "section_id": data.get("section_id"),
                    "position": data.get("position", 0),
                    "icon_path": data.get("icon_path", ""),
                }
            )

        # Stable order by original position, then by id
        old_states.sort(key=lambda x: (x.get("position", 0), x.get("id", 0)))

        # Form target states with name duplicate check in target section
        new_states = []

        offset = 0

        for st in old_states:
            cid = st["id"]
            name = self.name_overrides.get(cid, st.get("name", ""))

            # Name duplicates in target section — skip if not explicitly overridden
            try:
                if cid not in self.name_overrides and sb.has_duplicate_category(self.new_section_id, name, cid):
                    logger.debug(
                        "Duplicate category '%s' in target section %s, skipping id=%s",
                        name,
                        self.new_section_id,
                        cid,
                    )
                    continue
            except Exception:
                # If check fails — don't block operation, try to move
                pass

            ns = {
                "id": cid,
                "name": name,
                "section_id": self.new_section_id,
                "position": self.base_row + offset,
                "icon_path": st.get("icon_path", ""),
            }

            new_states.append(ns)
            offset += 1

        self._old_states = old_states
        self._new_states = new_states
        self._prepared = True

    def _execute_operation(self) -> bool:
        """Выполнение массового перемещения категорий."""
        try:
            self._prepare_data()
            self._maybe_suspend_preload_for_large_batch()

            # Apply new states
            self._apply_states(self._new_states)
            return True
        except Exception as e:
            self._resume_preload_after_ui()
            context = {
                "operation": "move_categories_batch",
                "category_ids": self.category_ids,
                "target_section": self.new_section_id
            }
            error_handler.handle_error(e, context)
            return False

    def _restore_original_state(self) -> bool:
        """Восстановление исходного состояния категорий."""
        try:
            self._maybe_suspend_preload_for_large_batch()
            # Restore original states
            self._apply_states(self._old_states)
            return True
        except Exception as e:
            self._resume_preload_after_ui()
            context = {
                "operation": "undo_move_categories_batch",
                "category_ids": self.category_ids,
                "original_section": self._old_states[0].get("section_id") if self._old_states else None
            }
            error_handler.handle_error(e, context)
            return False

    def _suppress_ui_signals(self, selection, tree):
        """Suppress selection and tree signals during batch operations."""
        from app.utils.ui.signal_suppression import suppress_ui_signals
        return suppress_ui_signals(selection, tree)

    def _restore_ui_signals(self, selection, tree, selection_state=True, tree_state=True):
        """Restore selection and tree signals after batch operations."""
        from app.utils.ui.signal_suppression import restore_ui_signals
        restore_ui_signals(selection, tree, selection_state, tree_state)

    def _extract_target_info(self, states):
        """Extract target IDs and section info from states."""
        try:
            target_ids = [
                int(st.get("id")) for st in states if isinstance(st.get("id"), int)
            ]
            targets = {
                st.get("section_id")
                for st in states
                if isinstance(st.get("section_id"), int)
            }
            single_target = len(targets) == 1
            target_section_id = next(iter(targets)) if single_target else None
            return target_ids, single_target, target_section_id
        except Exception:
            return [], False, None

    def _try_batch_move(self, sb, target_ids, target_section_id, states):
        """Attempt batch move operation, return (moved_ids, success)."""
        try:
            base_row = (
                min(int(st.get("position", 0) or 0) for st in states) if states else 0
            )
        except Exception:
            base_row = 0

        try:
            moved_ids = (
                sb.move_categories_batch(
                    target_ids, int(target_section_id), int(base_row)
                )
                or []
            )
            self._last_moved_ids.update(
                int(cid) for cid in moved_ids if isinstance(cid, int)
            )
            batch_done = bool(moved_ids)
            if batch_done and len(moved_ids) != len(target_ids):
                logger.debug(
                    "Some categories skipped by batch move (name duplicates in target section)"
                )
            return moved_ids, batch_done
        except Exception as exc:
            logger.debug(
                "Batch move failed, falling back to per-item updates: %s",
                exc,
                exc_info=True,
            )
            return [], False

    def _update_remaining_categories(self, sb, remaining_states, old_section_by_id):
        """Update categories that weren't moved in batch operation."""
        touched_override: set[int] = set()

        touched_override.update(
            {
                old_section_by_id.get(st.get("id"))
                for st in remaining_states
                if isinstance(old_section_by_id.get(st.get("id")), int)
            }
        )
        touched_override.update(
            {
                st.get("section_id")
                for st in remaining_states
                if isinstance(st.get("section_id"), int)
            }
        )

        for st in remaining_states:
            try:
                cid = st["id"]
                payload = {
                    "name": st.get("name", ""),
                    "section_id": st.get("section_id"),
                    "icon_path": st.get("icon_path", ""),
                    "position": st.get("position", 0),
                }
                sb.update_category(cid, payload)
                if isinstance(cid, int):
                    self._last_moved_ids.add(int(cid))
            except Exception as exc:
                logger.error(
                    "Error updating category %s during fallback move: %s",
                    st.get("id"),
                    exc,
                )
        return touched_override

    def _apply_states(self, states):
        """Apply states to the structure."""
        if not states:
            return

        main_window = _require_main(self.main)
        sb = _require_structure_business(main_window)
        struct = getattr(main_window, "structure", None)
        tree = getattr(struct, "tree", None)
        selection = getattr(struct, "selection_handler", None)

        self._last_moved_ids.clear()
        self._last_target_states = list(states)
        batch_started = False

        try:
            self._suppress_ui_signals(selection, tree)

            target_ids, single_target, target_section_id = self._extract_target_info(
                states
            )

            old_section_by_id = {
                st.get("id"): st.get("section_id")
                for st in getattr(self, "_old_states", [])
            }

            batch_started = self._try_begin_batch(sb)
            if single_target and isinstance(target_section_id, int):
                try:
                    setattr(sb, "_batch_preferred_section_id", int(target_section_id))
                except Exception:
                    pass

            touched_override = self._apply_states_core(
                sb,
                states,
                single_target,
                target_section_id,
                target_ids,
                old_section_by_id,
            )

            self._replace_touched_sections_safe(sb, touched_override)
        finally:
            if batch_started:
                self._try_end_batch(sb)
            self._restore_ui_signals(selection, tree)

    def _try_begin_batch(self, sb) -> bool:
        """Try to call begin_batch() and return True on success."""
        if hasattr(sb, "begin_batch") and callable(sb.begin_batch):
            try:
                sb.begin_batch()
                return True
            except Exception:
                return False
        return False

    def _try_end_batch(self, sb) -> None:
        """Try to call end_batch() safely."""
        try:
            sb.end_batch()
        except Exception:
            pass

    def _apply_states_core(
        self,
        sb,
        states,
        single_target: bool,
        target_section_id,
        target_ids,
        old_section_by_id,
    ):
        """Perform batch move or per-item updates and return touched sections set."""
        moved_ids, batch_done = [], False
        if single_target and isinstance(target_section_id, int):
            moved_ids, batch_done = self._try_batch_move(
                sb, target_ids, target_section_id, states
            )
            if self.name_overrides:
                for st in states:
                    cid = st.get("id")
                    if cid in self.name_overrides and cid in moved_ids:
                        name = st.get("name")
                        if name:
                            try:
                                sb.update_category(cid, {"name": name})
                            except Exception as exc:
                                logger.error("Error updating name for category %s: %s", cid, exc)

        moved_ids_set = set(moved_ids)
        remaining_states = [st for st in states if st.get("id") not in moved_ids_set]
        if remaining_states:
            return self._update_remaining_categories(
                sb, remaining_states, old_section_by_id
            )
        return None

    def _replace_touched_sections_safe(self, sb, touched_override) -> None:
        """Replace touched sections in event service with defensive logging."""
        if not touched_override:
            return
        normalized = {
            int(sid) for sid in touched_override if isinstance(sid, int) and sid > 0
        }
        if not normalized:
            return
        try:
            sb.event_service.replace_touched_sections(normalized)
        except Exception as exc:
            logger.debug(
                "replace_touched_sections failed in _apply_states: %s",
                exc,
                exc_info=True,
            )

    def _refresh_ui(self, affected_items: list = None) -> None:
        """Refresh UI after batch category moving."""
        target_states = (
            self._new_states if getattr(self, "_last_operation", "redo") != "undo" else self._old_states
        )
        first_focus_id = target_states[0]["id"] if target_states else None
        target_section_id = (
            target_states[0].get("section_id")
            if target_states and isinstance(target_states[0].get("section_id"), int)
            else self.new_section_id
        )

        main_window = _require_main(self.main)
        sb = getattr(main_window, "structure_business", None)
        if not sb:
            return
        sb = cast("StructureBusinessLogic", sb)

        struct = getattr(main_window, "structure", None)
        selection = getattr(struct, "selection_handler", None)
        tree = getattr(struct, "tree", None)

        large_batch = len(self.category_ids or []) >= AppConstants.LARGE_BATCH_THRESHOLD
        if large_batch:
            # Prioritize visible feedback (section/category focus) before expensive per-item tree moves.
            self._maybe_schedule_tree_focus(tree, first_focus_id, target_section_id)
            self._resume_preload_after_ui()

            def _deferred_model_moves() -> None:
                try:
                    self._suppress_ui_signals(selection, tree)
                    self._apply_tree_model_moves(tree)
                finally:
                    self._restore_ui_signals(selection, tree)

            try:
                QTimer.singleShot(0, _deferred_model_moves)
            except Exception:
                try:
                    self._suppress_ui_signals(selection, tree)
                    self._apply_tree_model_moves(tree)
                finally:
                    self._restore_ui_signals(selection, tree)
        else:
            try:
                self._suppress_ui_signals(selection, tree)
                self._apply_tree_model_moves(tree)
            finally:
                self._restore_ui_signals(selection, tree)

            self._maybe_schedule_tree_focus(tree, first_focus_id, target_section_id)
            self._resume_preload_after_ui()

        try:
            logger.info(
                "Switched focus to section %s after batch category moving",
                target_section_id,
            )
        except Exception:
            pass

        # Refresh category tiles and invalidate structure caches for all touched sections
        structure_ctrl = getattr(main_window, "structure", None)
        tree_manager = getattr(structure_ctrl, "tree_manager", None) if structure_ctrl else None
        touched_sections = {target_section_id}
        for st in getattr(self, "_old_states", []):
            sec = st.get("section_id")
            if isinstance(sec, int):
                touched_sections.add(sec)

        for sec_id in touched_sections:
            try:
                sb._invalidate_categories_cache(sec_id)
            except Exception:
                pass
            if tree_manager is not None:
                try:
                    fresh_cats = sb.get_categories(sec_id) or []
                    if hasattr(tree_manager, "replace_section_categories"):
                        tree_manager.replace_section_categories(sec_id, fresh_cats)
                except Exception:
                    pass

        if tree_manager is not None and hasattr(tree_manager, "refresh_section_tiles"):
            try:
                tree_manager.refresh_section_tiles(int(target_section_id), switch_view=False)
            except Exception:
                pass

    def _apply_tree_model_moves(self, tree) -> None:
        """Apply tree model moves."""
        if not tree or not self._last_target_states or not self._last_moved_ids:
            return
        try:
            model = tree.model() if hasattr(tree, "model") else None
            if not model or not hasattr(model, "move_category"):
                return
        except Exception:
            return
        touched_sections: set[int] = set()
        for st in self._last_target_states:
            cid = st.get("id")
            if not isinstance(cid, int) or cid not in self._last_moved_ids:
                continue
            section_id = st.get("section_id")
            if not isinstance(section_id, int):
                continue
            touched_sections.add(section_id)
            try:
                new_row = int(st.get("position", 0) or 0)
            except Exception:
                new_row = 0
            try:
                model.move_category(int(cid), int(section_id), int(new_row))
            except Exception:
                logger.debug(
                    "Tree model move_category failed for %s -> %s",
                    cid,
                    section_id,
                    exc_info=True,
                )
        if hasattr(model, "reorder_categories") and hasattr(self.main, "structure_business"):
            sb = getattr(self.main, "structure_business", None)
            if sb and hasattr(sb, "get_categories"):
                for sid in touched_sections:
                    try:
                        cats = sb.get_categories(sid) or []
                        ordered_ids = [
                            int(c["id"]) for c in cats if isinstance(c.get("id"), int)
                        ]
                        if ordered_ids:
                            model.reorder_categories(sid, ordered_ids)
                    except Exception:
                        pass

    def _maybe_schedule_tree_focus(self, tree, focus_category_id, target_section_id=None) -> None:
        """Schedule restoring tree selection and focus if possible."""
        if not (focus_category_id and tree):
            return
        section_id = (
            int(target_section_id)
            if isinstance(target_section_id, int)
            else int(self.new_section_id)
        )
        if len(self.category_ids or []) >= AppConstants.LARGE_BATCH_THRESHOLD:
            try:
                if tree and hasattr(tree, "model"):
                    model = tree.model()
                    if model and hasattr(model, "index_for"):
                        # First restore section focus immediately (best UX signal).
                        sec_index = model.index_for("section", section_id)
                        if sec_index and sec_index.isValid():
                            sel_model = tree.selectionModel()
                            if sel_model:
                                sel_model.setCurrentIndex(
                                    sec_index,
                                    QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
                                )
                            else:
                                tree.setCurrentIndex(sec_index)
                            try:
                                tree.scrollTo(sec_index)
                            except Exception:
                                pass
                            from app.utils.ui.focus import get_focus_manager

                            manager = get_focus_manager()
                            manager.set_focus(
                                tree,
                                widget_name="structure_tree",
                                origin="user_action",
                            )
                            logger.debug(
                                "MoveCategoriesCommand: immediate section focus applied for large batch -> section %s (count=%s)",
                                section_id,
                                len(self.category_ids or []),
                            )
                        # Then try category focus immediately only if already materialized.
                        cat_index = model.index_for("category", focus_category_id)
                        if cat_index and cat_index.isValid():
                            sel_model = tree.selectionModel()
                            if sel_model:
                                sel_model.setCurrentIndex(
                                    cat_index,
                                    QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
                                )
                            else:
                                tree.setCurrentIndex(cat_index)
                            try:
                                tree.scrollTo(cat_index)
                            except Exception:
                                pass
                            return
                        # Section focus already applied; don't fall back to delayed scheduler.
                        if sec_index and sec_index.isValid():
                            return
            except Exception as e:
                logger.debug("Immediate focus restore failed after batch move: %s", e)
        try:
            from app.controllers.ui.state.task_scheduler import (
                schedule_selection_restore,
            )

            def _restore_focus():
                try:
                    structure_ctrl = getattr(self.main, "structure", None)
                    selection_handler = getattr(structure_ctrl, "selection_handler", None)
                    if selection_handler is not None and hasattr(selection_handler, "_restore_category_selection"):
                        selection_handler._restore_category_selection(
                            int(focus_category_id),
                            target_section_id=int(section_id),
                        )
                except Exception as e:
                    logger.debug('Failed to restore focus after batch move: %s', e)

            schedule_selection_restore(_restore_focus, f"batch_move_{focus_category_id}")
        except Exception as e:
            logger.debug('Failed to schedule focus after batch move: %s', e)

    def _maybe_suspend_preload_for_large_batch(self) -> None:
        """Pause structure preload to avoid DB/UI contention for large DnD batches."""
        if self._preload_suspended:
            return
        if len(self.category_ids or []) < AppConstants.LARGE_BATCH_THRESHOLD:
            return
        sb = _get_structure_business(self.main)
        if sb is None:
            return
        try:
            sb.suspend_structure_preload(duration_ms=AppConstants.PRELOAD_SUSPEND_DURATION_MS, reason="dnd-move-categories")
            self._preload_suspended = True
        except Exception:
            logger.debug(
                "MoveCategoriesCommand: failed to suspend structure preload",
                exc_info=True,
            )

    def _resume_preload_after_ui(self) -> None:
        if not self._preload_suspended:
            return
        sb = _get_structure_business(self.main)
        if sb is None:
            self._preload_suspended = False
            return
        try:
            sb.resume_structure_preload(delay_ms=AppConstants.PRELOAD_RESUME_DELAY_MS, reason="dnd-move-categories")
        except Exception:
            logger.debug(
                "MoveCategoriesCommand: failed to resume structure preload",
                exc_info=True,
            )
        finally:
            self._preload_suspended = False


class MergeCategoriesCommand(BaseCommand):
    """Merge a source category into a target category with full Undo/Redo."""

    def __init__(
        self, source_category_id: int, target_category_id: int, main_window: object
    ) -> None:
        super().__init__("Merge categories", main_window)
        self.source_id = int(source_category_id)
        self.target_id = int(target_category_id)
        self._source_cat_data: dict[str, Any] = {}
        self._source_links_data: list[dict[str, Any]] = []
        self._moved_link_ids: list[int] = []
        self._deleted_link_ids: list[int] = []
        self._target_section_id: int | None = None
        self._source_section_id: int | None = None
        self._prepared = False

    def _prepare_data(self) -> None:
        if self._prepared:
            return
        sb = _require_structure_business(self.main)
        lb = getattr(self.main, "links_business", None)

        s_data = sb.get_category_data(self.source_id)
        if not s_data:
            raise ValueError(f"Source category {self.source_id} not found")
        t_data = sb.get_category_data(self.target_id)
        if not t_data:
            raise ValueError(f"Target category {self.target_id} not found")

        self._source_cat_data = dict(s_data)
        self._source_section_id = int(s_data.get("section_id", 0))
        self._target_section_id = int(t_data.get("section_id", 0))

        if lb is not None:
            source_links = lb.get_links(self.source_id) or []
            self._source_links_data = [dict(l) for l in source_links]
            target_links = lb.get_links(self.target_id) or []
            target_keys = {
                (
                    str(l.get("name", "")),
                    str(l.get("url", "")),
                    str(l.get("args", "")),
                )
                for l in target_links
            }
            self._moved_link_ids = []
            self._deleted_link_ids = []
            for sl in source_links:
                s_key = (
                    str(sl.get("name", "")),
                    str(sl.get("url", "")),
                    str(sl.get("args", "")),
                )
                lid = int(sl["id"])
                if s_key in target_keys:
                    self._deleted_link_ids.append(lid)
                else:
                    self._moved_link_ids.append(lid)
                    target_keys.add(s_key)
        self._prepared = True

    def redo(self) -> None:
        self._prepare_data()
        sb = _require_structure_business(self.main)
        lb = getattr(self.main, "links_business", None)
        db = getattr(getattr(sb, "structure_service", None), "db", None)

        def _do_redo():
            if lb is not None:
                links_svc = getattr(lb, "links", lb)
                if self._deleted_link_ids:
                    links_svc.batch_delete_links(self._deleted_link_ids)
                if self._moved_link_ids:
                    links_svc.move_links_bulk(self._moved_link_ids, self.target_id)
            sb.delete_category(self.source_id)

        if db and hasattr(db, "transaction"):
            with db.transaction():
                _do_redo()
        else:
            _do_redo()

        self._refresh_ui()

    def undo(self) -> None:
        if not self._source_cat_data:
            return
        sb = _require_structure_business(self.main)
        lb = getattr(self.main, "links_business", None)
        db = getattr(getattr(sb, "structure_service", None), "db", None)

        def _do_undo():
            # 1. Restore category record
            if db and hasattr(db, "connection"):
                db.connection.execute(
                    """
                    INSERT OR REPLACE INTO category (id, section_id, name, position, icon_path)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        self.source_id,
                        self._source_cat_data.get("section_id"),
                        self._source_cat_data.get("name"),
                        self._source_cat_data.get("position", 0),
                        self._source_cat_data.get("icon_path", ""),
                    ),
                )
            # 2. Move transferred links back
            if lb is not None:
                links_svc = getattr(lb, "links", lb)
                if self._moved_link_ids:
                    links_svc.move_links_bulk(self._moved_link_ids, self.source_id)
                # 3. Restore deleted duplicate links
                if self._deleted_link_ids:
                    for ldata in self._source_links_data:
                        if int(ldata.get("id", 0)) in self._deleted_link_ids:
                            db.connection.execute(
                                """
                                INSERT OR REPLACE INTO link (id, category_id, name, url, type, icon_path, notes, position, args, is_favorite)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    ldata["id"],
                                    self.source_id,
                                    ldata.get("name", ""),
                                    ldata.get("url", ""),
                                    ldata.get("type", "web"),
                                    ldata.get("icon_path", ""),
                                    ldata.get("notes", ""),
                                    ldata.get("position", 0),
                                    ldata.get("args", ""),
                                    ldata.get("is_favorite", 0),
                                ),
                            )

        if db and hasattr(db, "transaction"):
            with db.transaction():
                _do_undo()
        else:
            _do_undo()

        self._refresh_ui()

    def _refresh_ui(self) -> None:
        sb = _get_structure_business(self.main)
        if sb is not None:
            for sec_id in {self._source_section_id, self._target_section_id}:
                if isinstance(sec_id, int):
                    try:
                        sb._invalidate_categories_cache(sec_id)
                    except Exception:
                        pass
        facade = getattr(self.main, "_facade", None)
        if (
            facade
            and hasattr(facade, "refresh_structure_after_import")
            and self._target_section_id
        ):
            facade.refresh_structure_after_import(sb, self._target_section_id)
        elif sb and self._target_section_id:
            try:
                sb.section_selected.emit(int(self._target_section_id))
            except Exception:
                pass
        target_cat = self._source_category_id if getattr(self, "_last_operation", "") == "undo" else self._target_category_id
        target_sec = self._source_section_id if getattr(self, "_last_operation", "") == "undo" else self._target_section_id
        if target_cat:
            structure_ctrl = getattr(self.main, "structure", None)
            selection_handler = getattr(structure_ctrl, "selection_handler", None)
            if selection_handler and hasattr(selection_handler, "_restore_category_selection"):
                selection_handler._restore_category_selection(int(target_cat), target_section_id=target_sec)

