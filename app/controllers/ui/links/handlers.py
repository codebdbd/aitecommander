import logging
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt

from .base_component import BaseLinksUIComponent
from app.utils.common import safe_call

logger = logging.getLogger(__name__)


class SetupError(Exception):
    """Wiring error for critical LinksUIHandlers signals."""


class LinksUIHandlers(BaseLinksUIComponent):
    """Event handlers for LinksUIController."""

    def __init__(
        self,
        controller,
        *,
        link_operations,
        links_table_controller,
        ui_state=None,
        category_provider=None,
        structure_tree=None,
    ):
        # Explicit dependency requirements for better diagnostics
        if links_table_controller is None:
            raise ValueError(
                "LinksUIHandlers requires explicit 'links_table_controller' dependency"
            )
        provider = ui_state or category_provider
        if provider is None:
            raise ValueError(
                "LinksUIHandlers requires 'ui_state' or 'category_provider' dependency"
            )
        # Required contract: get_current_category_id() method needed
        if not hasattr(provider, "get_current_category_id") or not callable(
            provider.get_current_category_id
        ):
            raise TypeError(
                "'ui_state'/'category_provider' must provide callable get_current_category_id()"
            )
        self._category_provider = provider

        # Structure tree dependency for selection clearing (injected by window controller)
        # For unit tests, wiring may be absent, then behavior will only log error
        self._structure_tree = structure_tree

        super().__init__(
            controller, link_operations, links_table_controller=links_table_controller
        )

    def _connect_signals(self):
        """Connect signals from business logic."""
        if getattr(self, "_signals_connected", False):
            return
        # Moved to centralized LinksTableController to avoid direct populate and possible cycles
        # Strictly require presence of critical business signals and their compatibility
        try:
            biz = self.business
            # Required signals
            required = {
                "favorites_counted": self._complete_toggle_fav,
                "link_updated": self._on_link_updated,
                "error_occurred": self._handle_error,
            }
            for sig_name, slot in required.items():
                sig = getattr(biz, sig_name, None)
                if sig is None:
                    raise SetupError(f"Missing required business signal: {sig_name}")
                connect_fn = getattr(sig, "connect", None)
                if connect_fn is None or not callable(connect_fn):
                    raise SetupError(
                        f"Business signal '{sig_name}' must expose callable connect()"
                    )
                connect_fn(slot)

            # Optional global search signal (for backward test compatibility)
            try:
                search_sig = getattr(biz, "search_results_ready", None)
                if (
                    search_sig is not None
                    and hasattr(search_sig, "connect")
                    and callable(search_sig.connect)
                ):
                    search_sig.connect(self._update_search_results)
                else:
                    logger.debug(
                        "LinksUIHandlers: business signal 'search_results_ready' not present; global search UI updates disabled"
                    )
            except Exception:
                logger.debug(
                    "LinksUIHandlers: failed to wire optional 'search_results_ready'",
                    exc_info=True,
                )
        except SetupError:
            # Already informative message — re-raise as is, but log stack
            logger.exception(
                "Failed to wire LinksUIHandlers business signals (setup error)"
            )
            raise
        except Exception:
            # Any other errors considered setup error to not mask DI defects
            logger.exception("Unexpected error wiring LinksUIHandlers business signals")
            raise SetupError("Failed to connect LinksUIHandlers to business signals")
        self._signals_connected = True

    def _connect_table_signals(self):
        """Connect signals from table."""
        if getattr(self, "_table_signals_connected", False):
            return
        # Required table signals/methods for context menu — strict interface check
        if not hasattr(self.table, "setContextMenuPolicy") or not callable(
            self.table.setContextMenuPolicy
        ):
            raise SetupError("links table must provide callable setContextMenuPolicy()")
        if not hasattr(self.table, "customContextMenuRequested"):
            raise SetupError(
                "links table must expose signal customContextMenuRequested with connect()"
            )
        context_sig = self.table.customContextMenuRequested
        if not hasattr(context_sig, "connect") or not callable(context_sig.connect):
            raise SetupError(
                "links table must expose signal customContextMenuRequested with connect()"
            )
        connect_fn = context_sig.connect

        # Connect required context menu handlers
        try:
            self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        except (AttributeError, TypeError) as e:
            logger.error(
                "Failed to set context menu policy on links table: %s", e, exc_info=True
            )
            raise SetupError("Failed to set context menu policy on links table") from e
        except Exception:
            logger.exception(
                "Unexpected error while setting context menu policy on links table"
            )
            raise
        try:
            connect_fn(self._on_context_menu)
        except (AttributeError, TypeError) as e:
            logger.error(
                "Failed to connect customContextMenuRequested for links table: %s",
                e,
                exc_info=True,
            )
            raise SetupError(
                "Failed to connect customContextMenuRequested for links table"
            ) from e
        except Exception:
            logger.exception(
                "Unexpected error while connecting customContextMenuRequested for links table"
            )
            raise

        # QTableView: use index-based signals and adapt to existing handlers
        try:
            self.table.doubleClicked.connect(
                lambda idx: self._on_double_click(idx.row(), idx.column())
            )
        except (AttributeError, TypeError) as e:
            raise SetupError(f"Failed to connect doubleClicked: {e}") from e
        try:
            self.table.clicked.connect(
                lambda idx: self._on_cell_clicked(idx.row(), idx.column())
            )
        except (AttributeError, TypeError) as e:
            raise SetupError(f"Failed to connect clicked: {e}") from e
        # Reentrancy flag to protect from loops during reordering
        # (e.g. when order update in DB triggers UI reload)
        self._handling_reorder: bool = False
        try:
            if hasattr(self.table, "links_reordered"):
                self.table.links_reordered.connect(self._on_links_reordered)
            else:
                raise AttributeError("links_reordered signal is missing")
        except (AttributeError, TypeError) as e:
            raise SetupError(f"Failed to connect links_reordered: {e}") from e
        # Exclusive selection: any selection in table clears tree selection
        try:
            if hasattr(self.table, "selectionModel"):
                sel_model = self.table.selectionModel()
                if sel_model is None:
                    raise AttributeError("selectionModel() returned None")
                sel_model.selectionChanged.connect(self._on_table_selection_changed)
            else:
                raise AttributeError("selectionModel() is missing on table")
        except (AttributeError, TypeError) as e:
            raise SetupError(f"Failed to connect selectionChanged: {e}") from e
        self._table_signals_connected = True

        # Key handling now centralized in KeyboardManager

    def _update_table(self, links: List[Dict], category_id: int, task_id: int):
        """Update links table with new data."""
        # Desync protection: accept only links for current category
        current_category_id = self._category_provider.get_current_category_id()
        if category_id != current_category_id:
            # E.g. user switched category while links were loading
            logger.debug(
                "Ignoring task_id=%s results: result category = %s, "
                "but current category = %s",
                task_id,
                category_id,
                current_category_id,
            )
            return

        # Update table directly, not relying on async signal processing
        try:
            self.links_table_controller.on_links_loaded(links, category_id, task_id)
        except (ValueError, RuntimeError):
            # Expected table controller contract errors - log and re-raise
            logger.exception(
                "LinksUIHandlers._update_table: links_table_controller.on_links_loaded contract error"
            )
            raise
        except Exception:
            # Unexpected errors log with full stacktrace, but don't hide
            logger.exception(
                "LinksUIHandlers._update_table: unexpected error in links_table_controller.on_links_loaded"
            )
            raise

        # Don't emit links_changed here to avoid triggering repeated reloads
        # Load notifications handled in LinksTableController.on_links_loaded

    def _update_search_results(self, search_results: List[Dict]):
        """Update search results."""
        try:
            self.links_table_controller.on_search_results(search_results)
        except (TypeError, ValueError):
            # Don't hide table controller contract errors
            logger.exception(
                "LinksUIHandlers._update_search_results: on_search_results contract error"
            )
            raise

    def _complete_toggle_fav(
        self, fav_count: int, links: List[Dict], link: Optional[Dict]
    ):
        """Complete favorite toggle."""
        # Centralize signal emission in LinkOperationsController
        try:
            cat_id = None
            if link is not None:
                cat_id = link.get("category_id")
            if not isinstance(cat_id, int) or cat_id <= 0:
                # Use explicit provider instead of getattr(self.main, ...)
                cat_id = self._category_provider.get_current_category_id()
            self.link_operations.on_favorite_toggled(cat_id)
        except Exception as e:
            logger.warning(
                "Failed to emit signals after toggle favorite: %s", e, exc_info=True
            )

    def _handle_error(self, error_msg: str):
        """Handle error."""
        logger.error("LinksUIController error: %s", error_msg)
        self._show_error(f"An error occurred: {error_msg}")

    def _on_link_updated(self, updated_link: Dict):
        """Handle link update."""
        # Diagnostic logging instead of unused local variables
        try:
            logger.debug(
                "Link updated: id=%s, name=%s, favorite=%s",
                updated_link.get("id"),
                updated_link.get("name", "Untitled"),
                updated_link.get("is_favorite", False),
            )
        except Exception:
            logger.debug(
                "LinksUIHandlers._on_link_updated: failed to log diagnostics for updated link",
                exc_info=True,
            )

        # Centralize signal emission in LinkOperationsController
        try:
            self.link_operations.on_link_updated(updated_link)
        except Exception as e:
            logger.warning(
                "Failed to emit signals after link update: %s", e, exc_info=True
            )

    def _on_double_click(self, row: int, column: int):
        """Handle double-click on row."""
        link = self.controller.get_link_at(row)
        if not link:
            logger.warning("No link found at row %s", row)
            return

        # Don't open link on double-click on favorite column (star)
        if column == self.COLUMNS["favorite"]:
            return

        if column == self.COLUMNS["notes"]:
            self.controller.show_note_dialog(link)
        else:
            self.controller.open_link(link)

    def _on_cell_clicked(self, row: int, column: int):
        """Handle cell click."""
        link = self.controller.get_link_at(row)
        if not link:
            logger.warning("No link found at row %s", row)
            return

        if column == self.COLUMNS["favorite"]:
            link_name = link.get("name", "Untitled")

            # Get visible name through model (DisplayRole)
            model = safe_call(self.table, "model", default=None)
            idx = (
                safe_call(model, "index", row, self.COLUMNS["name"], default=None)
                if model is not None
                else None
            )
            if idx and safe_call(idx, "isValid", default=False):
                val = safe_call(model, "data", idx, Qt.ItemDataRole.DisplayRole, default=None)
                visible_name = str(val) if val is not None else "Unknown"
            else:
                visible_name = "Unknown"

            if link_name != visible_name:
                logger.warning(
                    "MISMATCH! Link data does not match visible content! Expected: '%s', Received: '%s'",
                    visible_name,
                    link_name,
                )

            # Log favorite toggle with brief context
            logger.debug(
                "Toggling favorite: id=%s, name=%s, current=%s",
                link.get("id"),
                link_name,
                link.get("is_favorite", False),
            )

            self.controller.toggle_favorite(link)

    def _on_context_menu(self, pos):
        """Handle context menu."""
        idx = self.table.indexAt(pos)
        try:
            if idx and idx.isValid():
                logger.debug(
                    "Context menu requested at row=%s, col=%s", idx.row(), idx.column()
                )
            else:
                logger.debug("Context menu requested at invalid index")
        except Exception:
            logger.debug("Context menu diagnostics failed", exc_info=True)

        menu = self.main.menu_controller.create_links_context_menu(
            self.table, idx, self.controller.clipboard.paste_link
        )
        if menu:
            menu.exec(self.table.mapToGlobal(pos))

    # Method _handle_key_press removed - key handling centralized in KeyboardManager

    def _on_links_reordered(self, link_ids: list):
        """Handle link reordering with reentrancy protection."""
        try:
            # Prevent reentrant calls if handler already executing
            if getattr(self, "_handling_reorder", False):
                logger.debug("[Reorder] Suppressed recursive _on_links_reordered call")
                return

            self._handling_reorder = True

            # Ignore empty or trivial input data
            if not link_ids or not isinstance(link_ids, list):
                return

            # Execute order update through business logic
            self.business.update_link_order(link_ids)

        except Exception as e:
            logger.error(
                "[Reorder] Error while handling links_reordered: %s", e, exc_info=True
            )
        finally:
            self._handling_reorder = False

    def _on_table_selection_changed(self, _selected, _deselected):
        """Exclusivity: when selecting in table, clear tree selection."""
        try:
            # Early exit: if selection actually empty, don't touch tree
            if _selected is not None and bool(safe_call(_selected, "isEmpty", default=False)):
                logger.debug("Table selection change: selected is empty; skip clearing tree")
                return

            tree = self._structure_tree
            if not tree:
                logger.debug("structure_tree not injected; skipping selection clear")
                return
            if hasattr(tree, "clearSelection") and callable(tree.clearSelection):
                safe_call(tree, "clearSelection")
                logger.debug("Cleared selection in structure_tree due to table selection change")
            else:
                logger.warning("structure_tree lacks clearSelection(); skipping")
        except Exception:
            logger.exception(
                "Failed to clear selection on structure_tree from table selection change"
            )
