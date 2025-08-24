# app/utils/ui/dnd/link.py

"""Централизованные утилиты DnD для таблиц/списков ссылок (Model/View).

Содержит:
- Миксин для таблиц ссылок, работающий с QModelIndex и моделью;
- Хелперы для извлечения выбранных строк и восстановления строк-источников из MIME через данные модели.

Примечание: API ориентирован на QTableView + QAbstractItemModel. Прямых
зависимостей от QTableWidget/QTableWidgetItem не осталось.
"""

import logging
from typing import List, Optional

from PyQt6.QtCore import Qt


class DragDropHandlerMixin:
    """Миксин для обработки Drag & Drop в таблице ссылок (QTableView)."""

    def _extract_item_ids_from_items(self, items) -> List[int]:
        """Извлекает ID ссылок из выбранных индексов (QModelIndex).

        Ожидается, что ``items`` — это последовательность ``QModelIndex``
        (например, из ``selectionModel().selectedIndexes()``). Идентификаторы
        извлекаются через ``self.get_link_at(row)`` и роль ``UserRole`` модели.
        """
        try:
            if not items:
                return []

            rows = sorted({getattr(item, "row", lambda: -1)() for item in items})
            ids = []

            model = getattr(self, "model", lambda: None)()
            total = model.rowCount() if model is not None else getattr(self, "rowCount", lambda: 0)()

            for row in rows:
                # Проверка границ
                if not (0 <= row < total):
                    logging.warning(f"[DRAG] Некорректный индекс строки: {row}")
                    continue

                link_data = self.get_link_at(row)
                if link_data and "id" in link_data:
                    ids.append(link_data["id"])
                else:
                    logging.warning(f"[DRAG] Отсутствует ID в строке {row}")

            return ids
        except Exception as e:
            logging.error(f"[DRAG] Ошибка извлечения ID из элементов: {e}")
            return []

    def _move_row_visually(self, source_row: int, target_row: int):
        """Перемещает строку через модель (beginMoveRows/endMoveRows)."""
        try:
            model = getattr(self, "model", lambda: None)()
            if model is None:
                return
            model.move_rows([source_row], target_row)
            # Перестраиваем кэш на основе актуального порядка
            self._current_links.clear()
            for row in range(model.rowCount()):
                link_data = self.get_link_at(row)
                if link_data:
                    self._current_links[row] = link_data
        except Exception as e:
            logging.error(
                f"[LinksTableView] Ошибка визуального перемещения строки {source_row} -> {target_row}: {e}"
            )
            # Фолбэк: пересканирование кэша
            self._current_links.clear()
            model = getattr(self, "model", lambda: None)()
            total = model.rowCount() if model is not None else 0
            for row in range(total):
                link_data = self.get_link_at(row)
                if link_data:
                    self._current_links[row] = link_data

    def _get_current_order(self) -> List[int]:
        """Получает текущий порядок ID ссылок по фактическому порядку строк модели."""
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
            logging.error(f"[DRAG] Ошибка получения текущего порядка ссылок: {e}")
            return []


# --- Переиспользуемые хелперы для таблиц ---


def get_selected_rows(table) -> List[int]:
    """Возвращает отсортированный список уникальных выбранных строк (QTableView).

    Использует ``selectionModel().selectedIndexes()`` и агрегирует уникальные
    номера строк. Совместимо с любой реализацией на базе ``QAbstractItemView``
    и моделью ``QAbstractItemModel``.
    """
    try:
        selection_model = table.selectionModel()
        if not selection_model:
            return []

        selected_rows = set()

        # Индексы из selectionModel
        for index in selection_model.selectedIndexes():
            if index.isValid():
                selected_rows.add(index.row())

        # Альтернатива через selectedRanges
        if not selected_rows:
            for selection_range in selection_model.selectedRanges():
                for row in range(selection_range.top(), selection_range.bottom() + 1):
                    selected_rows.add(row)

        return sorted(selected_rows)
    except Exception:
        return []


def extract_source_rows_from_mime(table, event, mime_type: str) -> List[int]:
    """Восстанавливает номера строк-источников из MIME-данных с ID.

    Идентификаторы извлекаются через ``MimeDataParser`` и сопоставляются с
    данными модели (``UserRole``) по первой колонке. При ошибке возвращает
    ``get_selected_rows(table)`` как фолбэк.
    """
    try:
        from app.utils.ui.dnd.mime import MimeDataParser

        item_ids = MimeDataParser.extract_item_ids(event.mimeData(), mime_type)
        if not item_ids:
            return []

        source_rows: List[int] = []
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
        logging.warning(f"[DROP] Ошибка извлечения строк из MIME: {e}")
        return get_selected_rows(table)


def move_row_visually(table, source_row: int, target_row: int) -> None:
    """Централизованно перемещает одну строку через модель и обновляет кэш."""
    try:
        model = getattr(table, "model", lambda: None)()
        if model is None:
            return
        model.move_rows([source_row], target_row)
        # Перестроить кэш
        if hasattr(table, "_current_links"):
            table._current_links.clear()
            for row in range(model.rowCount()):
                try:
                    link_data = table.get_link_at(row)
                except Exception:
                    link_data = None
                if link_data:
                    table._current_links[row] = link_data
    except Exception as e:
        logging.error(
            f"[DnD] Ошибка визуального перемещения строки {source_row}->{target_row}: {e}"
        )
        if hasattr(table, "_current_links"):
            table._current_links.clear()
            model = getattr(table, "model", lambda: None)()
            total = model.rowCount() if model is not None else 0
            for row in range(total):
                try:
                    link_data = table.get_link_at(row)
                except Exception:
                    link_data = None
                if link_data:
                    table._current_links[row] = link_data


def move_rows_visually(table, source_rows: List[int], target_row: int) -> None:
    """Перемещает набор строк через модель, сохраняя относительный порядок."""
    if not source_rows:
        return
    model = getattr(table, "model", lambda: None)()
    if model is None:
        return
    model.move_rows(list(source_rows), target_row)


def get_current_order(table) -> List[int]:
    """Возвращает ID всех элементов в текущем порядке строк таблицы."""
    try:
        ids: List[int] = []
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
        logging.error(f"[DnD] Ошибка получения порядка IDs: {e}")
        return []
