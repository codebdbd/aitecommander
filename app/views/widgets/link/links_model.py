from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from PyQt6.QtCore import (
    QAbstractTableModel,
    QCoreApplication,
    QModelIndex,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget

from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.views.common.retranslatable import ReTranslatable
from app.views.widgets.link.columns import (
    LinkTableColumn,
    centered_columns,
    chevron_padding_columns,
    descriptor_for_column,
    header_sources,
    header_tooltips,
    is_column,
)
from app.views.widgets.link.item_builders import ItemBuildersMixin
from app.views.widgets.link.order_utils import move_link_position, move_rows_for_drop
from app.views.widgets.link.sort_utils import sorted_links

_HEADER_TRANSLATABLE = header_sources()
_HEADER_TOOLTIPS = header_tooltips()

if False:  # pragma: no cover - lupdate hints for descriptor-backed headers
    QCoreApplication.translate("LinksTableModel", "Name")
    QCoreApplication.translate("LinksTableModel", "Order")
    QCoreApplication.translate("LinksTableModel", "Launch")
    QCoreApplication.translate("LinksTableModel", "Notes")
    QCoreApplication.translate("LinksTableModel", "Type")
    QCoreApplication.translate("LinksTableModel", "Custom order")
    QCoreApplication.translate("LinksTableModel", "Last launch")
    QCoreApplication.translate("LinksTableModel", "Resource type")

HEADER_CHEVRON_PADDING_ROLE = int(Qt.ItemDataRole.UserRole) + 101
_CHEVRON_PADDING_SECTIONS = frozenset(chevron_padding_columns())
_CENTERED_SECTIONS = frozenset(centered_columns())


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


def clear_links_table_icon_cache() -> None:
    """Clear table-specific icon cache."""
    _get_icon_cached.cache_clear()


class LinksTableModel(QAbstractTableModel, ItemBuildersMixin, ReTranslatable):
    """Data model for the links table.

    Default columns: ["Name", "Order", "Launch", "Notes", "Type"].
    Each row is a dict containing at minimum: ``id``, ``name``, ``last_used``,
    ``notes``, ``is_favorite``, ``url``/``path``.
    """

    MAX_ICON_CACHE = 500  # Icon cache size limit
    groupLaunchToggled = pyqtSignal(int, int)  # link_id, val_int
    orderEdited = pyqtSignal(list)  # link IDs in the new order

    def __init__(
        self,
        links: Sequence[dict[str, Any]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
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
        self._headers = [self._tr(text) if text else "" for text in _HEADER_TRANSLATABLE]
        # Notify views about header text update
        if hasattr(self, "headerDataChanged"):
            self.headerDataChanged.emit(
                Qt.Orientation.Horizontal, 0, len(self._headers) - 1
            )

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

    def _call_column_builder(
        self,
        col: int,
        link: dict[str, Any],
        builder_attr: str,
    ) -> Any:
        descriptor = descriptor_for_column(col)
        if descriptor is None:
            return None
        builder_name = getattr(descriptor, builder_attr)
        if not builder_name:
            return None
        builder = getattr(self, builder_name, None)
        if builder is None:
            return None
        return builder(link)

    def _display_name(self, link: dict[str, Any]) -> str:
        return self._name_display_text(link, mode="normal")

    def _display_order(self, link: dict[str, Any]) -> int:
        return self._display_position(link)

    def _display_launch(self, link: dict[str, Any]) -> str:
        return self._last_used_display_text(link.get("last_used"))

    def _display_notes(self, link: dict[str, Any]) -> str:
        display, _ = self._notes_display_and_tooltip(
            link.get("notes", ""), truncate=False
        )
        return display

    def _display_type(self, link: dict[str, Any]) -> str:
        return self._type_display_text(link)

    def _tooltip_name(self, link: dict[str, Any]) -> str:
        return self._name_tooltip(link)

    def _tooltip_order(self, link: dict[str, Any]) -> str:
        return self._tr("Position: {position}").format(
            position=self._display_position(link)
        )

    def _tooltip_launch(self, link: dict[str, Any]) -> str:
        return self._last_used_tooltip(link.get("last_used"))

    def _tooltip_notes(self, link: dict[str, Any]) -> str:
        _, tip = self._notes_display_and_tooltip(
            link.get("notes", ""), truncate=False
        )
        return tip

    def _tooltip_type(self, link: dict[str, Any]) -> str:
        return self._type_tooltip(link)

    def _decoration_name(self, link: dict[str, Any]) -> QIcon | None:
        try:
            resolved_path = resolve_icon_for_link(link)
            if resolved_path:
                return self._get_cached_icon(resolved_path)
        except Exception:
            pass
        return None

    def _get_display_data(self, col, link):
        """Get display data for column."""
        return self._call_column_builder(col, link, "display_builder")

    def _get_decoration_data(self, col, link):
        """Get decoration data for column."""
        return self._call_column_builder(col, link, "decoration_builder")

    def _get_tooltip_data(self, col, link):
        """Get tooltip data for column."""
        return self._call_column_builder(col, link, "tooltip_builder")

    def _get_alignment_data(self, col):
        """Get alignment data for column."""
        if col in _CENTERED_SECTIONS:
            return int(Qt.AlignmentFlag.AlignCenter)
        return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def _display_position(self, link: dict[str, Any]) -> int:
        """Return one-based position for UI display."""
        try:
            return int(link.get("position", 0) or 0) + 1
        except Exception:
            return 1

    @staticmethod
    def _coerce_group_launch(value: Any) -> int:
        """Normalize persisted group-launch settings to database-compatible int."""
        if isinstance(value, str):
            return 1 if value.strip().lower() in {"1", "true", "yes", "on"} else 0
        return 1 if bool(value) else 0

    def _normalize_link(self, link: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
        """Return a row dict with canonical group-launch setting fields."""
        normalized = dict(link)
        has_group_launch = "is_group_launch" in normalized or "group_launch" in normalized
        if has_group_launch or not partial:
            value = normalized.get("is_group_launch", normalized.get("group_launch", 0))
            val_int = self._coerce_group_launch(value)
            normalized["is_group_launch"] = val_int
            normalized["group_launch"] = bool(val_int)
        return normalized

    def data(
        self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:  # type: ignore[override]
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if not (0 <= row < len(self._links)):
            return None

        link = self._links[row]

        if role == Qt.ItemDataRole.UserRole:
            return link

        if role == Qt.ItemDataRole.CheckStateRole:
            if is_column(col, LinkTableColumn.GROUP_LAUNCH):
                return (
                    Qt.CheckState.Checked
                    if bool(link.get("is_group_launch"))
                    else Qt.CheckState.Unchecked
                )
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            result = self._get_display_data(col, link)
            return result if result is not None else None

        if role == Qt.ItemDataRole.DecorationRole:
            result = self._get_decoration_data(col, link)
            return result if result is not None else None

        if role == Qt.ItemDataRole.ToolTipRole:
            result = self._get_tooltip_data(col, link)
            return result if result is not None else None

        if role == Qt.ItemDataRole.TextAlignmentRole:
            result = self._get_alignment_data(col)
            return result if result is not None else None

        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:  # type: ignore[override]
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DecorationRole and is_column(section, LinkTableColumn.GROUP_LAUNCH):
                from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache

                return icon_cache.get_icon("list_start")
            if role == Qt.ItemDataRole.DisplayRole:
                if 0 <= section < len(self._headers):
                    return self._headers[section]
            elif role == Qt.ItemDataRole.TextAlignmentRole:
                if section in _CENTERED_SECTIONS:
                    return int(Qt.AlignmentFlag.AlignCenter)
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            elif role == HEADER_CHEVRON_PADDING_ROLE:
                return section in _CHEVRON_PADDING_SECTIONS
            elif role == Qt.ItemDataRole.ToolTipRole:
                text = _HEADER_TOOLTIPS.get(section)
                if text:
                    return self._tr(text)
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # type: ignore[override]
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base_flags = (
            Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )
        if is_column(index.column(), LinkTableColumn.GROUP_LAUNCH):
            base_flags |= Qt.ItemFlag.ItemIsUserCheckable
        if is_column(index.column(), LinkTableColumn.ORDER):
            base_flags |= Qt.ItemFlag.ItemIsEditable
        return base_flags

    def setData(
        self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:  # type: ignore[override]
        """Programmatically update model data.

        Allowed column updates:
        0: ``is_group_launch`` (bool / check state)
        1: ``name`` (str)
        2: ``position`` (one-based UI number)
        3: ``last_used`` (any serializable/comparable type)
        4: ``notes`` (str)
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
                new_link = self._normalize_link(value)
                # Remove any external icon cache entry
                new_link.pop("_icon", None)
                self._links[row] = new_link
                top_left = self.index(row, int(LinkTableColumn.GROUP_LAUNCH))
                bottom_right = self.index(row, len(self._headers) - 1)
                # Indicate that decorations (icons) might have changed
                self.dataChanged.emit(
                    top_left, bottom_right, [Qt.ItemDataRole.DecorationRole]
                )
                return True

            if role == Qt.ItemDataRole.CheckStateRole and is_column(col, LinkTableColumn.GROUP_LAUNCH):
                checked = (value == Qt.CheckState.Checked.value) or (value == Qt.CheckState.Checked)
                val_int = 1 if checked else 0
                link["is_group_launch"] = val_int
                link["group_launch"] = bool(val_int)
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
                link_id = link.get("id")
                if link_id:
                    self.groupLaunchToggled.emit(link_id, val_int)
                return True

            if role in (Qt.ItemDataRole.EditRole, Qt.ItemDataRole.DisplayRole):
                if is_column(col, LinkTableColumn.NAME):
                    link["name"] = str(value)
                elif is_column(col, LinkTableColumn.ORDER):
                    return self._set_display_position(row, value)
                elif is_column(col, LinkTableColumn.LAUNCH):
                    # Store as-is; sort() performs normalization for ordering
                    link["last_used"] = value
                elif is_column(col, LinkTableColumn.NOTES):
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

    def _set_display_position(self, row: int, value: Any) -> bool:
        """Move row to the requested one-based position and renumber all links."""
        if not (0 <= row < len(self._links)):
            return False
        link_id = self._links[row].get("id")
        result = move_link_position(self._links, link_id, value)
        if result is None:
            return False
        if not result.moved and result.links == self._links:
            return True

        self.layoutAboutToBeChanged.emit()
        self._links = result.links
        self.layoutChanged.emit()
        self.orderEdited.emit(self.link_ids_in_order())
        return True

    def _renumber_positions(self) -> None:
        for index, link in enumerate(self._links):
            link["position"] = index

    def link_ids_in_order(self) -> list[int]:
        ids: list[int] = []
        for link in self._links:
            link_id = link.get("id")
            if isinstance(link_id, int):
                ids.append(link_id)
        return ids

    def supportedDropActions(self) -> Qt.DropAction:  # type: ignore[override]
        # Support moving rows only
        return Qt.DropAction.MoveAction

    def supportedDragActions(self) -> Qt.DropAction:  # type: ignore[override]
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
        self._links = [self._normalize_link(link_item) for link_item in links]
        self.endResetModel()

    def insert_link(self, pos: int, link: dict[str, Any]) -> bool:
        pos = max(0, min(pos, len(self._links)))
        self.beginInsertRows(QModelIndex(), pos, pos)
        self._links.insert(pos, self._normalize_link(link))
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
        self._links[row].update(self._normalize_link(new_data, partial=True))
        top_left = self.index(row, int(LinkTableColumn.GROUP_LAUNCH))
        bottom_right = self.index(row, len(self._headers) - 1)
        self.dataChanged.emit(
            top_left,
            bottom_right,
            [
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.EditRole,
                Qt.ItemDataRole.ToolTipRole,
                Qt.ItemDataRole.DecorationRole,
                Qt.ItemDataRole.CheckStateRole,
            ],
        )
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
        result = move_rows_for_drop(self._links, source_rows, target_row)
        if result is None or not result.moved:
            return
        if result.contiguous:
            if result.first is None or result.last is None or result.destination_child is None:
                return
            if not self.beginMoveRows(
                QModelIndex(),
                result.first,
                result.last,
                QModelIndex(),
                result.destination_child,
            ):
                return
            self._links = result.links
            self.endMoveRows()
            return

        id_to_new_row = {
            item.get("id"): row
            for row, item in enumerate(result.links)
            if item.get("id") is not None
        }

        self.layoutAboutToBeChanged.emit()
        try:
            old_parents = self.persistentIndexList()
            to_indexes = []
            for p_idx in old_parents:
                if p_idx.isValid() and p_idx.row() < len(self._links):
                    item = self._links[p_idx.row()]
                    new_r = id_to_new_row.get(item.get("id"))
                    if new_r is not None:
                        to_indexes.append(self.index(new_r, p_idx.column(), p_idx.parent()))
                    else:
                        to_indexes.append(p_idx)
                else:
                    to_indexes.append(p_idx)
            self._links = result.links
            if old_parents:
                self.changePersistentIndexList(old_parents, to_indexes)
        finally:
            self.layoutChanged.emit()

    # --- Sorting ---
    def sort(
        self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
    ) -> None:  # type: ignore[override]
        """Sort table data in response to ``QTableView`` header clicks.

        Supported columns:
        0: ``is_group_launch`` (bool)
        1: ``name`` (str, casefold)
        2: ``position`` (int)
        3: ``last_used`` (normalized to float timestamp; ``None`` -> ``-inf``)
        4: ``notes`` (str, casefold)
        5: ``type`` (localized label)
        """
        if not self._links or is_column(column, LinkTableColumn.GROUP_LAUNCH):
            return

        reverse = order == Qt.SortOrder.DescendingOrder
        self.layoutAboutToBeChanged.emit()
        self._links = sorted_links(
            self._links,
            column,
            descending=reverse,
            type_label_getter=self._type_display_text,
        )
        self.layoutChanged.emit()

    def _get_cached_icon(self, icon_path: str) -> QIcon | None:
        """Return an icon with LRU caching to avoid memory leaks.

        Args:
            icon_path: Path to the icon file.

        Returns:
            ``QIcon`` instance or ``None`` if loading fails.
        """
        return _get_icon_cached(icon_path)
