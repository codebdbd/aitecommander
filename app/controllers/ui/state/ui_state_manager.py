# app/controllers/ui/state/ui_state_manager.py

"""Centralized UI state manager to eliminate logic duplication."""

import logging
from typing import Optional

from app.config_data import app_config

logger = logging.getLogger(__name__)


class UIStateManager:
    """Centralized manager for UI component state management.

    SINGLE RESPONSIBILITY POINT for category loading in the application.
    Eliminates load_category logic duplication in 15+ places.
    """

    def __init__(self, main_window):
        self.main = main_window
        # Simple flag to prevent parallel loading of same category
        self._loading: bool = False

    def load_category(self, category_id: int, source: str = "unknown") -> bool:
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
                table_idx = app_config.ui.get_stack_index_table()
            except Exception:
                current_idx = None
                table_idx = None
            already_loaded = (
                getattr(self.main, "current_category_id", None) == category_id
            )
            if already_loaded and current_idx == table_idx:
                logger.debug(
                    "load_category skipped: category %s already active and TABLE view set (source=%s)",
                    category_id,
                    source,
                )
                return True

            # 3. Update application state
            self.main.current_category_id = category_id

            # 4. Load data through business logic
            if hasattr(self.main, "links_business") and self.main.links_business:
                self.main.links_business.load_links(category_id)
            elif hasattr(self.main, "links") and self.main.links:
                # Fallback to UI controller (business logic only)
                self.main.links.business.load_links(category_id)
            else:
                logger.error(
                    "No links business logic available for category %s",
                    category_id,
                )
                return False

            # 5. Update UI state
            self._switch_to_table_view()
            self._clear_tiles_selection()

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
            table_index = app_config.ui.get_stack_index_table()
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

    def switch_to_category_tiles(self, categories_data: list):
        """Switch to category tiles for specified section."""
        try:
            # 1. Set category data in tiles
            if hasattr(self.main, "tiles") and self.main.tiles:
                self.main.tiles.set_categories(categories_data)

            # 2. Switch stack to category tiles ONLY when there's something to show
            #    This prevents "empty screen" when temporarily no selection during tree reload
            if hasattr(self.main, "stack") and categories_data:
                # Use consistent configuration getter
                tiles_index = app_config.ui.get_stack_index_tiles()
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

                # 3. After switching to tiles update status bar,
                #    to reflect category count instead of link count
                try:
                    if hasattr(self.main, "update_statusbar"):
                        self.main.update_statusbar()
                except Exception:
                    logger.debug(
                        "Failed to update status bar after switching to tiles",
                        exc_info=True,
                    )

        except Exception as e:
            logger.exception("Error switching to category tiles: %s", e)

    def _clear_tiles_selection(self):
        """Reset category tiles selection."""
        if hasattr(self.main, "tiles") and self.main.tiles:
            self.main.tiles._current_item_id = None

    def clear_tiles_selection(self):
        """Public method to reset category tiles selection."""
        self._clear_tiles_selection()

    def get_stack_index_table(self):
        """Get stack index for links table."""
        return app_config.ui.get_stack_index_table()

    def get_stack_index_tiles(self):
        """Get stack index for category tiles."""
        return app_config.ui.get_stack_index_tiles()

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
