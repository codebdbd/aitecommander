from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from PyQt6.QtCore import (
    QAbstractTableModel,
    QCoreApplication,
    QModelIndex,
    Qt,
    QVariant,
)
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget

from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.views.common.retranslatable import ReTranslatable
from app.views.widgets.link.item_builders import ItemBuildersMixin

# Global icon cache to avoid memory leaks with lru_cache on methods
@lru_cache(maxsize=100)
def _get_icon_cached(icon_path: str) -> QIcon | None:
    """Global icon cache function to avoid memory leaks."""
    if not icon_path:
        return None
    try:
        icon = create_icon_from_path(icon_path)
        return icon if isinstance(icon, QIcon) and not icon.isNull() else None
    except Exception:
        return None


class LinksTableModel(QAbstractTableModel, ItemBuildersMixin, ReTranslatable):
    """Data model for the links table.

    Default columns: ["♥", "Name", "Last opened", "Notes"].
    Each row is a dict containing at minimum: ``id``, ``name``, ``last_used``,
    ``notes``, ``is_favorite``, ``url``/``path``.
    """

    DEFAULT_HEADERS = ["♥", "Name", "Last opened", "Notes"]  # source strings
    MAX_ICON_CACHE = 500  # Icon cache size limit

    def __init__(self, links: Sequence[dict[str, Any]] | None = None, parent: QWidget | None = None) -> None:
        QAbstractTableModel.__init__(self, parent)
        ReTranslatable.__init__(self)
        self._headers: list[str] = []
        self._links: list[dict[str, Any]] = []
        # Initialize while cleaning potential icon cache entries
        self.retranslateUi()
        if links:
            self.set_links(links)

    # --- i18n helpers ---
    @staticmethod
    def _tr(text: str) -> str:
        return QCoreApplication.translate("LinksTableModel", text)

    def retranslateUi(self) -> None:
        """Refresh localized headers (call on language change)."""
        self._headers = [
            self._tr("♥"),
            self._tr("Name"),
            self._tr("Last opened"),
            self._tr("Notes"),
        ]
        # Notify views about header text update
        if hasattr(self, "headerDataChanged"):
            self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(self._headers) - 1)

    # --- Required methods ---
    def rowCount(self, parent: QModelIndex | None = None) -> int:  # type: ignore[override]
        if parent is None:
            parent = QModelIndex()
        if parent.isValid():
            return 0
        return len(self._links)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # type: ignore[override]
        if parent is None:
            parent = QModelIndex()
        if parent.isValid():
            return 0
        return len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> str | int | QIcon | dict | None:  # type: ignore[override]
        if not index.isValid():
            return QVariant()
        row = index.row()
        col = index.column()
        if not (0 <= row < len(self._links)):
            return QVariant()

        link = self._links[row]

        # UserRole: return the original link dict
        if role == Qt.ItemDataRole.UserRole:
            return link

        # Display/Decoration/ToolTip per column
        # 0: ★, 1: Name, 2: Last opened, 3: Notes
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return self._star_display_text(bool(link.get("is_favorite")))
            if col == 1:
                # Always "normal" mode here; search uses a separate model/view
                return self._name_display_text(link, mode="normal")
            if col == 2:
                return self._last_used_display_text(link.get("last_used"))
            if col == 3:
                display, _ = self._notes_display_and_tooltip(
                    link.get("notes", ""), truncate=False
                )
                return display

        if role == Qt.ItemDataRole.DecorationRole:
            if col == 1:
                # Link icon: use LRU cache to avoid memory leaks
                try:
                    resolved_path = resolve_icon_for_link(link)
                    if resolved_path:
                        return self._get_cached_icon(resolved_path)
                except Exception:
                    pass

        if role == Qt.ItemDataRole.ToolTipRole:
            if col == 1:
                tip = self._name_tooltip(link)
                if tip:
                    return tip
            if col == 3:
                _, tip = self._notes_display_and_tooltip(
                    link.get("notes", ""), truncate=False
                )
                if tip:
                    return tip

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 2):
                return int(Qt.AlignmentFlag.AlignCenter)

        return QVariant()

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:  # type: ignore[override]
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            if 0 <= section < len(self._headers):
                return self._headers[section]
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:  # type: ignore[override]
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        # By default the table is not editable via delegates
        return (
            Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )

    def setData(
        self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:  # type: ignore[override]
        """Programmatically update model data.

        Allowed column updates:
        0: ``is_favorite`` (bool)
        1: ``name`` (str)
        2: ``last_used`` (any serializable/comparable type)
        3: ``notes`` (str)
        Direct replacement of the entire link is also supported via ``UserRole`` (dict value).
        """
        if not index.isValid():
            return False
        row, col = index.row(), index.column()
        if not (0 <= row < len(self._links)):
            return False

        link = self._links[row]

        try:
            if role == Qt.ItemDataRole.UserRole and isinstance(value, dict):
                # Replace the link dict entirely
                new_link = dict(value)
                # Remove any external icon cache entry
                new_link.pop("_icon", None)
                self._links[row] = new_link
                top_left = self.index(row, 0)
                bottom_right = self.index(row, len(self._headers) - 1)
                # Indicate that decorations (icons) might have changed
                self.dataChanged.emit(
                    top_left, bottom_right, [Qt.ItemDataRole.DecorationRole]
                )
                return True

            if role in (Qt.ItemDataRole.EditRole, Qt.ItemDataRole.DisplayRole):
                if col == 0:
                    link["is_favorite"] = bool(value)
                elif col == 1:
                    link["name"] = str(value)
                elif col == 2:
                    # Store as-is; sort() performs normalization for ordering
                    link["last_used"] = value
                elif col == 3:
                    link["notes"] = str(value)
                else:
                    return False
                # Any change may affect visuals — clear the cached icon
                link.pop("_icon", None)
                self.dataChanged.emit(
                    index, index, [role, Qt.ItemDataRole.DecorationRole]
                )
                return True
        except Exception:
            return False

        return False

    def supportedDropActions(self) -> Qt.DropActions:  # type: ignore[override]
        # Support moving rows only
        return Qt.DropAction.MoveAction

    def supportedDragActions(self) -> Qt.DropActions:  # type: ignore[override]
        return Qt.DropAction.MoveAction

    # --- Data mutations ---
    def set_headers(self, headers: Sequence[str]) -> None:
        headers = list(headers)
        if headers == self._headers:
            return
        self._headers = headers
        # Cheaper header-changed notification

        self.headerDataChanged.emit(
            Qt.Orientation.Horizontal, 0, len(self._headers) - 1
        )

    def set_links(self, links: Sequence[dict[str, Any]]) -> None:
        self.beginResetModel()
        # Clone data (icons now live in the LRU cache, not inside dicts)
        self._links = [dict(link_item) for link_item in links]
        self.endResetModel()

    def insert_link(self, pos: int, link: dict[str, Any]) -> bool:
        pos = max(0, min(pos, len(self._links)))
        self.beginInsertRows(QModelIndex(), pos, pos)
        self._links.insert(pos, dict(link))
        self.endInsertRows()
        return True

    def append_link(self, link: dict[str, Any]) -> bool:
        return self.insert_link(len(self._links), link)

    def remove_row(self, row: int) -> bool:
        if not (0 <= row < len(self._links)):
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._links[row]
        self.endRemoveRows()
        return True

    def update_link(self, row: int, new_data: dict[str, Any]) -> bool:
        if not (0 <= row < len(self._links)):
            return False
        self._links[row].update(new_data)
        # Icon refresh happens automatically through the LRU cache
        top_left = self.index(row, 0)
        bottom_right = self.index(row, len(self._headers) - 1)
        self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DecorationRole])
        return True

    # --- Helper methods ---
    def get_link(self, row: int) -> dict[str, Any] | None:
        if 0 <= row < len(self._links):
            return self._links[row]
        return None

    def find_row_by_id(self, link_id: Any) -> int:
        for i, link in enumerate(self._links):
            if link.get("id") == link_id:
                return i
        return -1

    # --- Row reordering ---
    def move_rows(self, source_rows: list[int], target_row: int) -> None:
        """Move a set of rows while preserving relative order.

        For a single continuous range use ``beginMoveRows``/``endMoveRows``.
        For sparse indices perform sequential moves.
        """
        if not source_rows:
            return
        n = len(self._links)
        src = [r for r in sorted(set(source_rows)) if 0 <= r < n]
        if not src:
            return
        # Normalize target
        target_row = max(0, min(target_row, n))

        # When the rows form one contiguous range — use an atomic move
        def is_contiguous(rows: list[int]) -> bool:
            """Check whether rows form a contiguous range."""
            return all(b - a == 1 for a, b in zip(rows, rows[1:]))

        if len(src) == 1 or is_contiguous(src):
            first = src[0]
            last = src[-1]
            # Adjust the target when moving downward
            insert_row = target_row
            if insert_row > last + 1:
                insert_row = insert_row
            elif insert_row <= first:
                insert_row = insert_row
            else:
                # If the target falls inside the range, treat as no-op
                return

            if not self.beginMoveRows(
                QModelIndex(), first, last, QModelIndex(), insert_row
            ):
                return
            # Extract the segment and insert it at the new location
            segment = self._links[first : last + 1]
            del self._links[first : last + 1]
            # Adjust insert position after deletion
            if insert_row > first:
                insert_row -= last - first + 1
            for i, item in enumerate(segment):
                self._links.insert(insert_row + i, item)
            self.endMoveRows()
            return

        # Sparse set: reorder via a single ``layoutChanged`` pass
        # Semantics: remove selected rows, then insert them (in original order)
        # at ``target_row`` among remaining elements WITHOUT subtracting removals before target.
        # Matches user expectation of "insert before the item that was at target_row prior to move".
        src_set = set(src)
        remaining: list[dict[str, Any]] = [
            item for i, item in enumerate(self._links) if i not in src_set
        ]
        segment: list[dict[str, Any]] = [self._links[i] for i in src]
        insert_at = max(0, min(target_row, len(remaining)))
        self.layoutAboutToBeChanged.emit()
        try:
            self._links = remaining[:insert_at] + segment + remaining[insert_at:]
        finally:
            self.layoutChanged.emit()

    # --- Sorting ---
    def sort(
        self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
    ) -> None:  # type: ignore[override]
        """Sort table data in response to ``QTableView`` header clicks.

        Supported columns:
        0: ``is_favorite`` (bool)
        1: ``name`` (str, casefold)
        2: ``last_used`` (normalized to float timestamp; ``None`` -> ``-inf``)
        3: ``notes`` (str, casefold)
        """
        if not self._links:
            return

        def normalize_last_used(v: Any) -> float:
            """Return numeric timestamp for ``last_used``.
            Returns ``-inf`` when value is missing or cannot be parsed.
            """
            from math import inf

            if v is None:
                return -inf
            # Already numeric
            try:
                return float(v)  # type: ignore[arg-type]
            except Exception:
                pass
            # ISO datetime string
            try:
                from datetime import datetime

                return datetime.fromisoformat(str(v)).timestamp()
            except Exception:
                pass
            # Fallback: hash-stabilized string representation -> number (deterministic)
            try:
                return float(abs(hash(str(v))))
            except Exception:
                return -inf

        def key_for(link: dict[str, Any]) -> Any:
            if column == 0:
                # Cast to int for comparison to avoid mixing types
                return 1 if bool(link.get("is_favorite", False)) else 0
            if column == 1:
                return str(link.get("name", "")).casefold()
            if column == 2:
                return normalize_last_used(link.get("last_used"))
            if column == 3:
                return str(link.get("notes", "")).casefold()
            # Unknown column — sort by stable ``id`` if available, otherwise index order
            lid = link.get("id")
            try:
                return int(lid)
            except Exception:
                return self._links.index(link)

        reverse = order == Qt.SortOrder.DescendingOrder
        self.layoutAboutToBeChanged.emit()
        self._links.sort(key=key_for, reverse=reverse)
        self.layoutChanged.emit()

    def _get_cached_icon(self, icon_path: str) -> QIcon | None:
        """Return an icon with LRU caching to avoid memory leaks.

        Args:
            icon_path: Path to the icon file.

        Returns:
            ``QIcon`` instance or ``None`` if loading fails.
        """
        return _get_icon_cached(icon_path)
