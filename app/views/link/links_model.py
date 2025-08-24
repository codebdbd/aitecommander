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

    # --- Мутации данных ---
    def set_headers(self, headers: Sequence[str]) -> None:
        headers = list(headers)
        if headers == self._headers:
            return
        self._headers = headers
        # Более дешёвый сигнал изменения заголовков
        from PyQt6.QtCore import QPersistentModelIndex

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

        # Разреженный набор: перемещаем последовательно, сохраняя относительный порядок
        # Стратегия: переносим снизу вверх, чтобы индексы меньше сдвигались
        for i, row in enumerate(reversed(src)):
            # при переносе вниз target сдвигается на -1 для каждой уже перенесённой строки ниже
            insert_at = target_row
            if row < target_row:
                insert_at -= 1
            if not self.beginMoveRows(QModelIndex(), row, row, QModelIndex(), insert_at):
                continue
            item = self._links.pop(row)
            # корректируем позицию после pop
            if insert_at > row:
                insert_at -= 1
            self._links.insert(insert_at, item)
            self.endMoveRows()

    # --- Сортировка ---
    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:  # type: ignore[override]
        """Сортировка данных модели по клику в заголовке QTableView.

        Поддерживаются колонки:
        0: is_favorite (bool)
        1: name (str, casefold)
        2: last_used (считается как timestamp/сравнимое значение)
        3: notes (str, casefold)
        """
        if not self._links:
            return

        def key_for(link: Dict[str, Any]):
            try:
                if column == 0:
                    # Сортируем по False/True; для Descending True пойдёт вверх
                    return bool(link.get("is_favorite", False))
                if column == 1:
                    return str(link.get("name", "")).casefold()
                if column == 2:
                    v = link.get("last_used")
                    # Нормализуем к числу/сравнимому значению
                    if v is None:
                        return 0
                    # Частые варианты: int/float/str/datetime-like
                    try:
                        # Если уже число
                        return float(v)  # type: ignore[arg-type]
                    except Exception:
                        pass
                    try:
                        # Попытка ISO-строки времени
                        from datetime import datetime

                        return datetime.fromisoformat(str(v)).timestamp()
                    except Exception:
                        pass
                    # Фолбэк: строковое сравнение
                    return str(v)
                if column == 3:
                    return str(link.get("notes", "")).casefold()
            except Exception:
                # Любая ошибка ключа не должна ломать сортировку
                return 0
            # Неизвестная колонка — сортируем по индексу для детерминизма
            return 0

        reverse = order == Qt.SortOrder.DescendingOrder
        self.layoutAboutToBeChanged.emit()
        try:
            self._links.sort(key=key_for, reverse=reverse)
        except Exception:
            # В случае ошибки сортировки не падаем, просто пропускаем
            pass
        self.layoutChanged.emit()
