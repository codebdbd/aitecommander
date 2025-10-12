# app/utils/ui/dnd/link.py

"""Centralized DnD utilities for link tables/lists (Model/View).

Contains:
- Mixin for link tables working with QModelIndex and model;
- Helpers for extracting selected rows and restoring source rows from MIME via model data.

Note: API is oriented towards QTableView + QAbstractItemModel. Direct
dependencies on QTableWidget/QTableWidgetItem have been removed.
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

from PyQt6.QtCore import Qt

if TYPE_CHECKING:
    from PyQt6.QtCore import QModelIndex
    from app.views.widgets.protocols import LinkTableProtocol

from app.utils.ui.qt.roles import get_selected_rows as get_selected_rows_util

# Module logger
logger = logging.getLogger(__name__)


class DragDropHandlerMixin:
    """Mixin for handling Drag & Drop in link table (QTableView).
    
    This mixin expects to be used with a class that implements LinkTableProtocol.
    """
    
    # Type hint for the host class
    if TYPE_CHECKING:
        def __init__(self: "LinkTableProtocol") -> None: ...

    def _extract_item_ids_from_items(self, items) -> list[int]:
        """Extracts link IDs from selected indexes (QModelIndex).

        Expects ``items`` to be a sequence of ``QModelIndex``
        (e.g., from ``selectionModel().selectedIndexes()``). Identifiers
        are extracted via ``self.get_link_at(row)`` and model's ``UserRole``.
        """
        try:
            if not items:
                return []

            rows = sorted({getattr(item, "row", lambda: -1)() for item in items})
            ids = []

            model = getattr(self, "model", lambda: None)()
            total = (
                model.rowCount()
                if model is not None
                else getattr(self, "rowCount", lambda: 0)()
            )

            for row in rows:
                # Check boundaries
                if not (0 <= row < total):
                    logger.warning("[DRAG] Invalid row index: %s", row)
                    continue

                link_data = self.get_link_at(row)
                if link_data and "id" in link_data:
                    ids.append(link_data["id"])
                else:
                    logger.warning("[DRAG] Missing ID in row %s", row)

            return ids
        except Exception as e:
            logger.error("[DRAG] Error extracting IDs from items: %s", e)
            return []

    def _rebuild_current_links(self):
        """Clears and rebuilds _current_links cache from model.

        Called after operations changing row order (sorting, DnD).
        """
        try:
            self._current_links.clear()
            model = getattr(self, "model", lambda: None)()
            if not model:
                return

            for row in range(model.rowCount()):
                link_data = self.get_link_at(row)
                if link_data:
                    self._current_links[row] = link_data
        except Exception as e:
            logger.error("[DRAG] Error rebuilding links cache: %s", e)
            self._current_links.clear()  # On error cache should be empty

    def _move_row_visually(self, source_row: int, target_row: int):
        """Moves row via model and rebuilds cache.

        Uses `finally` to guarantee cache rebuilding.
        """
        try:
            model = getattr(self, "model", lambda: None)()
            if model is None:
                return
            # Call `move_rows` from model which should trigger begin/endMoveRows
            model.move_rows([source_row], target_row)
        except Exception as e:
            logger.error(
                "[LinksTableView] Error visual moving row %s -> %s: %s",
                source_row,
                target_row,
                e,
            )
        finally:
            # Cache is rebuilt in any case to reflect actual model state
            self._rebuild_current_links()

    def _get_current_order(self) -> list[int]:
        """Gets current order of link IDs by actual model row order."""
        try:
            model = getattr(self, "model", lambda: None)()
            total = model.rowCount() if model is not None else 0
            ids_in_order = []
            for row in range(total):
                link_data = self.get_link_at(row)
                if link_data and "id" in link_data:
                    ids_in_order.append(link_data["id"])
            return ids_in_order
        except Exception as e:
            logger.error("[DRAG] Error getting current links order: %s", e)
            return []

    def _get_drop_positions(self, event) -> tuple[list[int], int]:
        """Return source rows and insertion row for an internal drop."""

        try:
            source_rows = self._extract_source_rows_from_mime(event)
        except Exception as exc:
            logger.debug("[DROP] Failed to read rows from MIME: %s", exc, exc_info=True)
            source_rows = []

        if not source_rows:
            source_rows = self._get_selected_rows()

        source_rows = sorted({row for row in source_rows if isinstance(row, int)})

        target_row = -1
        row_count = 0
        try:
            pos = None
            if hasattr(event, "position"):
                pos_value = event.position()
                if hasattr(pos_value, "toPoint"):
                    pos = pos_value.toPoint()
                else:
                    pos = pos_value
            elif hasattr(event, "pos"):
                pos = event.pos()

            model = getattr(self, "model", lambda: None)()
            row_count = model.rowCount() if model is not None else 0

            if pos is not None and hasattr(self, "indexAt"):
                index = self.indexAt(pos)
            else:
                index = None

            if index is not None and index.isValid():
                target_row = index.row()
                if pos is not None and hasattr(self, "visualRect"):
                    rect = self.visualRect(index)
                    try:
                        mid_y = rect.center().y()
                    except Exception:
                        mid_y = rect.top() + rect.height() // 2
                    if pos.y() >= mid_y:
                        target_row = min(index.row() + 1, row_count)
            else:
                target_row = row_count
        except Exception as exc:
            logger.debug("[DROP] Failed to compute drop target row: %s", exc, exc_info=True)
            model = getattr(self, "model", lambda: None)()
            row_count = model.rowCount() if model is not None else 0
            target_row = row_count

        if target_row < 0:
            target_row = 0
        elif row_count and target_row > row_count:
            target_row = row_count

        return source_rows, target_row


# --- Reusable table helpers ---


def get_selected_rows(view) -> list[int]:
    """Gets sorted list of unique selected rows via common utility."""
    return get_selected_rows_util(view)


def extract_source_rows_from_mime(table, event, mime_type: str) -> list[int]:
    """Restores source row numbers from MIME data with IDs.

    Identifiers are extracted via ``MimeDataParser`` and matched with
    model data (``UserRole``) by first column. On error returns
    ``get_selected_rows(table)`` as fallback.
    """
    try:
        from app.utils.ui.dnd.mime import MimeDataParser

        item_ids = MimeDataParser.extract_item_ids(event.mimeData(), mime_type)
        if not item_ids:
            return []

        source_rows: list[int] = []
        model = getattr(table, "model", lambda: None)()
        total = model.rowCount() if model is not None else 0
        for row in range(total):
            idx = model.index(row, 0)
            data = model.data(idx, Qt.ItemDataRole.UserRole)
            link_id: Optional[int] = None
            if isinstance(data, dict):
                val = data.get("id")
                try:
                    link_id = int(val) if val is not None else None
                except Exception:
                    link_id = None
            if link_id is not None and link_id in item_ids:
                source_rows.append(row)
        return sorted(source_rows)
    except Exception as e:
        logger.warning("[DROP] Error extracting rows from MIME: %s", e)
        return get_selected_rows(table)


def move_row_visually(table, source_row: int, target_row: int) -> None:
    """Centrally moves one row and initiates cache update.

    If `table` has method `_rebuild_current_links`, it will be called.
    This avoids duplicating cache rebuilding logic.
    """
    try:
        model = getattr(table, "model", lambda: None)()
        if model is None:
            return
        model.move_rows([source_row], target_row)
    except Exception as e:
        logger.error(
            "[DnD] Error visual moving row %s->%s: %s",
            source_row,
            target_row,
            e,
        )
    finally:
        # If table has cache rebuilding method, use it.
        # This is main scenario when using DragDropHandlerMixin.
        if hasattr(table, "_rebuild_current_links") and callable(
            table._rebuild_current_links
        ):
            table._rebuild_current_links()
        else:
            logger.warning(
                "[DnD] Object %s has no _rebuild_current_links method. Cache may be outdated.",
                type(table).__name__,
            )


def move_rows_visually(table, source_rows: list[int], target_row: int) -> None:
    """Moves set of rows via model, preserving relative order."""
    if not source_rows:
        return
    model = getattr(table, "model", lambda: None)()
    if model is None:
        return
    model.move_rows(list(source_rows), target_row)


def get_current_order(table) -> list[int]:
    """Returns IDs of all elements in current table row order."""
    try:
        ids: list[int] = []
        model = getattr(table, "model", lambda: None)()
        total = model.rowCount() if model is not None else 0
        for row in range(total):
            try:
                link_data = table.get_link_at(row)
            except Exception:
                link_data = None
            if link_data and "id" in link_data:
                ids.append(link_data["id"])
        return ids
    except Exception as e:
        logger.error("[DnD] Error getting IDs order: %s", e)
        return []
