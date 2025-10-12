import logging
from typing import Optional

from PyQt6.QtCore import QObject

from app.controllers.business.links_business import LinksBusinessLogic
from app.utils.common import safe_call
from app.utils.ui.qt.roles import get_selected_rows as get_selected_rows_util
from app.views.widgets.link import LinksTableView

from .clipboard import LinksUIClipboard
from .handlers import LinksUIHandlers
from .link_operations import LinksUILinkOperations

logger = logging.getLogger(__name__)


class LinksUIController(QObject):
    """UI controller for managing links table."""

    def __init__(
        self,
        table_widget: LinksTableView,
        business_logic: LinksBusinessLogic,
        main_window,
        *,
        link_operations=None,
        links_table_controller=None,
    ):
        super().__init__()
        if table_widget is None:
            logger.error("LinksUIController: table_widget is required")
            raise ValueError("LinksUIController: table_widget is required")
        if business_logic is None:
            logger.error("LinksUIController: business_logic is required")
            raise ValueError("LinksUIController: business_logic is required")
        if links_table_controller is None:
            logger.error("LinksUIController: links_table_controller is required")
            raise ValueError("LinksUIController: links_table_controller is required")
        if link_operations is None:
            logger.error("LinksUIController: link_operations is required")
            raise ValueError("LinksUIController: link_operations is required")
        self.table = table_widget
        self.business = business_logic
        self.main = main_window
        self._row_by_link_id: dict[int, int] = {}
        self.table_controller = links_table_controller

        # Initialize submodules with explicit dependencies
        # Pass category provider: first ui_state, otherwise main_window itself,
        # if it provides get_current_category_id (important for tests/stubs)
        _ui_state = getattr(main_window, "ui_state", None)
        _kwargs = {}
        if _ui_state is not None:
            _kwargs["ui_state"] = _ui_state
        elif hasattr(main_window, "get_current_category_id"):
            _kwargs["category_provider"] = main_window

        # Explicit structure_tree dependency wiring for LinksUIHandlers (if available)
        structure = getattr(main_window, "structure", None)
        tree = getattr(structure, "tree", None) if structure is not None else None
        if tree is not None:
            _kwargs["structure_tree"] = tree

        self.handlers = LinksUIHandlers(
            self,
            link_operations=link_operations,
            links_table_controller=self.table_controller,
            **_kwargs,
        )
        self.clipboard = LinksUIClipboard(self, link_operations=link_operations)
        self.link_ops = LinksUILinkOperations(self, link_operations=link_operations)

        # Connect signals
        self.handlers.initialize()
        # Row indexing after any bulk table update
        try:
            if hasattr(self.table, "table_populated"):
                self.table.table_populated.connect(self.rebuild_row_index)
        except Exception as e:
            logger.debug("Failed to connect table_populated: %s", e)

        # CENTRALIZED: initial category load
        self._reload_current_category()

    def shutdown(self, timeout: int = 2000):
        """Graceful shutdown."""
        self.business.shutdown(timeout)

    def load_category(self, category_id: int):
        """Load links for category - business logic ONLY.

        CENTRALIZED: UI coordination moved to UIStateManager.load_category().
        This method now contains only business logic for data loading.
        """
        self.business.load_links(category_id)

    def on_search(self, text: str):
        """Handle search query."""
        if not text.strip():
            # If search empty, load current category
            self._reload_current_category()
        else:
            self.business.search_links(text)

    def get_link_at(self, row: int) -> Optional[dict]:
        """Get link by row number, delegating call to table.

        Bounds checks and error handling encapsulated in view method.
        """
        return safe_call(self.table, "get_link_at", row, default=None)

    def get_row_count(self) -> int:
        """Get table row count."""
        try:
            model = self.table.model()
            return model.rowCount() if model is not None else 0
        except (AttributeError, RuntimeError) as e:
            logger.error("Error getting row count: %s", e)
            return 0

    def has_selection(self) -> bool:
        """Check if table has selection."""
        try:
            sel = self.table.selectionModel()
            return bool(sel and sel.hasSelection())
        except (AttributeError, RuntimeError) as e:
            logger.error("Error checking selection: %s", e)
            return False

    def current_row(self) -> int:
        """Get current row number."""
        try:
            idx = self.table.currentIndex()
            return idx.row() if idx and idx.isValid() else -1
        except (AttributeError, RuntimeError) as e:
            logger.error("Error getting current row: %s", e)
            return -1

    def select_row(self, row: int) -> None:
        """Select row by number."""
        self.table.selectRow(row)

    def set_current_cell(self, row: int, column: int) -> None:
        """Set current cell."""
        try:
            model = self.table.model()
            if model is None:
                return
            index = model.index(row, column)
            if index and index.isValid():
                self.table.setCurrentIndex(index)
        except (AttributeError, RuntimeError) as e:
            logger.error("Error setting current cell: %s", e)

    def scroll_to_row(self, row: int) -> None:
        """Scroll table to row."""
        try:
            model = self.table.model()
            if model is None:
                return
            index = model.index(row, 0)
            if index and index.isValid():
                self.table.scrollTo(index)
        except (AttributeError, RuntimeError) as e:
            logger.error("Error scrolling to row: %s", e)

    def get_selected_rows(self) -> list[int]:
        """Get selected row numbers via common utility."""
        return get_selected_rows_util(self.table)

    def quick_add_link(self, link_type: str, category_id: int = None):
        """Quick add link."""
        self.link_ops.quick_add_link(link_type, category_id)

    def show_note_dialog(self, link: dict) -> None:
        """Show note dialog for link."""
        self.link_ops.show_note_dialog(link)

    def get_selected_links(self) -> list[dict]:
        """Get selected links (single source of truth).

        Collects selected rows via get_selected_rows() and extracts
        link objects via get_link_at(). Filters empty values.
        """
        rows = self.get_selected_rows()
        if not rows:
            return []
        links = [self.get_link_at(r) for r in rows]
        return [ln for ln in links if ln]

    def open_link(self, link: dict) -> None:
        """Open link."""
        logger.info("open_link called with link: %s", link)
        self.link_ops._open_link(link)

    def toggle_favorite(self, link: dict = None) -> None:
        """Toggle favorite status."""
        self.link_ops._toggle_fav(link)

    def cut_selected_links(self) -> None:
        """Cut selected links."""
        self.clipboard.cut_link()

    def copy_selected_links(self) -> None:
        """Copy selected links."""
        self.clipboard.copy_link()

    def paste_links(self) -> None:
        """Paste links from clipboard."""
        self.clipboard.paste_link()

    def delete_selected_links(self) -> None:
        """Delete selected links."""
        links = self.clipboard.get_selected_links()
        self.clipboard.delete_links(links)

    def focus_on_link(self, link_id: int) -> None:
        """Focus on link with specified ID.

        Logic moved from MainWindow._restore_table_selection to eliminate duplication
        and so external calls (see link_operations_controller) work through UI controller.
        """
        try:
            # Fast path: use index if available
            row = self._row_by_link_id.get(link_id)
            if row is None:
                # Lazy index rebuild
                self.rebuild_row_index()
                row = self._row_by_link_id.get(link_id)
            if row is not None:
                self.select_row(row)
                self.set_current_cell(row, 0)
                self.scroll_to_row(row)
                try:
                    if hasattr(self.table, "setFocus"):
                        self.table.setFocus()
                except Exception:
                    pass
            else:
                logger.debug(
                    "focus_on_link: link_id %s not found in current table", link_id
                )
        except Exception as e:
            logger.error("Failed to focus on link %s: %s", link_id, e)

    def rebuild_row_index(self) -> None:
        """Rebuild link_id -> row index from current table contents."""
        try:
            self._row_by_link_id.clear()
            rows = self.get_row_count()
            for row in range(rows):
                link = self.get_link_at(row)
                if link and "id" in link:
                    self._row_by_link_id[link["id"]] = row
        except Exception as e:
            logger.debug("rebuild_row_index failed: %s", e)

    def _reload_current_category(self) -> None:
        """Centralized current category reload via LinksTableController."""
        category_id = self.main.get_current_category_id()
        if not category_id:
            return
        try:
            self.table_controller.reload(category_id)
        except Exception as e:
            logger.error("Failed to reload category (id=%s): %s", category_id, e)
