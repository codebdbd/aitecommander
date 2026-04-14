# app/controllers/structure/tree_management.py

import logging
import time
from typing import Any, Optional

from PyQt6.QtCore import QModelIndex, QObject, Qt, pyqtSlot

from app.config_data.runtime_config import (
    get_selection_restore_delay_ms,
    is_tree_alphabetical_sort_enabled,
    is_tree_skip_sort_if_sorted,
)
from app.controllers.ui.state.task_scheduler import schedule_selection_restore
from app.controllers.ui.types import (
    CategoryTilesControllerProtocol,
    StructureTreeModelProtocol,
)
from app.utils.ui.qt.roles import get_tree_tuple

from .tree_snapshot_service import TreeSnapshotService
from .tree_state_service import TreeStateService
from .tree_tiles_service import TreeTilesService
from .tree_update_service import TreeUpdateService

logger = logging.getLogger(__name__)


class TreeManagement(QObject):
    def __init__(self, controller, category_tiles_controller) -> None:
        parent = controller if isinstance(controller, QObject) else None
        super().__init__(parent=parent)
        self.controller = controller
        self.tree = controller.tree
        self.icon_handler = controller.icon_handler
        # Explicit mandatory dependency: category tiles controller
        if category_tiles_controller is None:
            raise ValueError(
                "TreeManagement requires a non-None category_tiles_controller"
            )
        if not isinstance(category_tiles_controller, CategoryTilesControllerProtocol):
            raise TypeError(
                "category_tiles_controller must implement CategoryTilesControllerProtocol"
            )
        self.tiles_controller: CategoryTilesControllerProtocol = (
            category_tiles_controller
        )

        # Explicit reference to tree model and contract check
        try:
            model_getter = self.tree.model
            raw_model = model_getter() if callable(model_getter) else None
        except AttributeError:
            raw_model = None
        if raw_model is None:
            raise ValueError("TreeManagement requires a valid tree model")
        if not isinstance(raw_model, StructureTreeModelProtocol):
            raise TypeError(
                "TreeManagement requires model implementing StructureTreeModelProtocol"
            )
        self.model: StructureTreeModelProtocol = raw_model
        self._state = TreeStateService(
            controller=controller,
            tree=self.tree,
            model=self.model,
        )
        self._snapshot = TreeSnapshotService(manager=self, model=self.model)
        self._next_snapshot_mode: str | None = None
        self._tiles = TreeTilesService(manager=self)
        self._updates = TreeUpdateService(
            manager=self,
            tree=self.tree,
            model=self.model,
        )

    @pyqtSlot(list)
    def _on_structure_loaded(self, sections_data: list[dict[str, Any]]) -> None:
        t0 = time.perf_counter()
        sphere_id = None
        initial_load = self._is_initial_structure_load()
        try:
            sb = self._get_structure_business()
            sphere_id = getattr(sb, "current_sphere_id", None) if sb else None
        except Exception:
            sphere_id = None

        # Save current selection and expansion state before model reload
        t_sel0 = time.perf_counter()
        current_selection = (
            None if initial_load else self._state.capture_current_selection()
        )
        t_sel1 = time.perf_counter()
        expanded_state = {} if initial_load else self._state.capture_expanded_state()
        t_exp1 = time.perf_counter()

        t_sort0 = time.perf_counter()
        sections_data = self._sort_sections_data(sections_data)
        sections_data = sections_data or []
        t_sort1 = time.perf_counter()

        sections_count = len(sections_data)
        categories_count = 0
        try:
            categories_count = sum(
                len(s.get("categories") or [])
                for s in sections_data
                if isinstance(s, dict)
            )
        except Exception:
            categories_count = -1

        logger.info(
            "[Perf] TreeManagement.on_structure_loaded sphere=%s initial_load=%s sections=%s categories=%s capture_selection=%.2fms capture_expanded=%.2fms sort=%.2fms pre_schedule_total=%.2fms",
            sphere_id,
            initial_load,
            sections_count,
            categories_count,
            (t_sel1 - t_sel0) * 1000.0,
            (t_exp1 - t_sel1) * 1000.0,
            (t_sort1 - t_sort0) * 1000.0,
            (t_sort1 - t0) * 1000.0,
        )

        scheduled_at = time.perf_counter()
        snapshot_mode = self._consume_next_snapshot_mode()
        self._snapshot.schedule_snapshot(
            sections_data,
            on_success=lambda: self._handle_snapshot_success(
                sections_data,
                expanded_state,
                current_selection,
                sphere_id=sphere_id,
                scheduled_at=scheduled_at,
            ),
            on_error=self._handle_snapshot_error,
            mode=snapshot_mode,
        )

    def _sort_sections_data(
        self, sections_data: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]]:
        if not sections_data:
            return []
        try:
            sort_enabled = is_tree_alphabetical_sort_enabled(False)
        except Exception:
            sort_enabled = False
        if not sort_enabled:
            logger.debug(
                "TreeManagement._on_structure_loaded: alphabetical sort disabled"
            )
            return sections_data
        try:
            sb = self._get_structure_business()
            if sb and getattr(sb, "_suppress_tree_sort_once", False):
                try:
                    sb._suppress_tree_sort_once = False
                except Exception:
                    pass
                logger.info(
                    "TreeManagement._on_structure_loaded: skipped alphabetical sort (batch mode)"
                )
                return sections_data
        except Exception:
            pass
        try:
            def _section_key(section: dict[str, Any]) -> str:
                return str(section.get("name", "")).lower()

            def _category_key(category: dict[str, Any]) -> str:
                return str(category.get("name", "")).lower()

            try:
                skip_if_sorted = is_tree_skip_sort_if_sorted(True)
            except Exception:
                skip_if_sorted = True

            if skip_if_sorted and self._is_sections_sorted(sections_data):
                logger.debug(
                    "TreeManagement._on_structure_loaded: data already sorted, skip sort"
                )
                return sections_data

            sorted_sections = sorted(sections_data, key=_section_key)
            for section in sorted_sections:
                cats = section.get("categories")
                if not isinstance(cats, list):
                    continue
                try:
                    cats.sort(key=_category_key)
                except Exception:
                    logger.debug(
                        "TreeManagement._on_structure_loaded: category sort failed for section %s",
                        section.get("id"),
                    )
            logger.info(
                "TreeManagement._on_structure_loaded: applied alphabetical sort (sections=%s)",
                len(sorted_sections),
            )
            return sorted_sections
        except (TypeError, AttributeError, KeyError):
            logger.exception("TreeManagement._on_structure_loaded: sections sort error")
            return sections_data or []

    @staticmethod
    def _is_sections_sorted(sections: list[dict[str, Any]]) -> bool:
        prev_sec = ""
        for section in sections:
            name = str(section.get("name", "")).lower()
            if name < prev_sec:
                return False
            prev_sec = name
            cats = section.get("categories") or []
            if not isinstance(cats, list):
                continue
            prev_cat = ""
            for cat in cats:
                cname = str(cat.get("name", "")).lower()
                if cname < prev_cat:
                    return False
                prev_cat = cname
        return True

    def _handle_snapshot_error(self) -> None:
        logger.exception(
            "TreeManagement._on_structure_loaded: model failed to accept snapshot"
        )

    def _handle_snapshot_success(
        self,
        sections_data: list[dict[str, Any]],
        expanded_state: Any,
        current_selection: Any,
        *,
        sphere_id: Any = None,
        scheduled_at: float | None = None,
    ) -> None:
        t0 = time.perf_counter()
        self._clear_tiles_if_empty(sections_data)
        t1 = time.perf_counter()
        self._after_snapshot_applied(expanded_state, current_selection)
        t2 = time.perf_counter()
        self._select_first_item_if_needed()
        t3 = time.perf_counter()
        self._reset_suppression_flag()
        t4 = time.perf_counter()
        self._finalize_initial_load_if_needed()
        t5 = time.perf_counter()
        queue_to_success_ms = (
            (t5 - scheduled_at) * 1000.0
            if isinstance(scheduled_at, (int, float))
            else -1.0
        )
        logger.info(
            "[Perf] TreeManagement.snapshot_success sphere=%s queue_to_success=%.2fms clear_tiles=%.2fms after_snapshot=%.2fms select_first_if_needed=%.2fms reset_flags=%.2fms finalize_initial=%.2fms total=%.2fms",
            sphere_id,
            queue_to_success_ms,
            (t1 - t0) * 1000.0,
            (t2 - t1) * 1000.0,
            (t3 - t2) * 1000.0,
            (t4 - t3) * 1000.0,
            (t5 - t4) * 1000.0,
            (t5 - t0) * 1000.0,
        )

    def _clear_tiles_if_empty(self, sections_data: list[dict[str, Any]]) -> None:
        try:
            if not sections_data:
                self.clear_tiles()
        except Exception:
            logger.exception(
                "TreeManagement._on_structure_loaded: error clearing tiles on empty structure"
            )

    def request_next_snapshot_mode(self, mode: str) -> None:
        try:
            normalized = str(mode or "").strip().lower()
        except Exception:
            normalized = ""
        if normalized not in {"fast_switch", "full_restore"}:
            normalized = "fast_switch"
        self._next_snapshot_mode = normalized

    def _consume_next_snapshot_mode(self) -> str:
        mode = self._next_snapshot_mode or "fast_switch"
        self._next_snapshot_mode = None
        return mode

    def _select_first_item_if_needed(self) -> None:
        try:
            sb = self._get_structure_business()
            if sb and getattr(sb, "_suppress_category_restore_once", False):
                self._state.select_first_item()
        except Exception:
            logger.debug(
                "TreeManagement._on_structure_loaded: failed to select first item",
                exc_info=True,
            )

    def _reset_suppression_flag(self) -> None:
        try:
            sb = self._get_structure_business()
            if sb and getattr(sb, "_suppress_category_restore_once", False):
                sb._suppress_category_restore_once = False
        except Exception:
            logger.debug(
                "TreeManagement._on_structure_loaded: failed to reset suppression flag",
                exc_info=True,
            )

    def _finalize_initial_load_if_needed(self) -> None:
        main = getattr(self.controller, "main", None)
        if main is not None and getattr(main, "_first_structure_load", False):
            main._first_structure_load = False
            try:
                if getattr(self.tree, "viewport", None):
                    self.tree.viewport().update()
            except Exception:
                self.tree.update()

    def _get_structure_business(self):
        return getattr(self.controller, "business", None) or getattr(
            self.controller, "structure_business", None
        )

    def _is_initial_structure_load(self) -> bool:
        main = getattr(self.controller, "main", None)
        return bool(main is not None and getattr(main, "_first_structure_load", False))

    def _after_snapshot_applied(
        self, expanded_state: Any, current_selection: Any
    ) -> None:
        """Restore expanded nodes and selection after snapshot reload."""
        t0 = time.perf_counter()
        initial_load = self._is_initial_structure_load()
        try:
            if not initial_load:
                self._state.restore_expanded_state(expanded_state)
        except Exception:
            logger.exception(
                "TreeManagement._after_snapshot_applied: failed to restore expanded state"
            )
        t1 = time.perf_counter()

        try:
            sb = getattr(self.controller, "business", None) or getattr(
                self.controller, "structure_business", None
            )
            if sb and getattr(sb, "_suppress_category_restore_once", False):
                t_pop0 = time.perf_counter()
                try:
                    if (
                        not initial_load
                        and hasattr(self.model, "populate_first_section_if_deferred")
                    ):
                        self.model.populate_first_section_if_deferred()
                except Exception:
                    logger.debug(
                        "TreeManagement._after_snapshot_applied: failed to pre-populate first section",
                        exc_info=True,
                    )
                t_pop1 = time.perf_counter()
                self._state.select_first_item()
                sb._suppress_category_restore_once = False
                self._finalize_first_load()
                t2 = time.perf_counter()
                logger.info(
                    "[Perf] TreeManagement.after_snapshot restore_expanded=%.2fms prepopulate_target=%.2fms selection_path=suppress_first total=%.2fms",
                    (t1 - t0) * 1000.0,
                    (t_pop1 - t_pop0) * 1000.0,
                    (t2 - t0) * 1000.0,
                )
                return
        except Exception:
            logger.debug(
                "TreeManagement._after_snapshot_applied: suppress flag handling failed",
                exc_info=True,
            )

        if initial_load:
            self._state.select_first_item()
            self._finalize_first_load()
            t2 = time.perf_counter()
            logger.info(
                "[Perf] TreeManagement.after_snapshot initial_load restore_expanded=%.2fms selection_and_finalize=%.2fms total=%.2fms",
                (t1 - t0) * 1000.0,
                (t2 - t1) * 1000.0,
                (t2 - t0) * 1000.0,
            )
            return

        target_selection = None
        if (
            isinstance(current_selection, tuple)
            and len(current_selection) == 2
            and current_selection[0] in {"section", "category"}
        ):
            target_selection = current_selection
        else:
            target_selection = self._load_saved_selection()

        if target_selection:
            item_type, item_id = target_selection
            t_pop0 = time.perf_counter()
            try:
                if hasattr(self.model, "populate_for_selection"):
                    self.model.populate_for_selection(item_type, int(item_id))
            except Exception:
                logger.debug(
                    "TreeManagement._after_snapshot_applied: failed to pre-populate target selection %s #%s",
                    item_type,
                    item_id,
                    exc_info=True,
                )
            t_pop1 = time.perf_counter()

            def _restore_selection() -> None:
                try:
                    self._state.restore_selection((item_type, item_id))
                except Exception:
                    logger.exception(
                        "TreeManagement._after_snapshot_applied: failed to restore selection %s #%s",
                        item_type,
                        item_id,
                    )

            try:
                delay_ms = get_selection_restore_delay_ms(0)
            except Exception:
                delay_ms = 0

            if delay_ms <= 0:
                _restore_selection()
            else:
                try:
                    schedule_selection_restore(
                        _restore_selection,
                        f"tree_restore_{item_type}_{item_id}",
                        delay=delay_ms,
                    )
                except Exception:
                    logger.exception(
                        "TreeManagement._after_snapshot_applied: failed to schedule selection restore"
                    )
        else:
            self._state.select_first_item()

        self._finalize_first_load()
        t2 = time.perf_counter()
        logger.info(
            "[Perf] TreeManagement.after_snapshot restore_expanded=%.2fms prepopulate_target=%.2fms selection_and_finalize=%.2fms total=%.2fms delay_ms=%s target=%s",
            (t1 - t0) * 1000.0,
            (t_pop1 - t1) * 1000.0 if 't_pop1' in locals() else 0.0,
            (t2 - (t_pop1 if 't_pop1' in locals() else t1)) * 1000.0,
            (t2 - t0) * 1000.0,
            delay_ms if 'delay_ms' in locals() else None,
            target_selection if 'target_selection' in locals() else None,
        )

    @pyqtSlot(str, int, dict)
    def _on_item_added(
        self, item_type: str, parent_id: int, data: dict[str, Any]
    ) -> None:
        # Incremental insert via model
        # Note: on insert error full structure reload required —
        # expected model errors (ValueError, RuntimeError) logged and re-raised,
        # unexpected exceptions also not suppressed.
        if item_type == "category" and not isinstance(parent_id, int):
            return
        self._updates.handle_item_added(item_type, parent_id, data)

    @pyqtSlot(str, int, dict)
    def _on_item_updated(
        self, item_type: str, item_id: int, data: dict[str, Any]
    ) -> None:
        self._updates.handle_item_updated(item_type, item_id, data)

    @pyqtSlot(str, int)
    def _on_item_deleted(self, item_type: str, item_id: int) -> None:
        self._updates.handle_item_deleted(item_type, item_id)

    @pyqtSlot(str, list)
    def _on_items_batch_deleted(self, item_type: str, item_ids: list) -> None:
        ids = [int(i) for i in (item_ids or []) if isinstance(i, int) and i > 0]
        if not ids:
            return
        current_selection = self._state.capture_current_selection()
        selection_handler = getattr(self.controller, "selection_handler", None)
        if selection_handler is not None:
            selection_handler.begin_suppress_selection()
        try:
            self._updates.handle_items_batch_deleted(item_type, ids)
        finally:
            if selection_handler is not None:
                selection_handler.end_suppress_selection()

        if current_selection:
            item_type, item_id = current_selection
            idx = self.model.index_for(item_type, int(item_id))
            if idx is not None and idx.isValid():
                self._state.restore_selection(current_selection)
                logger.info(
                    "TreeManagement._on_items_batch_deleted: restored selection %s #%s",
                    item_type,
                    item_id,
                )
                return
        self._state.select_first_item()
        logger.info(
            "TreeManagement._on_items_batch_deleted: selected first item after batch delete"
        )

    def clear_tiles(self) -> None:
        """Clear category tiles."""
        self._tiles.clear_tiles()

    def refresh_tiles_for_current_selection(self) -> None:
        """Update tiles according to current tree selection."""
        self._tiles.refresh_by_current_tree_selection()

    def refresh_section_tiles(self, section_id: int) -> None:
        """Update section tiles via passed CategoryTilesController."""
        self._tiles.refresh_section_tiles(section_id)

    def replace_section_categories(
        self, section_id: int, categories: list[dict[str, Any]]
    ) -> None:
        """Replace categories under a section in the tree model."""
        self._updates.replace_section_categories(section_id, categories)

    def get_current_category_id(self) -> Optional[int]:
        selection = self._state.capture_current_selection()
        if selection and selection[0] == "category" and isinstance(selection[1], int):
            return selection[1]
        return None

    def _find_item_by_id(self, item_type: str, item_id: int):
        """Return QModelIndex of item by type ('section'|'category') and id.

        Compatible helper for calls from `ItemOperations` and menu actions.
        """
        try:
            idx = self.model.index_for(item_type, int(item_id))
            if idx and hasattr(idx, "isValid") and idx.isValid():
                return idx
        except Exception:
            logger.exception(
                "TreeManagement._find_item_by_id: error finding item %s #%s",
                item_type,
                item_id,
            )
        return None

    def on_structure_item_changed(
        self, item_type: str, item_id: int, data: dict
    ) -> None:
        self._on_item_updated(item_type, item_id, data)

    # --- Helper methods ----------------------------------------

    def _after_structure_loaded_snapshot(
        self,
        expanded_state: dict,
        current_selection: Optional[tuple[str, int]],
        has_sections: bool,
    ) -> None:
        # If structure empty — clear tiles
        if not has_sections:
            try:
                self.clear_tiles()
            except Exception:
                logger.exception(
                    "TreeManagement._after_structure_loaded_snapshot: tiles clear error"
                )

        # Restore expansion
        self._state.restore_expanded_state(expanded_state)

        # Restore selection if it existed
        if current_selection:
            item_type, item_id = current_selection
            if item_type in ("section", "category") and isinstance(item_id, int):
                if item_type == "category":
                    sb = None
                    try:
                        sb = getattr(self.controller, "business", None) or getattr(
                            self.controller, "structure_business", None
                        )
                    except Exception:
                        sb = None
                    if sb and getattr(sb, "_suppress_category_restore_once", False):
                        try:
                            sb._suppress_category_restore_once = False
                        except Exception:
                            pass
                        self._state.select_first_item()
                        self._finalize_first_load()
                        return
                self._state.restore_selection(current_selection)
        else:
            self._state.select_first_item()

        self._finalize_first_load()

    def _load_saved_selection(self) -> Optional[tuple[str, int]]:
        """Return persisted tree selection if present and exists in the model."""
        try:
            settings = getattr(self.controller.main, "settings", None)
            if not (settings and hasattr(settings, "get_last_tree_selection")):
                return None
            saved = settings.get_last_tree_selection()
            if not saved:
                return None
            item_type, item_id = saved
            idx = self.model.index_for(item_type, int(item_id))
            if idx and idx.isValid():
                return item_type, int(item_id)
        except Exception:
            logger.debug("TreeManagement: failed to load saved selection", exc_info=True)
        return None

    def _finalize_first_load(self) -> None:
        # Guaranteed reset of one-time category restore suppression flag
        try:
            sb = getattr(self.controller, "business", None) or getattr(
                self.controller, "structure_business", None
            )
            if sb and getattr(sb, "_suppress_category_restore_once", False):
                sb._suppress_category_restore_once = False
        except Exception:
            pass

        # After first structure load update main window display
        main = getattr(self.controller, "main", None)
        if main is not None and getattr(main, "_first_structure_load", False):
            main._first_structure_load = False
            try:
                if getattr(self.tree, "viewport", None):
                    self.tree.viewport().update()
            except Exception:
                self.tree.update()

    def on_structure_item_added(
        self, item_type: str, parent_id: int, data: dict
    ) -> None:
        self._on_item_added(item_type, parent_id, data)

    def _update_category_display(self, category_id: int, new_data: dict) -> None:
        """Display will update after model reload; update tiles via business logic."""
        if hasattr(self.controller, "business"):
            try:
                hier = self.controller.business.get_category_hierarchy(category_id)
                if hier and "section_id" in hier:
                    self.refresh_section_tiles(int(hier["section_id"]))
            except Exception:
                logger.exception(
                    "TreeManagement._update_category_display: tiles update error by category #%s hierarchy",
                    category_id,
                )

    def _update_category_tiles_after_edit(
        self, _category_index: QModelIndex | None = None
    ) -> None:
        """Update category tiles after category edit."""
        # Determine current section by current index and update tiles
        self._tiles.refresh_after_category_edit()

    def _update_section_tiles_after_edit(
        self, _section_index: QModelIndex | None = None
    ) -> None:
        """Update category tiles after section edit."""
        self._tiles.refresh_after_section_edit()
