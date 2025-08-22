# app/utils/dnd/link.py

"""Централизованные утилиты DnD для таблиц/списков ссылок.

Содержит:
- Миксин для таблиц ссылок (совместим с существующими реализациями);
- Переиспользуемые хелперы для извлечения выбранных строк и восстановления строк-источников из MIME.
"""

import logging
from typing import List


class DragDropHandlerMixin:
    """Миксин для обработки Drag & Drop в таблице ссылок."""

    def _extract_item_ids_from_items(self, items) -> List[int]:
        """Извлекает ID ссылок из выбранных элементов."""
        try:
            if not items:
                return []

            rows = sorted({item.row() for item in items})
            ids = []

            for row in rows:
                # Проверка границ
                if not (0 <= row < self.rowCount()):
                    logging.warning(f"[DRAG] Некорректный индекс строки: {row}")
                    continue

                link_data = self.get_link_at(row)
                if link_data and 'id' in link_data:
                    ids.append(link_data['id'])
                else:
                    logging.warning(f"[DRAG] Отсутствует ID в строке {row}")

            return ids
        except Exception as e:
            logging.error(f"[DRAG] Ошибка извлечения ID из элементов: {e}")
            return []

    def _move_row_visually(self, source_row: int, target_row: int):
        """Визуально перемещает строку в таблице."""
        try:
            # Простое и безопасное перемещение строки
            self.insertRow(target_row)

            # Перемещаем элементы
            for col in range(self.columnCount()):
                current_source_row = source_row if source_row < target_row else source_row + 1
                item = self.takeItem(current_source_row, col)
                if item:
                    self.setItem(target_row, col, item)

            # Безопасное обновление кэша - просто пересчитываем все
            old_cache = dict(self._current_links)
            new_cache = {}

            # Пересчитываем позиции для всех строк
            for row in range(self.rowCount()):
                if row == target_row and source_row in old_cache:
                    # Перемещаем данные в новую позицию
                    new_cache[row] = old_cache[source_row]
                elif source_row < target_row:
                    # Сдвигаем строки вниз
                    if row < source_row:
                        new_cache[row] = old_cache.get(row)
                    elif source_row < row <= target_row:
                        new_cache[row] = old_cache.get(row - 1)
                    elif row > target_row:
                        new_cache[row] = old_cache.get(row - 1)
                else:
                    # Сдвигаем строки вверх
                    if row < target_row:
                        new_cache[row] = old_cache.get(row)
                    elif target_row <= row < source_row:
                        new_cache[row + 1] = old_cache.get(row)
                    elif row >= source_row:
                        new_cache[row + 1] = old_cache.get(row)

            # Очищаем и обновляем кэш атомарно
            self._current_links.clear()
            self._current_links.update({k: v for k, v in new_cache.items() if v is not None})

            # Удаляем старую строку
            old_row = source_row if source_row < target_row else source_row + 1
            self.removeRow(old_row)

        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка визуального перемещения строки {source_row} -> {target_row}: {e}")
            # В случае ошибки просто пересчитываем весь кэш
            self._current_links.clear()
            for row in range(self.rowCount()):
                link_data = self.get_link_at(row)
                if link_data:
                    self._current_links[row] = link_data

    def _get_current_order(self) -> List[int]:
        """Получает текущий порядок ссылок."""
        try:
            ids_in_order = []
            for row in range(self.rowCount()):
                link_data = self.get_link_at(row)
                if link_data and 'id' in link_data:
                    ids_in_order.append(link_data['id'])
            return ids_in_order
        except Exception as e:
            logging.error(f"[DRAG] Ошибка получения текущего порядка ссылок: {e}")
            return []


# --- Переиспользуемые хелперы для таблиц ---

