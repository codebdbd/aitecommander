# Module for populating and updating the links table
# Provides bulk-update helpers

import logging
from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtCore import Qt

from app.utils.ui.updates import suspend_updates
from app.views.widgets.protocols import LinkTableWidgetProtocol


class PopulationManagerMixin:
    """Mixin that populates and refreshes the links table.

    This mixin expects to be used with a class that implements LinkTableProtocol.
    Typically used with QTableView-based classes for link management.
    """

    # Module-level logger
    logger = logging.getLogger(__name__)

    if TYPE_CHECKING:
        _current_mode: Any

    def _link_table(self) -> LinkTableWidgetProtocol:
        """Return ``self`` typed as ``LinkTableWidgetProtocol`` for mypy."""

        return cast(LinkTableWidgetProtocol, self)

    def _capture_ui_state(self):
        """Capture current UI state (selection, scroll, sorting)."""
        table = self._link_table()
        try:
            sel = table.selectionModel()
            current_selection = [i.row() for i in sel.selectedRows()] if sel else []
        except Exception:
            self.logger.debug("populate: failed to capture selection", exc_info=True)
            current_selection = []
        current_scroll_bar = table.verticalScrollBar()
        current_scroll_pos = current_scroll_bar.value() if current_scroll_bar else 0

        try:
            header = table.horizontalHeader()
            sort_col, sort_order = (
                header.sortIndicatorSection(),
                header.sortIndicatorOrder(),
            )
        except Exception:
            self.logger.debug(
                "populate: failed to read sort state; using defaults", exc_info=True
            )
            sort_col, sort_order = -1, Qt.SortOrder.AscendingOrder
        return current_selection, current_scroll_pos, sort_col, sort_order

    def _block_signals(self) -> None:
        """Block table and header signals."""
        table = self._link_table()
        try:
            table.blockSignals(True)
        except Exception:
            self.logger.debug("populate: failed to block table signals", exc_info=True)

        header = table.horizontalHeader()
        if header is None:
            return

        try:
            header.blockSignals(True)
        except Exception:
            self.logger.debug("populate: failed to block header signals", exc_info=True)

    def _unblock_signals(self) -> None:
        """Unblock table and header signals."""
        table = self._link_table()

        header = table.horizontalHeader()
        if header is not None:
            try:
                header.blockSignals(False)
            except Exception:
                self.logger.debug(
                    "populate: failed to unblock header signals", exc_info=True
                )

        try:
            table.blockSignals(False)
        except Exception:
            self.logger.debug(
                "populate: failed to unblock table signals", exc_info=True
            )

    def _should_full_refresh(self, links, sort_col):
        """Check if full refresh is needed."""
        current_order = self._get_current_order()
        new_order = [link.get("id") for link in links if link and "id" in link]
        if (sort_col == -1) and current_order and (current_order != new_order):
            self.logger.info(
                "[LinksTableView] Detected ID order change without active sorting — performing full refresh"
            )
            return True

        current_ids = self._get_current_link_ids()
        new_ids = self._get_new_link_ids(links)
        bulk_changes = len(new_ids - current_ids) + len(current_ids - new_ids)
        if bulk_changes >= 30 or len(links) >= 200:
            self.logger.info(
                "[LinksTableView] Large number of changes (%s) — performing full refresh",
                bulk_changes,
            )
            return True
        return False

    def _get_current_order(self):
        """Get current order of link IDs in table."""
        ids = []
        model = self._link_table().model()
        total = model.rowCount() if model is not None else 0
        for row in range(total):
            data = self.get_link_at(row)
            if data and "id" in data:
                ids.append(data["id"])
        return ids

    def _perform_incremental_update(self, links, mode, sort_col):
        """Perform incremental update of table."""
        current_ids = self._get_current_link_ids()
        new_ids = self._get_new_link_ids(links)
        new_link_map = self._create_link_id_to_data_map(links)
        ids_to_remove = current_ids - new_ids
        ids_to_add = new_ids - current_ids
        ids_to_check = current_ids & new_ids

        remove_op = getattr(self, "_remove_links", None)
        update_op = getattr(self, "_update_links", None)
        add_op = getattr(self, "_add_links", None)

        missing_helpers = [
            name
            for name, op in (
                ("_remove_links", remove_op),
                ("_update_links", update_op),
                ("_add_links", add_op),
            )
            if op is None
        ]

        if missing_helpers:
            self.logger.warning(
                "[LinksTableView] Missing row operation helpers %s — switching to full refresh",
                ", ".join(missing_helpers),
            )
            raise AttributeError("row operation helpers unavailable")

        remove_op(ids_to_remove)
        update_op(ids_to_check, new_link_map, mode)

        table = self._link_table()
        try:
            add_op(links, ids_to_add, sort_col)
        finally:
            try:
                table.rebuild_cache_from_items()
            except Exception:
                self.logger.debug(
                    "populate: rebuild_cache_from_items failed after incremental ops",
                    exc_info=True,
                )

    def populate(self, links: list[dict], mode: str = "normal"):
        """Populate the table with link data using incremental updates."""
        if not isinstance(links, list):
            self.logger.warning(
                "[LinksTableView] Expected a list of links, got %s",
                type(links),
            )
            return

        table = self._link_table()

        with suspend_updates(table):
            current_selection, current_scroll_pos, sort_col, sort_order = (
                self._capture_ui_state()
            )

            if mode != self._current_mode:
                self._current_mode = mode
                self._full_populate(links, mode)
                self._restore_ui_state(
                    current_selection, current_scroll_pos, sort_col, sort_order
                )
                return

            try:
                self._block_signals()
                cache_ok = table.validate_cache_integrity()
                if not cache_ok:
                    table.rebuild_cache_from_items()

                if self._should_full_refresh(links, sort_col):
                    self._full_populate(links, mode)
                    return

                self._perform_incremental_update(links, mode, sort_col)

            except Exception as exc:
                self.logger.error(
                    "[LinksTableView] Incremental update error: %s",
                    exc,
                    exc_info=True,
                )
                self._full_populate(links, mode)
            finally:
                self._unblock_signals()
                self._restore_ui_state(
                    current_selection, current_scroll_pos, sort_col, sort_order
                )
                try:
                    if hasattr(self, "table_populated"):
                        self.table_populated.emit()
                except Exception as emit_exc:
                    self.logger.debug(
                        "[LinksTableView] Failed to emit table_populated after populate: %s",
                        emit_exc,
                        exc_info=True,
                    )

    def _full_populate(self, links: list[dict], mode: str) -> None:
        """Perform a full table refresh via the model."""
        table = self._link_table()
        try:
            # Update mode
            self._current_mode = mode
            # Push data into the model once
            model = table.model()
            if model is not None and hasattr(model, "set_links"):
                model.set_links(links)
            # Refresh cache from the model
            if hasattr(table, "rebuild_cache_from_items"):
                table.rebuild_cache_from_items()

        except Exception as e:
            self.logger.error(
                "[LinksTableView] Full refresh error: %s",
                e,
                exc_info=True,
            )
        finally:
            # Notify listeners that the table was fully refreshed
            try:
                if hasattr(self, "table_populated"):
                    self.table_populated.emit()
            except Exception as emit_exc:
                self.logger.debug(
                    "[LinksTableView] Failed to emit table_populated after _full_populate: %s",
                    emit_exc,
                    exc_info=True,
                )

    def _restore_ui_state(
        self,
        selection: list[int],
        scroll_pos: int,
        sort_col: int,
        sort_order: Qt.SortOrder,
    ):
        # Update stored sorting state
        self._sort_col = sort_col
        self._sort_order = sort_order
        """Restore UI state after an update."""
        try:
            # Restore sorting
            table = self._link_table()
            model = table.model()
            total_cols = model.columnCount() if model is not None else 0
            if sort_col != -1 and sort_col < total_cols:
                # Use ``sortByColumn`` for QTableView
                try:
                    table.sortByColumn(sort_col, sort_order)
                except Exception:
                    pass
                # IMPORTANT: sorting reindexes rows — sync ``_current_links`` with items
                # to avoid visual duplicates and incorrect updates
                try:
                    if hasattr(table, "rebuild_cache_from_items"):
                        table.rebuild_cache_from_items()
                except Exception as e:
                    self.logger.warning(
                        "[LinksTableView] Failed to rebuild cache after sorting: %s",
                        e,
                        exc_info=True,
                    )

            # Automatic selection restore intentionally removed for default Qt behavior

            # Restore scroll position
            scroll_bar = table.verticalScrollBar()
            if scroll_bar is not None:
                scroll_bar.setValue(scroll_pos)

            viewport = table.viewport()
            if viewport is not None:
                viewport.update()

        except Exception as e:
            self.logger.error(
                "[LinksTableView] Failed to restore UI state: %s",
                e,
                exc_info=True,
            )
