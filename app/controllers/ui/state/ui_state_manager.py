# app/controllers/ui/state/ui_state_manager.py

"""Centralized UI state manager to eliminate logic duplication."""

import logging
import os
import time

from app.config_data.runtime_config import get_table_stack_index, get_tiles_stack_index

logger = logging.getLogger(__name__)
_DIAG_SPHERE_SWITCH = str(os.getenv("APP_SPHERE_SWITCH_DIAG", "")).lower() in {
    "1",
    "true",
    "yes",
    "on",
}


class UIStateManager:
    """Centralized manager for UI component state management.

    SINGLE RESPONSIBILITY POINT for category loading in the application.
    Eliminates load_category logic duplication in 15+ places.
    """

    def __init__(self, main_window):
        self.main = main_window
        # Simple flag to prevent parallel loading of same category
        self._loading: bool = False
        # Navigation history stack for categories
        self._history: list[int] = []
        self._history_index: int = -1
        self._navigating_history: bool = False

    def load_category(
        self,
        category_id: int,
        source: str = "unknown",
        *,
        force_reload: bool = False,
    ) -> bool:
        """SINGLE method for category loading in the application.

        Replaces all duplicated implementations:
        - MainWindow.load_category()
        - LinksUIController.load_category() (UI coordination only)
        - BaseCommand.update_links_table()
        - SelectionHandling calls
        - Dialog controller calls

        Args:
            category_id: Category ID to load
            source: Call source for logging and debugging

        Returns:
            bool: True if load successful, False on error
        """
        # Simple protection from parallel calls without complex magic
        if self._loading:
            logger.info("load_category skipped: already loading (source=%s)", source)
            return True

        try:
            self._loading = True
            logger.debug("Loading category %s from %s", category_id, source)

            if _DIAG_SPHERE_SWITCH:
                try:
                    started = getattr(self.main, "_sphere_switch_started_ms", None)
                    if isinstance(started, (int, float)) and started > 0:
                        elapsed_ms = int((time.monotonic() - float(started)) * 1000)
                        logger.info(
                            "[Perf] Sphere switch -> load_category start: %d ms (source=%s)",
                            elapsed_ms,
                            source,
                        )
                        self.main._sphere_switch_started_ms = None
                except Exception:
                    pass

            # 1. Валидация входных данных
            if not isinstance(category_id, int) or category_id <= 0:
                logger.warning("Invalid category_id: %s from %s", category_id, source)
                return False

            # 2. If this category is already loaded and we're already in TABLE, can safely skip
            try:
                current_idx = (
                    self.main.stack.currentIndex()
                    if hasattr(self.main, "stack")
                    else None
                )
                table_idx = get_table_stack_index()
            except Exception:
                current_idx = None
                table_idx = None
            already_loaded = (
                getattr(self.main, "current_category_id", None) == category_id
            )
            if not force_reload and already_loaded and current_idx == table_idx:
                logger.debug(
                    "load_category skipped: category %s already active and TABLE view set (source=%s)",
                    category_id,
                    source,
                )
                return True

            # 3. Update application state
            self.main.current_category_id = category_id
            settings = getattr(self.main, "settings", None)
            if settings and hasattr(settings, "set_last_tree_selection"):
                settings.set_last_tree_selection("category", int(category_id))
            if settings and hasattr(settings, "set_last_sphere_id"):
                sb = getattr(self.main, "structure_business", None)
                curr_sp = getattr(sb, "current_sphere_id", None) if sb else None
                if isinstance(curr_sp, int) and curr_sp > 0:
                    settings.set_last_sphere_id(curr_sp)

            # 4. Load data through centralized links table controller
            links_ctrl = getattr(self.main, "links_table_controller", None)
            if links_ctrl and hasattr(links_ctrl, "reload"):
                links_ctrl.reload(category_id)
            else:
                logger.error(
                    "No links_table_controller available for category %s",
                    category_id,
                )
                return False

            # 5. Update UI state
            self._switch_to_table_view()
            self._clear_tiles_selection()

            if not self._navigating_history:
                self._record_history(category_id)

            logger.debug("Successfully loaded category %s from %s", category_id, source)
            return True

        except Exception as e:
            logger.exception(
                "Error loading category %s from %s: %s", category_id, source, e
            )
            self._handle_load_error()
            return False
        finally:
            self._loading = False

    def _switch_to_table_view(self):
        """Switch UI to links table view."""
        if hasattr(self.main, "stack"):
            # Use consistent configuration getter
            table_index = get_table_stack_index()
            count = (
                self.main.stack.count() if hasattr(self.main.stack, "count") else None
            )
            if count is not None and (table_index < 0 or table_index >= count):
                logger.warning(
                    "Table index %s out of range (count=%s). Forcing index=0.",
                    table_index,
                    count,
                )
                table_index = 0
            try:
                current = self.main.stack.currentIndex()
            except Exception:
                current = None
            if current != table_index:
                logger.info(
                    "[UI] Switch to TABLE view: index=%s, stack_count=%s",
                    table_index,
                    count,
                )
                self.main.stack.setCurrentIndex(table_index)
            else:
                logger.debug(
                    "[UI] Already in TABLE view (index=%s) - skip switch",
                    table_index,
                )
            try:
                cur = self.main.stack.currentIndex()
                # Inform only on real switch, otherwise DEBUG
                if current != table_index:
                    logger.info(
                        "[UI] Stack currentIndex after switch_to_table_view: %s",
                        cur,
                    )
                else:
                    logger.debug(
                        "[UI] Stack currentIndex after switch_to_table_view (unchanged): %s",
                        cur,
                    )
            except Exception:
                pass

    def _handle_load_error(self):
        """Handle category loading errors."""
        self._clear_tiles_selection()
        # Can add user notification in future

    # --- Navigation history methods ---
    def _record_history(self, category_id: int) -> None:
        """Record category visit in navigation history."""
        if 0 <= self._history_index < len(self._history):
            if self._history[self._history_index] == category_id:
                return
        self._history = self._history[: self._history_index + 1]
        self._history.append(category_id)
        if len(self._history) > 50:
            self._history.pop(0)
        self._history_index = len(self._history) - 1
        self.sync_navigation_state()

    def sync_navigation_state(self) -> None:
        updater = getattr(self.main, "update_navigation_history_state", None)
        if callable(updater):
            updater(self.can_navigate_back(), self.can_navigate_forward())

    def can_navigate_back(self) -> bool:
        return self._history_index > 0

    def can_navigate_forward(self) -> bool:
        return 0 <= self._history_index < len(self._history) - 1

    def navigate_back(self) -> bool:
        if not self.can_navigate_back():
            return False
        self._history_index -= 1
        self.sync_navigation_state()
        target_id = self._history[self._history_index]
        return self._navigate_to_history_category(target_id)

    def navigate_forward(self) -> bool:
        if not self.can_navigate_forward():
            return False
        self._history_index += 1
        self.sync_navigation_state()
        target_id = self._history[self._history_index]
        return self._navigate_to_history_category(target_id)

    def _navigate_to_history_category(self, category_id: int) -> bool:
        self._navigating_history = True
        try:
            sb = getattr(self.main, "structure_business", None)
            if sb and hasattr(sb, "get_category_hierarchy"):
                hierarchy = sb.get_category_hierarchy(category_id)
                if hierarchy and isinstance(hierarchy, dict):
                    target_sphere = hierarchy.get("sphere_id")
                    current_sphere = getattr(sb, "current_sphere_id", None)
                    if (
                        isinstance(target_sphere, int)
                        and target_sphere > 0
                        and target_sphere != current_sphere
                    ):
                        struct_ctrl = getattr(self.main, "structure_controller", None) or getattr(
                            self.main, "structure", None
                        )
                        if struct_ctrl and hasattr(struct_ctrl, "switch_sphere"):
                            struct_ctrl.switch_sphere(target_sphere, item_to_select=("category", category_id))
                            return True
                        if hasattr(sb, "set_current_sphere"):
                            sb.set_current_sphere(target_sphere)
            struct_ctrl = getattr(self.main, "structure_controller", None) or getattr(
                self.main, "structure", None
            )
            handler = getattr(struct_ctrl, "selection_handler", None) if struct_ctrl else None
            if handler and hasattr(handler, "_restore_category_selection"):
                handler._restore_category_selection(category_id)
            else:
                self.load_category(category_id, source="NavigationHistory")
            return True
        except Exception:
            logger.exception("Failed navigating to category #%s", category_id)
            return False
        finally:
            self._navigating_history = False

    def switch_to_category_tiles(
        self, categories_data: list, *, force_show_when_empty: bool = False
    ) -> bool:
        """Switch to category tiles for specified section and apply tile data.
        
        Returns:
            True if tiles data was applied via UIStateManager path.
        """
        applied_tiles = False
        perf_t0 = None
        try:
            import time as _time
            perf_t0 = _time.perf_counter()
            t_switch_done = perf_t0
            t_status_done = perf_t0
        except Exception:
            _time = None
            t_switch_done = None
            t_status_done = None
        try:
            # 1. Switch stack to category tiles when explicitly requested for a section,
            #    even if it has zero categories. Keep old behavior for transient empty states.
            should_show_tiles = bool(categories_data) or bool(force_show_when_empty)
            if hasattr(self.main, "stack") and should_show_tiles:
                # Use consistent configuration getter
                tiles_index = get_tiles_stack_index()
                count = (
                    self.main.stack.count()
                    if hasattr(self.main.stack, "count")
                    else None
                )
                if count is not None and (tiles_index < 0 or tiles_index >= count):
                    logger.warning(
                        "Tiles index %s out of range (count=%s). Forcing index=0.",
                        tiles_index,
                        count,
                    )
                    tiles_index = 0
                try:
                    current = self.main.stack.currentIndex()
                except Exception:
                    current = None
                if current != tiles_index:
                    logger.info(
                        "[UI] Switch to TILES view: index=%s, stack_count=%s, categories=%s",
                        tiles_index,
                        count,
                        len(categories_data),
                    )
                    self.main.stack.setCurrentIndex(tiles_index)
                else:
                    logger.debug(
                        "[UI] Already in TILES view (index=%s) - skip switch",
                        tiles_index,
                    )
                try:
                    cur = self.main.stack.currentIndex()
                    if current != tiles_index:
                        logger.info(
                            "[UI] Stack currentIndex after switch_to_category_tiles: %s",
                            cur,
                        )
                    else:
                        logger.debug(
                            "[UI] Stack currentIndex after switch_to_category_tiles (unchanged): %s",
                            cur,
                        )
                except Exception:
                    pass
                if _time is not None and perf_t0 is not None:
                    t_switch_done = _time.perf_counter()

                # 2. After switching to tiles update status bar,
                #    to reflect category count instead of link count
                try:
                    if hasattr(self.main, "update_statusbar"):
                        self.main.update_statusbar()
                except Exception:
                    logger.debug(
                        "Failed to update status bar after switching to tiles",
                        exc_info=True,
                    )
                if _time is not None and perf_t0 is not None:
                    t_status_done = _time.perf_counter()
            # 3. Apply tile data through the central UI state path.
            applied_tiles = self.set_tiles_data(categories_data)
            if _time is not None and perf_t0 is not None:
                t_end = _time.perf_counter()
                logger.debug(
                    "[Perf] UIState.switch_to_category_tiles categories=%s switch_stack=%.2fms statusbar=%.2fms set_tiles_data=%.2fms total=%.2fms",
                    len(categories_data) if isinstance(categories_data, list) else -1,
                    ((t_switch_done or perf_t0) - perf_t0) * 1000.0,
                    ((t_status_done or t_switch_done or perf_t0) - (t_switch_done or perf_t0)) * 1000.0,
                    (t_end - (t_status_done or t_switch_done or perf_t0)) * 1000.0,
                    (t_end - perf_t0) * 1000.0,
                )

        except Exception as e:
            logger.exception("Error switching to category tiles: %s", e)
        return applied_tiles

    def set_tiles_data(self, categories_data: list) -> bool:
        """Update tiles data without switching the current view.
        
        Returns:
            True when tiles widget was updated.
        """
        try:
            tiles_widget = getattr(self.main, "tiles", None)
            if tiles_widget is None:
                widgets = getattr(self.main, "widgets", None)
                tiles_widget = getattr(widgets, "tiles", None) if widgets else None
            if tiles_widget is None or not hasattr(tiles_widget, "set_categories"):
                return False
            tiles_widget.set_categories(categories_data or [])
            return True
        except Exception as e:
            logger.exception("Error setting tiles data: %s", e)
            return False

    def _clear_tiles_selection(self):
        """Reset category tiles selection."""
        if hasattr(self.main, "tiles") and self.main.tiles:
            self.main.tiles._current_item_id = None

    def clear_tiles_selection(self):
        """Public method to reset category tiles selection."""
        self._clear_tiles_selection()

    def get_stack_index_table(self):
        """Get stack index for links table."""
        return get_table_stack_index()

    def get_stack_index_tiles(self):
        """Get stack index for category tiles."""
        return get_tiles_stack_index()

    # ========== DEBUG AND MONITORING METHODS ==========

    def get_current_category_id(self):
        """Get current category ID."""
        return getattr(self.main, "current_category_id", None)

    def is_category_loaded(self, category_id: int) -> bool:
        """Check if specified category is loaded."""
        current_id = self.get_current_category_id()
        return current_id == category_id

    def get_load_category_stats(self):
        """Get load_category usage statistics for debugging."""
        # In future can add call counters by sources
        return {
            "current_category_id": self.get_current_category_id(),
            "ui_state_manager_available": True,
            "links_business_available": hasattr(self.main, "links_business")
            and bool(self.main.links_business),
            "links_ui_available": hasattr(self.main, "links") and bool(self.main.links),
        }