def get_selected_rows(table) -> List[int]:
    """Надёжно получает выбранные строки из QTableWidget/QTableView.

    Возвращает отсортированный список уникальных индексов.
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
    """Восстанавливает номера строк-источников из MIME данных с ID.

    Требует, чтобы у `table` был метод `_extract_item_id_from_item(item)`.
    Если не удаётся — возвращает `get_selected_rows(table)` как фолбэк.
    """
    try:
        from app.utils.ui.dnd.mime import MimeDataParser

        item_ids = MimeDataParser.extract_item_ids(event.mimeData(), mime_type)
        if not item_ids:
            return []

        source_rows: List[int] = []
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if not item:
                continue
            try:
                item_id = table._extract_item_id_from_item(item)  # pylint: disable=protected-access
                if item_id in item_ids:
                    source_rows.append(row)
            except Exception:
                continue
        return sorted(source_rows)
    except Exception as e:
        logging.warning(f"[DROP] Ошибка извлечения строк из MIME: {e}")
        return get_selected_rows(table)


def move_row_visually(table, source_row: int, target_row: int) -> None:
    """Централизованно перемещает одну строку таблицы визуально и обновляет кэш.

    Требования к таблице:
    - методы: rowCount(), columnCount(), takeItem(r,c), setItem(r,c,item), insertRow(r), removeRow(r)
    - поле-кэш: table._current_links: dict[int, dict] c данными строки (если есть)
    - метод: table.get_link_at(row) -> dict | None
    """
    try:
        table.insertRow(target_row)

        # Перенос ячеек
        for col in range(table.columnCount()):
            current_source_row = source_row if source_row < target_row else source_row + 1
            item = table.takeItem(current_source_row, col)
            if item:
                table.setItem(target_row, col, item)

        # Обновляем кэш, если присутствует
        old_cache = dict(getattr(table, "_current_links", {}))
        new_cache = {}

        for row in range(table.rowCount()):
            if row == target_row and source_row in old_cache:
                new_cache[row] = old_cache[source_row]
            elif source_row < target_row:
                if row < source_row:
                    new_cache[row] = old_cache.get(row)
                elif source_row < row <= target_row:
                    new_cache[row] = old_cache.get(row - 1)
                elif row > target_row:
                    new_cache[row] = old_cache.get(row - 1)
            else:
                if row < target_row:
                    new_cache[row] = old_cache.get(row)
                elif target_row <= row < source_row:
                    new_cache[row + 1] = old_cache.get(row)
                elif row >= source_row:
                    new_cache[row + 1] = old_cache.get(row)

        if hasattr(table, "_current_links"):
            table._current_links.clear()
            table._current_links.update({k: v for k, v in new_cache.items() if v is not None})

        # Удаляем прежнюю строку-«дырку»
        old_row = source_row if source_row < target_row else source_row + 1
        table.removeRow(old_row)

    except Exception as e:
        logging.error(f"[DnD] Ошибка визуального перемещения строки {source_row}->{target_row}: {e}")
        # Фолбэк: полное пересканирование кэша
        if hasattr(table, "_current_links"):
            table._current_links.clear()
            for row in range(table.rowCount()):
                try:
                    link_data = table.get_link_at(row)
                except Exception:
                    link_data = None
                if link_data:
                    table._current_links[row] = link_data


def move_rows_visually(table, source_rows: List[int], target_row: int) -> None:
    """Перемещает набор строк внутри таблицы с сохранением относительного порядка."""
    if not source_rows:
        return
    if len(source_rows) == 1:
        move_row_visually(table, source_rows[0], target_row)
        return
    for i, source_row in enumerate(reversed(source_rows)):
        adjusted_target = target_row + (len(source_rows) - 1 - i)
        if source_row < target_row:
            adjusted_target -= 1
        move_row_visually(table, source_row, adjusted_target)


def get_current_order(table) -> List[int]:
    """Возвращает ID всех элементов в текущем порядке строк таблицы."""
    try:
        ids: List[int] = []
        for row in range(table.rowCount()):
            try:
                link_data = table.get_link_at(row)
            except Exception:
                link_data = None
            if link_data and 'id' in link_data:
                ids.append(link_data['id'])
        return ids
    except Exception as e:
        logging.error(f"[DnD] Ошибка получения порядка IDs: {e}")
        return []
