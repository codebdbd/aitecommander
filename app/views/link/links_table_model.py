# Модель данных для таблицы ссылок на основе QAbstractTableModel
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, QVariant
from PyQt6.QtGui import QIcon

from app.config_data import app_config
from app.utils.system.date_utils import format_last_used
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link


class LinksTableModel(QAbstractTableModel):
    """Табличная модель для ссылок.
    - Хранит список dict ссылок.
    - Поддерживает два режима отображения: "normal" и "search".
    - Заголовки отдает через headerData().
    - В UserRole возвращает исходный dict ссылки.
    """

    def __init__(self, links: Optional[List[Dict]] = None, mode: str = "normal", parent=None):
        super().__init__(parent)
        self._links: List[Dict] = list(links or [])
        self._mode: str = mode
        # Заголовки из конфигурации
        try:
            self._headers: List[str] = app_config.get_links_table_headers()
        except Exception:
            self._headers = ["★", "Название", "Открывалась", "Заметки"]

    # Публичные API
    def set_mode(self, mode: str):
        if mode == self._mode:
            return
        self._mode = mode
        # Меняется представление колонок (тексты/иконки/подсказки)
        self.dataChanged.emit(self.index(0, 0), self.index(max(0, self.rowCount() - 1), max(0, self.columnCount() - 1)))

    def set_links(self, links: List[Dict], mode: Optional[str] = None):
        t0 = time.perf_counter()
        if mode is not None:
            self._mode = mode
        self.beginResetModel()
        self._links = list(links or [])
        self.endResetModel()
        t1 = time.perf_counter()
        logging.debug(f"LinksTableModel.set_links rows={len(self._links)} took={(t1 - t0)*1000:.1f} ms")

    def insert_link(self, row: int, link: Dict) -> bool:
        t0 = time.perf_counter()
        row = max(0, min(row, len(self._links)))
        self.beginInsertRows(QModelIndex(), row, row)
        self._links.insert(row, link)
        self.endInsertRows()
        t1 = time.perf_counter()
        logging.debug(f"LinksTableModel.insert_link row={row} took={(t1 - t0)*1000:.1f} ms")
        return True

    def update_link(self, row: int, link: Dict) -> bool:
        t0 = time.perf_counter()
        if not (0 <= row < len(self._links)):
            return False
        self._links[row] = link
        top_left = self.index(row, 0)
        bottom_right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right, [
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.DecorationRole,
            Qt.ItemDataRole.ToolTipRole,
            Qt.ItemDataRole.TextAlignmentRole,
            Qt.ItemDataRole.UserRole,
        ])
        t1 = time.perf_counter()
        logging.debug(f"LinksTableModel.update_link row={row} took={(t1 - t0)*1000:.1f} ms")
        return True

    def remove_row(self, row: int) -> bool:
        t0 = time.perf_counter()
        if not (0 <= row < len(self._links)):
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._links[row]
        self.endRemoveRows()
        t1 = time.perf_counter()
        logging.debug(f"LinksTableModel.remove_row row={row} took={(t1 - t0)*1000:.1f} ms")
        return True

    # Базовые методы модели
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        if parent.isValid():
            return 0
        return len(self._links)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        if parent.isValid():
            return 0
        # 4 колонки для обоих режимов (икона/звезда, имя, last_used|path, notes)
        return len(self._headers)

    def headerData(self, section: int, orientation, role: int = Qt.ItemDataRole.DisplayRole):  # type: ignore[override]
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._headers):
                return self._headers[section]
        if role == Qt.ItemDataRole.TextAlignmentRole and orientation == Qt.Orientation.Horizontal:
            # Заголовок "Название" выравниваем по левому краю, остальные по центру
            try:
                name_col = app_config.get_links_table_columns().get("name", 1)
            except Exception:
                name_col = 1
            if section == name_col:
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # type: ignore[override]
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if not (0 <= row < len(self._links)):
            return None

        link = self._links[row]

        try:
            if role == Qt.ItemDataRole.UserRole:
                return link

            if role == Qt.ItemDataRole.TextAlignmentRole:
                if col == 0:
                    return int(Qt.AlignmentFlag.AlignCenter)
                if col == 2:
                    return int(Qt.AlignmentFlag.AlignCenter)
                return int(Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignLeft if col == 1 else Qt.AlignmentFlag.AlignCenter))

            if role == Qt.ItemDataRole.DecorationRole:
                # Иконка только для колонки Название (1)
                if col == 1:
                    try:
                        resolved_path = resolve_icon_for_link(link)
                        if resolved_path:
                            icon = create_icon_from_path(resolved_path)
                            if isinstance(icon, QIcon) and not icon.isNull():
                                return icon
                    except Exception:
                        pass
                return None

            if role == Qt.ItemDataRole.ToolTipRole:
                if self._mode == "search" and col == 1:
                    url_or_path = link.get("url", "") or link.get("path", "")
                    if url_or_path:
                        return f"<b>URL/Путь:</b> {url_or_path}"
                if col == 3:
                    notes_text = str(link.get("notes", "") or "")
                    return notes_text or None
                if col == 2 and self._mode == "search":
                    url_or_path = link.get("url", "") or link.get("path", "")
                    return url_or_path or None
                return None

            if role == Qt.ItemDataRole.DisplayRole:
                if col == 0:
                    return "★" if link.get("is_favorite", False) else ""
                if col == 1:
                    name_text = link.get("name", "")
                    if self._mode == "search":
                        # Добавляем путь категории
                        parts = [link.get("sphere_name", ""), link.get("section_name", ""), link.get("category_name", "")]
                        trail = " → ".join([p for p in parts if p])
                        if trail:
                            name_text = f"{name_text} ({trail})"
                    return name_text
                if col == 2:
                    if self._mode == "normal":
                        return format_last_used(link.get("last_used"))
                    else:  # search mode: URL/Path
                        return link.get("url", "") or link.get("path", "")
                if col == 3:
                    notes_text = str(link.get("notes", "") or "")
                    # Без тримминга — отображение полное; если нужен тримминг, лучше делать делегатом
                    return notes_text
                return None
        except Exception as e:
            logging.debug(f"[LinksTableModel] data() error at row={row}, col={col}: {e}")
            return None

        return None

    # Простая сортировка по колонке (для QTableView.setSortingEnabled(True))
    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:  # type: ignore[override]
        try:
            reverse = order == Qt.SortOrder.DescendingOrder
            key_fn = None
            if column == 0:
                key_fn = lambda l: 1 if l.get("is_favorite", False) else 0
            elif column == 1:
                key_fn = lambda l: (l.get("name") or "").lower()
            elif column == 2:
                if self._mode == "normal":
                    key_fn = lambda l: l.get("last_used") or 0
                else:
                    key_fn = lambda l: (l.get("url") or l.get("path") or "").lower()
            elif column == 3:
                key_fn = lambda l: (l.get("notes") or "").lower()
            if key_fn is None:
                return

            self.layoutAboutToBeChanged.emit()
            self._links.sort(key=key_fn, reverse=reverse)
            self.layoutChanged.emit()
        except Exception as e:
            logging.debug(f"[LinksTableModel] sort error: {e}")
