from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, QVariant
from PyQt6.QtGui import QIcon

from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.views.link.item_builders import ItemBuildersMixin


class LinksTableModel(QAbstractTableModel, ItemBuildersMixin):
    """Модель данных для таблицы ссылок.

    Колонки по умолчанию: ["★", "Название", "Открывалась", "Заметки"].
    Данные строки — dict с полями как минимум: id, name, last_used, notes, is_favorite, url/path.
    """

    DEFAULT_HEADERS = ["★", "Название", "Открывалась", "Заметки"]

    def __init__(self, links: Optional[Sequence[Dict[str, Any]]] = None, parent=None):
        super().__init__(parent)
        self._headers: List[str] = list(self.DEFAULT_HEADERS)
        self._links: List[Dict[str, Any]] = list(links) if links else []

    # --- Обязательные методы ---
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        if parent.isValid():
            return 0
        return len(self._links)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # type: ignore[override]
        if parent.isValid():
            return 0
        return len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:  # type: ignore[override]
        if not index.isValid():
            return QVariant()
        row = index.row()
        col = index.column()
        if not (0 <= row < len(self._links)):
            return QVariant()

        link = self._links[row]

        # UserRole: возвращаем исходный dict ссылки
        if role == Qt.ItemDataRole.UserRole:
            return link

        # Display/Decoration/ToolTip по колонкам
        # 0: ★, 1: Название, 2: Открывалась, 3: Заметки
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return self._star_display_text(bool(link.get("is_favorite")))
            if col == 1:
                # Здесь всегда "normal" режим; поиск использует отдельную модель/вид
                return self._name_display_text(link, mode="normal")
            if col == 2:
                return self._last_used_display_text(link.get("last_used"))
            if col == 3:
                display, _ = self._notes_display_and_tooltip(link.get("notes", ""), truncate=False)
                return display

        if role == Qt.ItemDataRole.DecorationRole:
            if col == 1:
                # Иконка ссылки: ленивое разрешение и кэширование в link["_icon"]
                icon: Optional[QIcon] = link.get("_icon")
                if isinstance(icon, QIcon) and not icon.isNull():
                    return icon
                try:
                    resolved_path = resolve_icon_for_link(link)
                    if resolved_path:
                        icon = create_icon_from_path(resolved_path)
                        if isinstance(icon, QIcon) and not icon.isNull():
                            link["_icon"] = icon
                            return icon
                except Exception:
                    pass

        if role == Qt.ItemDataRole.ToolTipRole:
            if col == 1:
                tip = self._name_tooltip(link)
                if tip:
                    return tip
            if col == 3:
                _, tip = self._notes_display_and_tooltip(link.get("notes", ""), truncate=False)
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
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self._headers):
                return self._headers[section]
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:  # type: ignore[override]
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        # По умолчанию таблица не редактируема через делегаты
        return (
            Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )

    def setData(
        self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:  # type: ignore[override]
        """Обновляет данные модели программно.

        Разрешаем обновлять поля ссылки по колонкам:
        0: is_favorite (bool)
        1: name (str)
        2: last_used (любой сериализуемый/сравнимый тип)
        3: notes (str)
        Также поддерживаем прямую замену всей ссылки через UserRole (value: dict).
        """
        if not index.isValid():
            return False
        row, col = index.row(), index.column()
        if not (0 <= row < len(self._links)):
            return False

        link = self._links[row]

        try:
            if role == Qt.ItemDataRole.UserRole and isinstance(value, dict):
                # Полная замена словаря ссылки
                self._links[row] = dict(value)
                top_left = self.index(row, 0)
                bottom_right = self.index(row, len(self._headers) - 1)
                self.dataChanged.emit(top_left, bottom_right, [])
                return True

            if role in (Qt.ItemDataRole.EditRole, Qt.ItemDataRole.DisplayRole):
                if col == 0:
                    link["is_favorite"] = bool(value)
                elif col == 1:
                    link["name"] = str(value)
                elif col == 2:
                    # Храним как есть; нормализация для сортировки выполняется в sort()
                    link["last_used"] = value
                elif col == 3:
                    link["notes"] = str(value)
                else:
                    return False
                self.dataChanged.emit(index, index, [role])
                return True
        except Exception:
            return False

        return False

    def supportedDropActions(self) -> Qt.DropActions:  # type: ignore[override]
        # Поддерживаем только перемещение строк
        return Qt.DropAction.MoveAction

    def supportedDragActions(self) -> Qt.DropActions:  # type: ignore[override]
        return Qt.DropAction.MoveAction

    # --- Мутации данных ---
    def set_headers(self, headers: Sequence[str]) -> None:
        headers = list(headers)
        if headers == self._headers:
            return
        self._headers = headers
        # Более дешёвый сигнал изменения заголовков

        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(self._headers) - 1)

    def set_links(self, links: Sequence[Dict[str, Any]]) -> None:
        self.beginResetModel()
        self._links = list(links)
        self.endResetModel()

    def insert_link(self, pos: int, link: Dict[str, Any]) -> bool:
        pos = max(0, min(pos, len(self._links)))
        self.beginInsertRows(QModelIndex(), pos, pos)
        self._links.insert(pos, dict(link))
        self.endInsertRows()
        return True

    def append_link(self, link: Dict[str, Any]) -> bool:
        return self.insert_link(len(self._links), link)

    def remove_row(self, row: int) -> bool:
        if not (0 <= row < len(self._links)):
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._links[row]
        self.endRemoveRows()
        return True

    def update_link(self, row: int, new_data: Dict[str, Any]) -> bool:
        if not (0 <= row < len(self._links)):
            return False
        self._links[row].update(new_data)
        top_left = self.index(row, 0)
        bottom_right = self.index(row, len(self._headers) - 1)
        self.dataChanged.emit(top_left, bottom_right, [])
        return True

    # --- Вспомогательные методы ---
    def get_link(self, row: int) -> Optional[Dict[str, Any]]:
        if 0 <= row < len(self._links):
            return self._links[row]
        return None

    def find_row_by_id(self, link_id: Any) -> int:
        for i, link in enumerate(self._links):
            if link.get("id") == link_id:
                return i
        return -1

    # --- Перемещение строк ---
    def move_rows(self, source_rows: List[int], target_row: int) -> None:
        """Перемещает набор строк в модели, сохраняя относительный порядок.

        Для одиночного диапазона использует beginMoveRows/endMoveRows.
        Для разреженных индексов выполняет последовательные перемещения.
        """
        if not source_rows:
            return
        n = len(self._links)
        src = [r for r in sorted(set(source_rows)) if 0 <= r < n]
        if not src:
            return
        # Нормализуем target
        target_row = max(0, min(target_row, n))

        # Если один непрерывный диапазон — используем атомарный move
        def is_contiguous(rows: List[int]) -> bool:
            return all(b - a == 1 for a, b in zip(rows, rows[1:]))

        if len(src) == 1 or is_contiguous(src):
            first = src[0]
            last = src[-1]
            # Корректируем target, если переносим вниз
            insert_row = target_row
            if insert_row > last + 1:
                insert_row = insert_row
            elif insert_row <= first:
                insert_row = insert_row
            else:
                # если цель попадает внутрь диапазона, считаем как no-op
                return

            if not self.beginMoveRows(QModelIndex(), first, last, QModelIndex(), insert_row):
                return
            # Извлекаем сегмент и вставляем
            segment = self._links[first : last + 1]
            del self._links[first : last + 1]
            # Корректируем позицию вставки после удаления
            if insert_row > first:
                insert_row -= (last - first + 1)
            for i, item in enumerate(segment):
                self._links.insert(insert_row + i, item)
            self.endMoveRows()
            return

        # Разреженный набор: переупорядочиваем список одним проходом через layoutChanged
        # Семантика: удаляем выбранные строки, затем вставляем их (в исходном порядке)
        # в позицию target_row с учётом сдвига индексов после удаления исходных строк.
        removed_before_target = sum(1 for r in src if r < target_row)
        adjusted_target = target_row - removed_before_target
        # Строим списки
        src_set = set(src)
        remaining: List[Dict[str, Any]] = [item for i, item in enumerate(self._links) if i not in src_set]
        segment: List[Dict[str, Any]] = [self._links[i] for i in src]
        insert_at = max(0, min(adjusted_target, len(remaining)))
        self.layoutAboutToBeChanged.emit()
        try:
            self._links = remaining[:insert_at] + segment + remaining[insert_at:]
        finally:
            self.layoutChanged.emit()

    # --- Сортировка ---
    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:  # type: ignore[override]
        """Сортировка данных модели по клику в заголовке QTableView.

        Поддерживаются колонки:
        0: is_favorite (bool)
        1: name (str, casefold)
        2: last_used (нормализуется в float timestamp; None -> -inf)
        3: notes (str, casefold)
        """
        if not self._links:
            return

        def normalize_last_used(v: Any) -> float:
            """Возвращает числовой timestamp для last_used.
            Возвращает -inf (очень старое), если значение отсутствует/непарсибельно.
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
            # Fallback: хеш-стабилизированное строковое представление -> число (детерминизм)
            try:
                return float(abs(hash(str(v))))
            except Exception:
                return -inf

        def key_for(link: Dict[str, Any]):
            if column == 0:
                # Приводим к int для сравнения, чтобы исключить смешение типов
                return 1 if bool(link.get("is_favorite", False)) else 0
            if column == 1:
                return str(link.get("name", "")).casefold()
            if column == 2:
                return normalize_last_used(link.get("last_used"))
            if column == 3:
                return str(link.get("notes", "")).casefold()
            # Неизвестная колонка — сортируем по стабильному индексу id, иначе по позиции
            lid = link.get("id")
            try:
                return int(lid)
            except Exception:
                return self._links.index(link)

        reverse = order == Qt.SortOrder.DescendingOrder
        self.layoutAboutToBeChanged.emit()
        self._links.sort(key=key_for, reverse=reverse)
        self.layoutChanged.emit()
