# app/utils/dnd/tree.py

"""Централизованный обработчик drag & drop для дерева структуры.

Поддерживается `StructureTreeView` (QTreeView) с моделью и индексами.
"""

import logging
from typing import List

from PyQt6.QtCore import QModelIndex
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QAbstractItemView

from app.config_data import app_config
from app.utils.ui.dnd.mime import MimeDataParser
from app.utils.ui.qt.roles import get_tree_tuple

from .base import TreeHandlerBase

logger = logging.getLogger(__name__)


class DragDropHandler(TreeHandlerBase):
    """Обработчик drag & drop операций в дереве структуры."""

    def accepts_mime_type(self, mime) -> bool:
        """Проверяет, принимает ли виджет данный MIME тип."""
        return mime.hasFormat(app_config.get_link_mime_type()) or mime.hasFormat(
            app_config.get_category_mime_type()
        )

    def handle_drag_enter_event(self, event) -> None:
        """Обработка входа drag операции."""
        mime = event.mimeData()
        if self.accepts_mime_type(mime):
            event.acceptProposedAction()
        else:
            # Передаем обработку родительскому классу для внутренних операций
            super(type(self.tree_widget), self.tree_widget).dragEnterEvent(event)

    def handle_drag_move_event(self, event) -> None:
        """Визуальная обратная связь во время перетаскивания."""
        mime = event.mimeData()
        is_internal_move = event.source() == self.tree_widget

        # Путь для QTreeView (модель/индексы)
        src_index = self.tree_widget.currentIndex()
        if is_internal_move:
            if src_index and src_index.isValid() and self._is_valid_drop_index(src_index, event):
                event.accept()
            else:
                event.ignore()
        else:
            self._handle_external_drag_move_index(event, mime)
        return

    def handle_drag_leave_event(self, event) -> None:
        """Обработка выхода из drag зоны."""
        event.accept()

    def handle_drop_event(self, event) -> None:
        """Основной обработчик drop событий."""
        mime = event.mimeData()

        target_index: QModelIndex = self.tree_widget.indexAt(event.position().toPoint())
        if mime.hasFormat(app_config.get_category_mime_type()):
            self._handle_category_drop_index(mime, target_index)
            event.accept()
            return
        if mime.hasFormat(app_config.get_link_mime_type()):
            self._handle_link_drop_index(mime, target_index)
            event.accept()
            return
        if event.source() == self.tree_widget:
            self._handle_internal_drop_event_index(event)
            return
        event.ignore()

    # --- Индексная версия внешнего dragMove ---
    def _handle_external_drag_move_index(self, event, mime) -> None:
        target_index: QModelIndex = self.tree_widget.indexAt(event.position().toPoint())
        if not target_index or not target_index.isValid():
            event.ignore()
            return
        ttuple = get_tree_tuple(target_index, 0)
        if not ttuple:
            event.ignore()
            return
        target_type, _ = ttuple
        drop_pos = self.tree_widget.dropIndicatorPosition()
        valid_drop = False
        if mime.hasFormat(app_config.get_link_mime_type()):
            if target_type == "category":
                valid_drop = True
                event.accept()
            else:
                event.ignore()
        elif mime.hasFormat(app_config.get_category_mime_type()):
            if target_type == "section":
                if drop_pos == QAbstractItemView.DropIndicatorPosition.OnItem:
                    valid_drop = True
                    event.accept()
                else:
                    event.ignore()
            else:
                event.ignore()
        else:
            event.ignore()
        if valid_drop and mime.hasFormat(app_config.get_link_mime_type()) and target_type == "category":
            self._focus_target_category_index(target_index)

    def _focus_target_category_index(self, target_index: QModelIndex):
        """Фокусировка на целевой категории (QTreeView)."""
        if target_index and target_index.isValid():
            self.tree_widget.setCurrentIndex(target_index)
            ttuple = get_tree_tuple(target_index, 0)
            if not ttuple:
                return
            target_type, target_id = ttuple
            if target_type == "category":
                try:
                    self.tree_widget.dragFeedback.emit(
                        {
                            "type": "focus_category_request",
                            "category_id": target_id,
                            "title": target_index.data(),
                        }
                    )
                except Exception as e:
                    logger.warning(
                        f"Не удалось отправить dragFeedback для категории {target_id}: {e}"
                    )

    def _handle_internal_drop_event_index(self, event) -> None:
        """Внутренний drop для QTreeView: массовый перенос категорий между/внутри разделов."""
        selection_model = getattr(self.tree_widget, "selectionModel", lambda: None)()
        selected_indexes: list[QModelIndex] = []
        if selection_model and hasattr(selection_model, "selectedRows"):
            try:
                selected_indexes = selection_model.selectedRows(0) or []
            except Exception:
                selected_indexes = []
        # Фолбэк на текущий индекс, если множественный выбор пуст
        if not selected_indexes:
            cur = self.tree_widget.currentIndex()
            if cur and cur.isValid():
                selected_indexes = [cur]

        # Фильтруем только категории
        category_indices: list[QModelIndex] = []
        for idx in selected_indexes:
            t = get_tree_tuple(idx, 0)
            if t and t[0] == "category":
                category_indices.append(idx)
        if not category_indices:
            try:
                self.tree_widget.invalidDrop.emit("Перемещать можно только категории")
            except Exception:
                pass
            event.ignore()
            return

        target_index: QModelIndex = self.tree_widget.indexAt(event.position().toPoint())
        drop_pos = self.tree_widget.dropIndicatorPosition()
        if not target_index or not target_index.isValid():
            event.ignore()
            return
        ttuple = get_tree_tuple(target_index, 0)
        if not ttuple:
            event.ignore()
            return
        target_type, _ = ttuple

        model = self.tree_widget.model()
        # Определяем целевой раздел и базовую позицию вставки
        if target_type == "section" and drop_pos == QAbstractItemView.DropIndicatorPosition.OnItem:
            new_section_index = target_index
            new_section_tuple = get_tree_tuple(new_section_index, 0)
            new_section_id = new_section_tuple[1] if new_section_tuple else None
            base_row = model.rowCount(new_section_index)
        elif target_type == "category":
            parent_index = target_index.parent()
            parent_tuple = get_tree_tuple(parent_index, 0)
            if not (parent_tuple and parent_tuple[0] == "section"):
                event.ignore()
                return
            new_section_id = parent_tuple[1]
            tgt_row = target_index.row()
            if drop_pos == QAbstractItemView.DropIndicatorPosition.AboveItem:
                base_row = tgt_row
            elif drop_pos == QAbstractItemView.DropIndicatorPosition.BelowItem:
                base_row = tgt_row + 1
            elif drop_pos == QAbstractItemView.DropIndicatorPosition.OnItem:
                base_row = model.rowCount(parent_index)
            else:
                event.ignore()
                return
        else:
            event.ignore()
            return

        # Нормализуем base_row в допустимый диапазон [0..rowCount]
        try:
            parent_for_count = new_section_index if (target_type == "section") else parent_index
            total_rows = model.rowCount(parent_for_count) if parent_for_count and parent_for_count.isValid() else 0
            if not isinstance(base_row, int):
                base_row = 0
            if base_row < 0:
                base_row = 0
            if base_row > total_rows:
                base_row = total_rows
        except Exception:
            # В случае любой ошибки безопасно отклоняем операцию, чтобы не повредить модель
            event.ignore()
            return

        if not isinstance(new_section_id, int):
            event.ignore()
            return

        # Стабильный порядок: по возрастанию row в текущем представлении
        category_indices.sort(key=lambda i: i.row())

        # Если выбрано несколько категорий — используем атомарную команду с единым undo
        if len(category_indices) > 1 and hasattr(self.tree_widget, "move_operations_handler"):
            ids: list[int] = []
            for idx in category_indices:
                st = get_tree_tuple(idx, 0)
                if st and isinstance(st[1], int):
                    ids.append(int(st[1]))
            if ids:
                try:
                    self.tree_widget.move_operations_handler.execute_move_categories_command(
                        ids, int(new_section_id), int(base_row)
                    )
                    event.accept()
                    return
                except Exception:
                    # Fallback ниже — поштучные перемещения
                    pass

        # Обычный путь: одиночный перенос (или fallback)
        moved_any = False
        insert_offset = 0
        for idx in category_indices:
            st = get_tree_tuple(idx, 0)
            if not (st and isinstance(st[1], int)):
                continue
            category_id = int(st[1])
            target_row = int(base_row + insert_offset)
            try:
                ok = hasattr(model, "move_category") and model.move_category(category_id, int(new_section_id), target_row)
            except Exception:
                ok = False
            if ok:
                moved_any = True
                insert_offset += 1
                try:
                    self.tree_widget.itemsMoved.emit(
                        {
                            "type": "internal_move",
                            "source_type": "category",
                            "category_id": category_id,
                            "section_id": int(new_section_id),
                            "new_row": target_row,
                        }
                    )
                except Exception:
                    pass

        if moved_any:
            event.accept()
        else:
            try:
                self.tree_widget.invalidDrop.emit("Недопустимая операция перемещения")
            except Exception:
                pass
            event.ignore()

    def _handle_category_drop_index(self, mime, target_index: QModelIndex) -> None:
        """Перенос одной или нескольких категорий (из плиток) на раздел для QTreeView."""
        ids = MimeDataParser.extract_item_ids(mime, app_config.get_category_mime_type())
        if not ids:
            logger.warning("Не удалось извлечь ID категории из MIME данных")
            return
        ttuple = get_tree_tuple(target_index, 0)
        if not (ttuple and ttuple[0] == "section" and isinstance(ttuple[1], int)):
            return
        section_id = int(ttuple[1])
        moved_count = 0
        for category_id in ids:
            if not isinstance(category_id, int):
                continue
            # Выполняем перенос через обработчик операций (бизнес-логика)
            try:
                self.tree_widget.move_operations_handler.execute_move_category_command(category_id, section_id)
                moved_count += 1
            except Exception:
                continue
            try:
                self.tree_widget.itemsMoved.emit(
                    {
                        "type": "category_to_section",
                        "category_id": category_id,
                        "section_id": section_id,
                    }
                )
            except Exception:
                pass
        if moved_count > 1:
            logger.info(f"Перенесено категорий: {moved_count} в раздел {section_id}")

    def _handle_link_drop_index(self, mime, target_index: QModelIndex) -> None:
        """Перенос ссылок на категорию (QTreeView)."""
        ttuple = get_tree_tuple(target_index, 0)
        if not (ttuple and ttuple[0] == "category"):
            return
        link_ids = self._extract_link_ids_from_mime(mime)
        if not link_ids:
            return
        new_category_id = ttuple[1]
        if not isinstance(new_category_id, int):
            return
        try:
            self.tree_widget.move_operations_handler.execute_move_links_command(link_ids, new_category_id)
        except Exception:
            pass
        try:
            self.tree_widget.itemsMoved.emit(
                {
                    "type": "links_to_category",
                    "link_ids": link_ids,
                    "category_id": new_category_id,
                }
            )
        except Exception:
            pass

    def _extract_link_ids_from_mime(self, mime) -> List[int]:
        """Извлекает ID ссылок из MIME данных."""
        ids = MimeDataParser.extract_item_ids(mime, app_config.get_link_mime_type())
        if not ids:
            logger.warning("Не удалось извлечь ID ссылок из MIME данных")
        return ids

    # Индексная версия проверки валидности DnD (QTreeView)
    def _is_valid_drop_index(self, source_index: QModelIndex, event: QDropEvent) -> bool:
        stuple = get_tree_tuple(source_index, 0)
        if not stuple:
            return False
        source_type, _ = stuple
        target_index = self.tree_widget.indexAt(event.position().toPoint())
        drop_pos = self.tree_widget.dropIndicatorPosition()
        if source_type == "section":
            # Разделы не поддерживаем к перемещению пока
            return False
        elif source_type == "category":
            if not target_index or not target_index.isValid():
                return False
            ttuple = get_tree_tuple(target_index, 0)
            if not ttuple:
                return False
            target_type, _ = ttuple
            if drop_pos == QAbstractItemView.DropIndicatorPosition.OnItem:
                return target_type in ("section", "category")
            else:
                # Между элементами разрешаем только между категориями одного раздела
                if target_type != "category":
                    return False
                # Один и тот же родитель
                return source_index.parent() == target_index.parent()
        return False
