# app/utils/dnd/tree.py

"""Централизованный обработчик drag & drop для StructureTreeWidget."""

import logging
from typing import List

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
        source_item = self.tree_widget.currentItem()
        mime = event.mimeData()

        # Проверяем, является ли это внутренним перемещением
        is_internal_move = event.source() == self.tree_widget

        if is_internal_move:
            if source_item and self._is_valid_drop(source_item, event):
                event.accept()
            else:
                event.ignore()
        else:
            self._handle_external_drag_move(event, mime)

    def handle_drag_leave_event(self, event) -> None:
        """Обработка выхода из drag зоны."""
        event.accept()

    def handle_drop_event(self, event) -> None:
        """Основной обработчик drop событий."""
        mime = event.mimeData()

        # Обработка различных типов drop операций
        if mime.hasFormat(app_config.get_category_mime_type()):
            self._handle_category_drop_event(mime, event)
        elif mime.hasFormat(app_config.get_link_mime_type()):
            self._handle_link_drop_event(mime, event)
        elif event.source() == self.tree_widget:
            self._handle_internal_drop_event(event)
        else:
            event.ignore()

    def _handle_external_drag_move(self, event, mime) -> None:
        """Обработка внешнего перетаскивания в dragMoveEvent."""
        target_item = self.tree_widget.itemAt(event.position().toPoint())
        if not target_item:
            event.ignore()
            return

        ttuple = get_tree_tuple(target_item, 0)
        if not ttuple:
            event.ignore()
            return
        target_type, _ = ttuple
        drop_pos = self.tree_widget.dropIndicatorPosition()

        valid_drop = False

        if mime.hasFormat(app_config.get_link_mime_type()):
            # Ссылки можно бросать только на категории
            if target_type == "category":
                valid_drop = True
                event.accept()
            else:
                event.ignore()
        elif mime.hasFormat(app_config.get_category_mime_type()):
            # Более строгая проверка для категорий
            if target_type == "section":
                # Категорию можно бросить только НА раздел, но не рядом с ним
                if drop_pos == QAbstractItemView.DropIndicatorPosition.OnItem:
                    valid_drop = True
                    event.accept()
                else:
                    event.ignore()
            else:
                event.ignore()
        else:
            event.ignore()

        # Переключаем фокус на целевую категорию при валидном drop ссылок
        if (
            valid_drop
            and mime.hasFormat(app_config.get_link_mime_type())
            and target_type == "category"
        ):
            self._focus_target_category(target_item)

    def _focus_target_category(self, target_item):
        """Переключает фокус на целевую категорию."""
        if target_item:
            self.tree_widget.setCurrentItem(target_item)

            # Получаем ID категории и переключаем фокус через бизнес-логику
            ttuple = get_tree_tuple(target_item, 0)
            if not ttuple:
                return
            target_type, target_id = ttuple
            if target_type == "category":
                # Слабая связанность: сообщаем наружу через сигнал виджета
                try:
                    self.tree_widget.emit_drag_feedback(
                        {
                            "type": "focus_category_request",
                            "category_id": target_id,
                            "title": target_item.text(0),
                        }
                    )
                except Exception as e:
                    logger.warning(
                        f"Не удалось отправить dragFeedback для категории {target_id}: {e}"
                    )

    def _handle_category_drop_event(self, mime, event) -> None:
        """Обработка drop категории из виджета плиток."""
        target_item = self.tree_widget.itemAt(event.position().toPoint())
        if target_item:
            ttuple = get_tree_tuple(target_item, 0)
            if ttuple and ttuple[0] == "section":
                self._handle_category_drop(mime, target_item)
                event.accept()
                return
        else:
            self.tree_widget.emit_invalid_drop(
                "Категорию можно бросать только на раздел"
            )
            event.ignore()

    def _handle_link_drop_event(self, mime, event) -> None:
        """Обработка drop ссылки из таблицы ссылок."""
        target_item = self.tree_widget.itemAt(event.position().toPoint())
        if target_item:
            ttuple = get_tree_tuple(target_item, 0)
            if ttuple and ttuple[0] == "category":
                self._handle_link_drop(mime, target_item)
                event.accept()
                return
        else:
            self.tree_widget.emit_invalid_drop(
                "Ссылку можно бросать только на категорию"
            )
            event.ignore()

    def _handle_internal_drop_event(self, event) -> None:
        """Обработка внутреннего drop в дереве."""
        source_item = self.tree_widget.currentItem()
        if not source_item:
            self.tree_widget.emit_invalid_drop(
                "Нет выбранного элемента для перемещения"
            )
            event.ignore()
            return

        if self._is_valid_drop(source_item, event):
            super(type(self.tree_widget), self.tree_widget).dropEvent(event)
            # Используем move_operations_handler для обработки перемещения
            self.tree_widget.move_operations_handler.handle_internal_move(source_item)
            # Сообщаем наружу о перемещении
            try:
                stuple = get_tree_tuple(source_item, 0)
                source_type = stuple[0] if stuple else None
                self.tree_widget.emit_items_moved(
                    {
                        "type": "internal_move",
                        "source_type": source_type,
                        "source_text": source_item.text(0),
                    }
                )
            except Exception:
                pass
            event.accept()
        else:
            self.tree_widget.emit_invalid_drop("Недопустимая операция перемещения")
            event.ignore()

    def _handle_category_drop(self, mime, target_item) -> None:
        """Обработка перетаскивания категории на раздел."""
        ids = MimeDataParser.extract_item_ids(mime, app_config.get_category_mime_type())
        if not ids:
            logger.warning("Не удалось извлечь ID категории из MIME данных")
            return
        category_id = ids[0]

        ttuple = get_tree_tuple(target_item, 0)
        if not ttuple:
            return
        target_type, target_id = ttuple
        if target_type != "section" or not isinstance(target_id, int):
            return

        # Используем move_operations_handler для выполнения команды
        self.tree_widget.move_operations_handler.execute_move_category_command(
            category_id, target_id
        )
        # Слабая связанность: уведомляем о перемещении
        self.tree_widget.emit_items_moved(
            {
                "type": "category_to_section",
                "category_id": category_id,
                "section_id": target_id,
            }
        )

    def _handle_link_drop(self, mime, target_item) -> None:
        """Обработка перетаскивания ссылки на категорию."""
        if not target_item:
            return
        ttuple = get_tree_tuple(target_item, 0)
        if not (ttuple and ttuple[0] == "category"):
            return

        link_ids = self._extract_link_ids_from_mime(mime)
        if not link_ids:
            return

        new_category_id = ttuple[1]
        if not isinstance(new_category_id, int):
            return
        # Используем move_operations_handler для выполнения команды
        self.tree_widget.move_operations_handler.execute_move_links_command(
            link_ids, new_category_id
        )
        # Слабая связанность: уведомляем о перемещении
        self.tree_widget.emit_items_moved(
            {
                "type": "links_to_category",
                "link_ids": link_ids,
                "category_id": new_category_id,
            }
        )

    def _extract_link_ids_from_mime(self, mime) -> List[int]:
        """Извлекает ID ссылок из MIME данных."""
        ids = MimeDataParser.extract_item_ids(mime, app_config.get_link_mime_type())
        if not ids:
            logger.warning("Не удалось извлечь ID ссылок из MIME данных")
        return ids

    def _is_valid_drop(self, source_item, event: QDropEvent) -> bool:
        """Проверяет валидность операции перетаскивания."""
        stuple = get_tree_tuple(source_item, 0)
        if not stuple:
            return False
        source_type, _ = stuple
        target_item = self.tree_widget.itemAt(event.position().toPoint())
        drop_pos = self.tree_widget.dropIndicatorPosition()

        if source_type == "section":
            return self._is_valid_section_drop(drop_pos, target_item)
        elif source_type == "category":
            return self._is_valid_category_drop(source_item, target_item, drop_pos)

        return False

    def _is_valid_section_drop(self, drop_pos, target_item) -> bool:
        """Проверка валидности drop для раздела."""
        # Раздел можно бросить только на верхний уровень
        if drop_pos == QAbstractItemView.DropIndicatorPosition.OnItem:
            return False
        # Если бросаем между элементами, родитель должен быть None
        if target_item and target_item.parent() is not None:
            return False
        return True

    def _is_valid_category_drop(self, source_item, target_item, drop_pos) -> bool:
        """Проверка валидности drop для категории."""
        if not target_item:
            # Категорию нельзя бросать в корень дерева
            return False

        ttuple = get_tree_tuple(target_item, 0)
        if not ttuple:
            return False
        target_type, _ = ttuple

        if drop_pos == QAbstractItemView.DropIndicatorPosition.OnItem:
            # Можно бросить только на раздел
            return target_type == "section"
        else:  # AboveItem или BelowItem
            # Проверяем, что источник не является разделом
            stuple = get_tree_tuple(source_item, 0)
            if not stuple:
                return False
            source_type, _ = stuple
            if source_type == "section":
                # категорию нельзя размещать ни над, ни под ним
                return False

            # При drop между элементами
            if target_type == "section":
                # Нельзя ставить категорию между разделами (на корневой уровень)
                return False
            elif target_type == "category":
                # Целевой элемент должен быть категорией и в том же разделе
                return source_item.parent() == target_item.parent()

        return False
