# Module for populating and updating the links table
# Provides bulk-update helpers

import logging

from PyQt6.QtCore import Qt

from app.utils.ui.updates import suspend_updates


class PopulationManagerMixin:
    # Module-level logger
    logger = logging.getLogger(__name__)

    """Mixin that populates and refreshes the links table."""

    def populate(self, links: list[dict], mode: str = "normal"):
        """Populate the table with link data using incremental updates."""
        if not isinstance(links, list):
            self.logger.warning(
                "[LinksTableView] Expected a list of links, got %s",
                type(links),
            )
            return

        # Optimization: suspend UI updates during bulk operations
        with suspend_updates(self):
            # Capture UI state
            try:
                sel = self.selectionModel()
                current_selection = [i.row() for i in sel.selectedRows()] if sel else []
            except Exception:
                self.logger.debug(
                    "populate: failed to capture selection", exc_info=True
                )
                current_selection = []
            current_scroll_pos = self.verticalScrollBar().value()

            # Preserve current sorting
            try:
                header = self.horizontalHeader()
                sort_col, sort_order = (
                    header.sortIndicatorSection(),
                    header.sortIndicatorOrder(),
                )
            except Exception:
                self.logger.debug(
                    "populate: failed to read sort state; using defaults", exc_info=True
                )
                sort_col, sort_order = -1, Qt.SortOrder.AscendingOrder

            # If the mode changed, trigger a full refresh
            if mode != self._current_mode:
                self._current_mode = mode
                self._full_populate(links, mode)
                self._restore_ui_state(
                    current_selection, current_scroll_pos, sort_col, sort_order
                )
                return

            # Incremental update
            try:
                # Safely block signals when APIs are available (tests may lack them)
                try:
                    if hasattr(self, "blockSignals"):
                        self.blockSignals(True)
                except Exception:
                    self.logger.debug(
                        "_restore_ui_state: sortByColumn failed", exc_info=True
                    )
                try:
                    header = self.horizontalHeader()
                    if header is not None and hasattr(header, "blockSignals"):
                        header.blockSignals(True)
                except Exception:
                    pass
                # Ensure cache consistency before diffing
                cache_ok = self.validate_cache_integrity()
                if not cache_ok:
                    self.rebuild_cache_from_items()

                # Without active sorting and ID order changed, fall back to full refresh
                def _ids_from_table() -> list:
                    ids = []
                    model = self.model()
                    total = model.rowCount() if model is not None else 0
                    for row in range(total):
                        data = self.get_link_at(row)
                        if data and "id" in data:
                            ids.append(data["id"])
                    return ids

                current_order = _ids_from_table()
                new_order = [link.get("id") for link in links if link and "id" in link]
                if (sort_col == -1) and current_order and (current_order != new_order):
                    self.logger.info(
                        "[LinksTableView] Detected ID order change without active sorting — performing full refresh"
                    )
                    self._full_populate(links, mode)
                    return

                current_ids = self._get_current_link_ids()
                new_ids = self._get_new_link_ids(links)
                new_link_map = self._create_link_id_to_data_map(links)

                # Detect differences
                ids_to_remove = current_ids - new_ids
                ids_to_add = new_ids - current_ids
                ids_to_check = current_ids & new_ids

                # If many rows changed, a full refresh is cheaper
                bulk_changes = len(ids_to_add) + len(ids_to_remove)
                if bulk_changes >= 30 or len(links) >= 200:
                    self.logger.info(
                        "[LinksTableView] Large number of changes (%s) — performing full refresh",
                        bulk_changes,
                    )
                    self._full_populate(links, mode)
                    return

                # Remove disappeared links (reverse order)
                rows_to_remove = []
                # Copy cache to avoid mutating while iterating
                current_links_copy = self._current_links.copy()
                for row, link in current_links_copy.items():
                    if link and link.get("id") in ids_to_remove:
                        rows_to_remove.append(row)

                # Sort indexes descending to delete safely
                for row in sorted(rows_to_remove, reverse=True):
                    removed_ok = False
                    try:
                        removed_ok = bool(self._remove_row(row))
                    except Exception as e:
                        self.logger.debug(
                            "[LinksTableView] _remove_row exception: %s",
                            e,
                            exc_info=True,
                        )
                        removed_ok = False
                    if not removed_ok:
                        self.logger.warning(
                            f"[LinksTableView] Failed to remove row {row} during incremental update"
                        )

                # Update modified links
                for row, current_link in list(self._current_links.items()):
                    if not current_link or current_link.get("id") not in ids_to_check:
                        continue

                    link_id = current_link.get("id")
                    new_link = new_link_map.get(link_id)

                    if new_link and not self._links_equal(current_link, new_link, mode):
                        self._update_row(row, new_link, mode)

                # Insert new links
                if ids_to_add:
                    # Pick insertion point for each new link
                    for i, link in enumerate(links):
                        link_id = link.get("id")
                        if link_id in ids_to_add:
                            # If sorted, append; otherwise insert near source index
                            model = self.model()
                            total = model.rowCount() if model is not None else 0
                            target_row = total if sort_col != -1 else min(i, total)
                            # Optimization: rebuild cache once afterward
                            self._add_row(target_row, link, mode)

                # Rebuild cache once after batch operations
                try:
                    if hasattr(self, "rebuild_cache_from_items"):
                        self.rebuild_cache_from_items()
                except Exception:
                    self.logger.debug(
                        "populate: rebuild_cache_from_items failed after incremental ops",
                        exc_info=True,
                    )

            except Exception as e:
                self.logger.error(
                    "[LinksTableView] Incremental update error: %s",
                    e,
                    exc_info=True,
                )
                # Fall back to full refresh on failure
                self._full_populate(links, mode)
            finally:
                # Always unblock signals when APIs are available
                try:
                    header = self.horizontalHeader()
                    if header is not None and hasattr(header, "blockSignals"):
                        header.blockSignals(False)
                except Exception:
                    self.logger.debug(
                        "populate: failed to unblock header signals", exc_info=True
                    )
                try:
                    if hasattr(self, "blockSignals"):
                        self.blockSignals(False)
                except Exception:
                    self.logger.debug(
                        "populate: failed to unblock table signals", exc_info=True
                    )
                self._restore_ui_state(
                    current_selection, current_scroll_pos, sort_col, sort_order
                )
                # Notify listeners about table refresh
                try:
                    if hasattr(self, "table_populated"):
                        self.table_populated.emit()
                except Exception as e:
                    self.logger.debug(
                        "[LinksTableView] Failed to emit table_populated after populate: %s",
                        e,
                        exc_info=True,
                    )

    def _full_populate(self, links: list[dict], mode: str):
        """Perform a full table refresh via the model."""
        try:
            # Update mode
            self._current_mode = mode
            # Push data into the model once
            model = self.model()
            if model is not None and hasattr(model, "set_links"):
                model.set_links(links)
            # Refresh cache from the model
            if hasattr(self, "rebuild_cache_from_items"):
                self.rebuild_cache_from_items()

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
            except Exception as e:
                self.logger.debug(
                    "[LinksTableView] Failed to emit table_populated after _full_populate: %s",
                    e,
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
            model = self.model()
            total_cols = model.columnCount() if model is not None else 0
            if sort_col != -1 and sort_col < total_cols:
                # Use ``sortByColumn`` for QTableView
                try:
                    self.sortByColumn(sort_col, sort_order)
                except Exception:
                    pass
                # IMPORTANT: sorting reindexes rows — sync ``_current_links`` with items
                # to avoid visual duplicates and incorrect updates
                try:
                    if hasattr(self, "rebuild_cache_from_items"):
                        self.rebuild_cache_from_items()
                except Exception as e:
                    self.logger.warning(
                        "[LinksTableView] Failed to rebuild cache after sorting: %s",
                        e,
                        exc_info=True,
                    )

            # Automatic selection restore intentionally removed for default Qt behavior

            # Restore scroll position
            self.verticalScrollBar().setValue(scroll_pos)

            self.viewport().update()

        except Exception as e:
            self.logger.error(
                "[LinksTableView] Failed to restore UI state: %s",
                e,
                exc_info=True,
            )
