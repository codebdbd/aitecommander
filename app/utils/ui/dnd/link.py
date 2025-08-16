# app/utils/dnd/link.py

"""Централизованные утилиты DnD для таблицы ссылок."""

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

            # Удаляем старую строку
            old_row = source_row if source_row < target_row else source_row + 1
            self.removeRow(old_row)

        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка визуального перемещения строки {source_row} -> {target_row}: {e}")
            # В случае ошибки – визуально ничего не восстанавливаем здесь

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
