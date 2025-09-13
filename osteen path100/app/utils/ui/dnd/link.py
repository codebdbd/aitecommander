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

from app.utils.ui.qt.roles import get_selected_rows as get_selected_rows_util

# Модульный логгер
logger = logging.getLogger(__name__)


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
            total = (
                model.rowCount()
                if model is not None
                else getattr(self, "rowCount", lambda: 0)()
            )

            for row in rows:
                # Проверка границ
                if not (0 <= row < total):
                    logger.warning("[DRAG] Некорректный индекс строки: %s", row)
                    continue

                link_data = self.get_link_at(row)
                if link_data and "id" in link_data:
                    ids.append(link_data["id"])
                else:
                    logger.warning("[DRAG] Отсутствует ID в строке %s", row)

            return ids
        except Exception as e:
            logger.error("[DRAG] Ошибка извлечения ID из элементов: %s", e)
            return []

    def _rebuild_current_links(self):
        """Очищает и перестраивает кэш _current_links из модели.

        Вызывается после операций, изменяющих порядок строк (сортировка, DnD).
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
            logger.error("[DRAG] Ошибка перестроения кэша ссылок: %s", e)
            self._current_links.clear()  # В случае ошибки кэш должен быть пустым

    def _move_row_visually(self, source_row: int, target_row: int):
        """Перемещает строку через модель и перестраивает кэш.

        Использует `finally`, чтобы гарантировать перестроение кэша.
        """
        try:
            model = getattr(self, "model", lambda: None)()
            if model is None:
                return
            # Вызываем `move_rows` из модели, который должен вызвать begin/endMoveRows
            model.move_rows([source_row], target_row)
        except Exception as e:
            logger.error(
                "[LinksTableView] Ошибка визуального перемещения строки %s -> %s: %s",
                source_row,
                target_row,
                e,
            )
        finally:
            # Кэш перестраивается в любом случае, чтобы отразить фактическое состояние модели
            self._rebuild_current_links()

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
            logger.error("[DRAG] Ошибка получения текущего порядка ссылок: %s", e)
            return []


# --- Переиспользуемые хелперы для таблиц ---


def get_selected_rows(view) -> List[int]:
    """Получает отсортированный список уникальных выбранных строк через общую утилиту."""
    return get_selected_rows_util(view)


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
        logger.warning("[DROP] Ошибка извлечения строк из MIME: %s", e)
        return get_selected_rows(table)


def move_row_visually(table, source_row: int, target_row: int) -> None:
    """Централизованно перемещает одну строку и инициирует обновление кэша.

    Если у `table` есть метод `_rebuild_current_links`, он будет вызван.
    Это позволяет избежать дублирования логики перестроения кэша.
    """
    try:
        model = getattr(table, "model", lambda: None)()
        if model is None:
            return
        model.move_rows([source_row], target_row)
    except Exception as e:
        logger.error(
            "[DnD] Ошибка визуального перемещения строки %s->%s: %s",
            source_row,
            target_row,
            e,
        )
    finally:
        # Если у таблицы есть метод для перестройки кэша, используем его.
        # Это основной сценарий при использовании DragDropHandlerMixin.
        if hasattr(table, "_rebuild_current_links") and callable(
            getattr(table, "_rebuild_current_links")
        ):
            table._rebuild_current_links()
        else:
            logger.warning(
                "[DnD] Объект %s не имеет метода _rebuild_current_links. Кэш может быть неактуален.",
                type(table).__name__,
            )


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
        logger.error("[DnD] Ошибка получения порядка IDs: %s", e)
        return []
