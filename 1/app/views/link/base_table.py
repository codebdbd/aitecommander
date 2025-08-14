# Основной модуль таблицы ссылок
# Содержит главный класс LinksTableView и базовую функциональность

import logging
from typing import Dict, List, Optional, Set

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QTableWidgetItem,
)

from app.config_data import app_config
from app.utils.ui.dnd.link import DragDropHandlerMixin
from app.views.base_widgets import BaseDragDropTableWidget

from .data_management import DataManagementMixin

# Импортируем все миксины
from .item_builders import ItemBuildersMixin
from .population_manager import PopulationManagerMixin
from .row_operations import RowOperationsMixin

# Константы для магических чисел
HOVER_COLOR = "#444444"


class HoverHighlightDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hovered_row = -1
        self.hover_color = QColor(HOVER_COLOR)

    def paint(self, painter, option, index):
        # Оптимизация: проверяем только если строка поменялась
        if self.hovered_row == index.row() and not (option.state & QStyle.StateFlag.State_Selected):
            painter.save()
            painter.fillRect(option.rect, self.hover_color)
            painter.restore()
        super().paint(painter, option, index)


class LinksTableView(BaseDragDropTableWidget, 
                    ItemBuildersMixin,
                    DataManagementMixin,
                    RowOperationsMixin,
                    PopulationManagerMixin,
                    DragDropHandlerMixin):
    """Основной класс таблицы ссылок с модульной архитектурой."""
    
    def update_font_size(self, font_size: int):
        """Применяет локальный размер шрифта ко всем ячейкам таблицы."""
        # Проверяем, изменился ли размер шрифта
        if hasattr(self, '_current_font_size') and self._current_font_size == font_size:
            return
        
        self._current_font_size = font_size
        
        # Создаем новый шрифт и применяем к таблице
        from PyQt6.QtGui import QFont
        font = QFont(self.font().family(), font_size)
        self.setFont(font)
        
        # Обновляем отображение
        self.viewport().update()

    # Переопределяем константы базового класса
    MIME_TYPE = app_config.get_link_mime_type()
    
    # Переименовываем сигнал для совместимости
    links_reordered: pyqtSignal = pyqtSignal(list)  # List[int] - ID ссылок в новом порядке

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_links = {}  # Кэш текущих данных: {row: link_data}
        self._current_mode = "normal"  # Текущий режим отображения
        self._setup_table()

        self.setSortingEnabled(True)
        self.horizontalHeader().setSortIndicatorShown(False)
        self.delegate = HoverHighlightDelegate(self)
        self.setItemDelegate(self.delegate)
        self.setMouseTracking(True)
        self.cellEntered.connect(self._on_cell_entered)
        self.leaveEvent = self._on_leave_event

        # Простое решение: очищаем кэш после сортировки
        self.horizontalHeader().sectionClicked.connect(self._on_sort_clicked)

        # Подключаем сигнал базового класса к нашему сигналу для совместимости
        self.items_reordered.connect(self.links_reordered.emit)

    def _setup_table(self):
        headers = app_config.get_links_table_headers()
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setShowGrid(False)
        col_widths = app_config.get_col_widths()
        self.setColumnWidth(0, col_widths[0])
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setIconSize(app_config.get_icon_size())
        self.verticalHeader().setDefaultSectionSize(app_config.get_row_height())
        self.horizontalHeader().setStretchLastSection(True)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(1, col_widths[1])
        self.setColumnWidth(2, col_widths[2])
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

    def _on_cell_entered(self, row, column):
        if self.delegate.hovered_row != row:
            self.delegate.hovered_row = row

    def _on_leave_event(self, event):
        if self.delegate.hovered_row != -1:
            self.delegate.hovered_row = -1
        event.accept()
    
    # Переопределяем абстрактные методы из BaseDragDropTableWidget
    def _extract_item_ids_from_items(self, items):
        """Извлекает ID ссылок из выбранных элементов."""
        # Используем реализацию из DragDropHandlerMixin
        return DragDropHandlerMixin._extract_item_ids_from_items(self, items)
    
    def _move_row_visually(self, source_row: int, target_row: int):
        """Визуально перемещает строку в таблице."""
        # Используем реализацию из DragDropHandlerMixin
        return DragDropHandlerMixin._move_row_visually(self, source_row, target_row)
    
    def _get_current_order(self):
        """Получает текущий порядок ссылок."""
        # Используем реализацию из DragDropHandlerMixin
        return DragDropHandlerMixin._get_current_order(self)
    
    def _on_sort_clicked(self, logical_index):
        """Обработчик клика по заголовку - очищает кэш после сортировки."""
        import logging

        from PyQt6.QtCore import QTimer
        
        logging.debug(f"[SORT] Клик по колонке {logical_index}, очищаем кэш")
        
        # Отложенное очищение кэша после завершения сортировки
        QTimer.singleShot(0, self._clear_cache_after_sort)
    
    def _clear_cache_after_sort(self):
        """Очищает кэш после сортировки."""
        import logging
        
        old_cache_size = len(self._current_links)
        self._current_links.clear()
        
        logging.debug(f"[SORT] Кэш очищен: {old_cache_size} записей удалено")
        logging.debug(f"[SORT] Теперь get_link_at() будет использовать fallback (item.data)")
