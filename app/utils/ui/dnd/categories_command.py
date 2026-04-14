"""Команда перемещения нескольких категорий с использованием нового базового класса."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtCore import QTimer

from app.utils.ui.dnd.base_bulk_command import BaseBulkCommand
from app.utils.ui.dnd.error_handler import BulkOperationErrorHandler

if TYPE_CHECKING:
    from app.controllers.business.structure_business import StructureBusinessLogic
    from app.views.windows.main_window_protocol import MainWindowProtocol

import logging

logger = logging.getLogger(__name__)
error_handler = BulkOperationErrorHandler()


def _require_main(main: object | None) -> MainWindowProtocol:
    if main is None:
        raise RuntimeError("Command requires an attached main window")
    return cast("MainWindowProtocol", main)


def _require_structure_business(main: object | None) -> StructureBusinessLogic:
    main_window = _require_main(main)
    structure_business = getattr(main_window, "structure_business", None)
    if structure_business is None:
        raise RuntimeError("Main window is missing structure_business")
    return cast("StructureBusinessLogic", structure_business)


def _get_structure_business(main: object | None) -> StructureBusinessLogic | None:
    try:
        return _require_structure_business(main)
    except RuntimeError:
        return None


class MoveCategoriesCommand(BaseBulkCommand):
    """Batch moving multiple categories to one section with unified undo/redo."""

    def __init__(self, category_ids, new_section_id, base_row, main_window) -> None:
        super().__init__(f"Moving {len(category_ids)} categories", main_window, "category")
        self.category_ids = list(category_ids or [])
        self.new_section_id = (
            int(new_section_id) if isinstance(new_section_id, int) else new_section_id
        )
        self.base_row = int(base_row) if isinstance(base_row, int) else 0
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
        old_states = []

        for cid in self.category_ids:
            data = sb.get_category_data(cid)

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
            name = st.get("name", "")

            # Name duplicates in target section — skip
            try:
                if sb.has_duplicate_category(self.new_section_id, name, cid):
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

        large_batch = len(self.category_ids or []) >= 20
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
        for st in self._last_target_states:
            cid = st.get("id")
            if not isinstance(cid, int) or cid not in self._last_moved_ids:
                continue
            section_id = st.get("section_id")
            if not isinstance(section_id, int):
                continue
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

    def _maybe_schedule_tree_focus(self, tree, focus_category_id, target_section_id=None) -> None:
        """Schedule restoring tree selection and focus if possible."""
        if not (focus_category_id and tree):
            return
        section_id = (
            int(target_section_id)
            if isinstance(target_section_id, int)
            else int(self.new_section_id)
        )
        if len(self.category_ids or []) >= 20:
            try:
                if tree and hasattr(tree, "model"):
                    model = tree.model()
                    if model and hasattr(model, "index_for"):
                        # First restore section focus immediately (best UX signal).
                        sec_index = model.index_for("section", section_id)
                        if sec_index and sec_index.isValid():
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
                    if tree and hasattr(tree, 'model'):
                        model = tree.model()
                        if model and hasattr(model, 'index_for'):
                            cat_index = model.index_for('category', focus_category_id)
                            if cat_index and cat_index.isValid():
                                tree.setCurrentIndex(cat_index)
                                from app.utils.ui.focus import get_focus_manager
                                manager = get_focus_manager()
                                manager.set_focus(
                                    tree,
                                    widget_name="structure_tree",
                                    origin="user_action",
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
        if len(self.category_ids or []) < 20:
            return
        sb = _get_structure_business(self.main)
        if sb is None:
            return
        try:
            sb.suspend_structure_preload(duration_ms=3500, reason="dnd-move-categories")
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
            sb.resume_structure_preload(delay_ms=900, reason="dnd-move-categories")
        except Exception:
            logger.debug(
                "MoveCategoriesCommand: failed to resume structure preload",
                exc_info=True,
            )
        finally:
            self._preload_suspended = False
