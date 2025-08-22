# Основной модуль таблицы ссылок (QTableView + QAbstractTableModel)

import logging
import time

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QTableView,
)

from app.config_data import app_config
from app.utils.ui.dnd.mime import get_link_mime

from .data_management import DataManagementMixin

# Импортируем все миксины
from .population_manager import PopulationManagerMixin
from .row_operations import RowOperationsMixin
from .links_table_model import LinksTableModel

# Константы для магических чисел
HOVER_COLOR = "#444444"


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

class LinksTableView(QTableView,
                    DataManagementMixin,
                    RowOperationsMixin,
                    PopulationManagerMixin):
    """Основной класс таблицы ссылок на базе QTableView + LinksTableModel."""
    
    # Сигнал оповещения о завершении массового обновления/заполнения таблицы
    table_populated: pyqtSignal = pyqtSignal()
    # Сигналы совместимости с QTableWidget API
    # cellDoubleClicked(row:int, column:int)
    cellDoubleClicked: pyqtSignal = pyqtSignal(int, int)
    # cellClicked(row:int, column:int)
    cellClicked: pyqtSignal = pyqtSignal(int, int)

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

    # MIME для будущей поддержки DnD (этап 2)
    MIME_TYPE = get_link_mime()
    # Сигнал совместимости (этап 2 вернем DnD и эмит)
    links_reordered: pyqtSignal = pyqtSignal(list)  # List[int] - ID ссылок в новом порядке

    def __init__(self, parent=None):
        super().__init__(parent)
        t0 = time.perf_counter()
        self._current_links = {}
        self._current_mode = "normal"

        # --- ФИНАЛЬНАЯ ОПТИМИЗАЦИЯ: Отложенная инициализация ---
        t_model0 = time.perf_counter()
        self._model = LinksTableModel([], mode=self._current_mode, parent=self)
        t_model1 = time.perf_counter()
        
        # Откладываем setModel() до первого показа таблицы
        self._model_ready = False
        self._lazy_model = self._model  # Сохраняем модель для отложенной установки
        
        # Вместо setModel() сразу, используем временную заглушку
        from PyQt6.QtGui import QStandardItemModel
        temp_model = QStandardItemModel(0, 4, self)
        temp_model.setHorizontalHeaderLabels(["★", "Название", "Открывалась", "Заметки"])
        super().setModel(temp_model)
        
        t_set_model = time.perf_counter()
        self._setup_table()
        t_setup = time.perf_counter()

        self.setSortingEnabled(True)
        self.horizontalHeader().setSortIndicatorShown(False)
        
        self.delegate = HoverHighlightDelegate(self)
        self.setItemDelegate(self.delegate)
        
        self.setMouseTracking(True)
        # Для QTableView используем сигнал entered
        self.entered.connect(lambda index: self._on_cell_entered(index.row(), index.column()))
        self.leaveEvent = self._on_leave_event

        # Совместимость: пробрасываем сигналы кликов ячеек
        self.doubleClicked.connect(lambda index: self.cellDoubleClicked.emit(index.row(), index.column()))
        self.clicked.connect(lambda index: self.cellClicked.emit(index.row(), index.column()))

        # Планировщик перестройки кэша (единый таймер, чтобы не плодить singleShot)
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.timeout.connect(self._clear_cache_after_sort)
        header = self.horizontalHeader()
        header.sectionClicked.connect(self._on_sort_clicked)
        
        # Сигнал для отложенной инициализации
        self._initialized = False
        try:
            # sortIndicatorChanged(int, Qt.SortOrder) — реагируем на программную смену сортировки
            header.sortIndicatorChanged.connect(self._on_sort_indicator_changed)
        except Exception:
            pass

        t_end = time.perf_counter()
        try:
            logging.info(
                f"LinksTableView init timings: model={ (t_model1 - t_model0)*1000:.1f} ms, "
                f"setModel={ (t_set_model - t_model1)*1000:.1f} ms, setup={ (t_setup - t_set_model)*1000:.1f} ms, "
                f"rest={ (t_end - t_setup)*1000:.1f} ms, total={ (t_end - t0)*1000:.1f} ms"
            )
        except Exception:
            pass

    def setModel(self, model):
        """Переопределяем setModel для поддержки сортировки и кэширования."""
        if hasattr(self, 'horizontalHeader'):
            # Сохраняем текущее состояние сортировки
            old_sort_column = -1
            old_sort_order = Qt.SortOrder.AscendingOrder
            header = self.horizontalHeader()
            if header:
                old_sort_column = header.sortIndicatorSection()
                old_sort_order = header.sortIndicatorOrder()

            # Устанавливаем новую модель
            super().setModel(model)
            
            # Восстанавливаем сортировку
            if old_sort_column >= 0 and old_sort_column < model.columnCount():
                header.setSortIndicator(old_sort_column, old_sort_order)
                
            # Очищаем кэш после установки новой модели
            self._clear_cache_after_sort()
        else:
            super().setModel(model)

    def showEvent(self, event):
        """Отложенная инициализация при первом показе таблицы."""
        super().showEvent(event)
        if not self._initialized and hasattr(self, '_lazy_model'):
            # Устанавливаем реальную модель только когда таблица видима
            QTimer.singleShot(0, self._initialize_model)
            self._initialized = True

    def _initialize_model(self):
        """Устанавливает реальную модель после отображения таблицы."""
        if hasattr(self, '_lazy_model'):
            self.setModel(self._lazy_model)
            del self._lazy_model  # Удаляем ссылку на временную модель

    def _setup_table(self):
        # Настройки внешнего вида и поведения
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setShowGrid(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setIconSize(app_config.get_icon_size())
        self.verticalHeader().setDefaultSectionSize(app_config.get_row_height())

        header = self.horizontalHeader()
        # Избегаем дублирования механизма растяжения: управляем адресно через setSectionResizeMode
        header.setStretchLastSection(False)
        try:
            col_widths = app_config.get_col_widths()
            # Безопасно применяем, если ширины заданы
            if len(col_widths) >= 3:
                columns = self.model().columnCount() if self.model() is not None else 0
                if columns >= 1:
                    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
                    self.setColumnWidth(0, col_widths[0])
                if columns >= 2:
                    self.setColumnWidth(1, col_widths[1])
                if columns >= 3:
                    self.setColumnWidth(2, col_widths[2])
                    header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
                if columns >= 4:
                    header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        except Exception as e:
            logging.debug(f"[Headers] Не удалось применить ширины колонок: {e}")

    def _on_cell_entered(self, row, column):
        if self.delegate.hovered_row != row:
            self.delegate.hovered_row = row
            # Явная инвалидация для снятия подсветки со старой строки и применения к новой
            try:
                self.viewport().update()
            except Exception:
                pass

    def _on_leave_event(self, event):
        if self.delegate.hovered_row != -1:
            self.delegate.hovered_row = -1
            try:
                self.viewport().update()
            except Exception:
                pass
        event.accept()
    
    # DnD будет реализован на этапе 2 (через QTableView API)
    
    def _on_sort_clicked(self, logical_index):
        """Обработчик клика по заголовку - очищает кэш после сортировки."""
        logging.debug(f"[SORT] Клик по колонке {logical_index}, очищаем кэш")
        # Единоразово планируем перестройку кэша
        self._schedule_cache_rebuild()

    def _on_sort_indicator_changed(self, logical_index, sort_order):
        """Реакция на программную смену индикатора сортировки."""
        logging.debug(f"[SORT] Индикатор сортировки изменён: col={logical_index}, order={sort_order}")
        self._schedule_cache_rebuild()

    def _schedule_cache_rebuild(self):
        """Планирует перестройку кэша единым таймером, коалесцируя частые события."""
        try:
            if self._rebuild_timer.isActive():
                self._rebuild_timer.stop()
            self._rebuild_timer.start(0)
        except Exception:
            # Fallback: если таймер по какой-то причине недоступен
            try:
                QTimer.singleShot(0, self._clear_cache_after_sort)
            except Exception:
                pass
    
    def _clear_cache_after_sort(self):
        """Перестраивает кэш после сортировки по фактическому порядку строк."""
        old_cache_size = len(self._current_links)
        # Перестраиваем кэш, чтобы соответствовать отсортированным строкам
        self.rebuild_cache_from_items()
        new_cache_size = len(self._current_links)
        logging.debug(f"[SORT] Кэш перестроен: было {old_cache_size}, стало {new_cache_size}")
        # Оповещаем подписчиков (например, контроллер) о том, что таблица обновлена
        try:
            self.table_populated.emit()
        except Exception as e:
            logging.debug(f"[SORT] Не удалось эмитить table_populated: {e}")
