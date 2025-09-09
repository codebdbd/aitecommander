# Основной модуль таблицы ссылок
# Содержит главный класс LinksTableView и базовую функциональность

import logging

from PyQt6.QtCore import QModelIndex, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
)

from app.config_data import app_config
from app.utils.ui.dnd.link import DragDropHandlerMixin
from app.utils.ui.dnd.mime import get_link_mime
from app.views.base_widgets import BaseDragDropTableWidget
from app.views.link.links_model import LinksTableModel

from .data_management import DataManagementMixin

# Импортируем все миксины
from .item_builders import ItemBuildersMixin
from .population_manager import PopulationManagerMixin
from .row_operations import RowOperationsMixin

# Константы для магических чисел
HOVER_COLOR = "#444444"

# Модульный логгер
logger = logging.getLogger(__name__)


class HoverHighlightDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hovered_row = -1
        self.hover_color = QColor(HOVER_COLOR)

    def paint(self, painter, option, index):
        # Оптимизация: проверяем только если строка под курсором и ячейка не выбрана
        is_hovered_row = self.hovered_row == index.row()
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)

        if is_hovered_row and not is_selected:
            painter.save()
            # Подсветка фона строки
            painter.fillRect(option.rect, self.hover_color)
            painter.restore()

        # Рисуем стандартное содержимое
        super().paint(painter, option, index)


class LinksTableView(
    BaseDragDropTableWidget,
    ItemBuildersMixin,
    DataManagementMixin,
    RowOperationsMixin,
    PopulationManagerMixin,
    DragDropHandlerMixin,
):
    """Основной класс таблицы ссылок с модульной архитектурой."""

    # Сигнал оповещения о завершении массового обновления/заполнения таблицы
    table_populated: pyqtSignal = pyqtSignal()

    def update_font_size(self, font_size: int):
        """Применяет локальный размер шрифта ко всем ячейкам таблицы."""
        # Проверяем, изменился ли размер шрифта
        if hasattr(self, "_current_font_size") and self._current_font_size == font_size:
            return

        self._current_font_size = font_size

        # Создаем новый шрифт и применяем к таблице
        from PyQt6.QtGui import QFont

        font = QFont(self.font().family(), font_size)
        self.setFont(font)

        # Обновляем отображение
        self.viewport().update()

    # Переопределяем константы базового класса (выравниваем с централизованной функцией)
    MIME_TYPE = get_link_mime()

    # Переименовываем сигнал для совместимости
    links_reordered: pyqtSignal = pyqtSignal(
        list
    )  # List[int] - ID ссылок в новом порядке

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_links = {}  # Кэш текущих данных: {row: link_data}
        self._current_mode = "normal"  # Текущий режим отображения
        self._setup_table()

        # Включаем сортировку и индикатор в заголовке
        self.setSortingEnabled(True)
        header = self.horizontalHeader()
        header.setSortIndicatorShown(True)
        # Базовый порядок по умолчанию: по названию по возрастанию
        try:
            self.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        except Exception:
            logger.debug("LinksTableView: initial sortByColumn failed", exc_info=True)
        self.delegate = HoverHighlightDelegate(self)
        self.setItemDelegate(self.delegate)
        self.setMouseTracking(True)
        # QTableView: используем сигнал entered(QModelIndex) вместо cellEntered
        try:
            self.entered.connect(self._on_index_entered)
        except Exception:
            logger.debug(
                "LinksTableView: failed to connect entered signal", exc_info=True
            )
        self.leaveEvent = self._on_leave_event

        # Сортировка по клику в заголовке: если была отключена после DnD — включим и выполним один сорт
        self.horizontalHeader().sectionClicked.connect(self._on_sort_clicked)
        # Перестраиваем кэш только по факту изменения layout модели (дешевле и корректнее)
        try:
            self.model().layoutChanged.connect(self._rebuild_cache_on_layout)
        except Exception:
            logger.debug(
                "LinksTableView: failed to connect layoutChanged", exc_info=True
            )

        # Подключаем сигнал базового класса к нашему сигналу для совместимости
        self.items_reordered.connect(self.links_reordered.emit)

    def _setup_table(self):
        headers = app_config.ui.get_links_table_headers()
        model = LinksTableModel([])
        model.set_headers(headers)
        self.setModel(model)

        # Визуальные настройки
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setShowGrid(False)
        col_widths = app_config.ui.get_col_widths()
        try:
            self.setColumnWidth(0, col_widths[0])
        except Exception:
            pass
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        _icon_sz = app_config.ui.get_icon_size()
        self.setIconSize(QSize(_icon_sz[0], _icon_sz[1]))
        self.verticalHeader().setDefaultSectionSize(app_config.ui.get_row_height())
        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        try:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        except Exception:
            logger.debug(
                "LinksTableView: failed to set resize mode for column 0", exc_info=True
            )
        try:
            self.setColumnWidth(1, col_widths[1])
            self.setColumnWidth(2, col_widths[2])
        except Exception:
            logger.debug(
                "LinksTableView: failed to set column widths for 1/2", exc_info=True
            )
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

    def _on_index_entered(self, index: QModelIndex):
        row = index.row()
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
        """Включаем сортировку по клику, если она была отключена из-за ручного порядка."""
        header = self.horizontalHeader()
        if not self.isSortingEnabled():
            self.setSortingEnabled(True)
            try:
                header.setSortIndicatorShown(True)
            except Exception:
                logger.debug(
                    "LinksTableView: failed to setSortIndicatorShown(True)",
                    exc_info=True,
                )
            # Выполняем один сорт по колонке (Ascending); дальше Qt сам будет
            try:
                self.sortByColumn(logical_index, Qt.SortOrder.AscendingOrder)
            except Exception:
                logger.debug(
                    "LinksTableView: sortByColumn on header click failed", exc_info=True
                )

    def _rebuild_cache_on_layout(self):
        """Перестраиваем кэш после изменения layout модели (сортировка/перемещения)."""
        try:
            self.rebuild_cache_from_items()
        except Exception as e:
            logger.debug(
                "[SORT] Ошибка перестроения кэша по layoutChanged: %s", e, exc_info=True
            )
