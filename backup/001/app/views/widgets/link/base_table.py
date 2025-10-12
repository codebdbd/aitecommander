# Основной модуль таблицы ссылок
# Содержит главный класс LinksTableView и базовую функциональность

import logging

from PyQt6.QtCore import QModelIndex, QSize, Qt, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from app.config_data import app_config
from app.utils.ui.dnd.link import DragDropHandlerMixin
from app.utils.ui.dnd.mime import get_link_mime
from app.views.widgets.base.base_widgets import BaseDragDropTableWidget
from app.views.widgets.link.links_model import LinksTableModel

from .data_management import DataManagementMixin

# Импортируем все миксины
from .item_builders import ItemBuildersMixin
from .population_manager import PopulationManagerMixin
from .row_operations import RowOperationsMixin

# Модульный логгер
logger = logging.getLogger(__name__)


class TableDelegate(QStyledItemDelegate):
    """Единый делегат: подсветка строки по hover и элидирование по символам в колонке 'Название'."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hovered_row = -1
        self.hover_color = QColor("#444444")  # Hover цвет для строк таблицы
        # Настройки размеров шрифтов из единого реестра ui.fonts.*
        def _get_px(key: str) -> int | None:
            try:
                v = app_config.ui.get(f"ui.fonts.{key}")
                return int(v) if v is not None else None
            except Exception:
                return None
        # Единицы для шрифтов: 'px' или 'pt'
        try:
            self._font_units = str(app_config.ui.get("ui.fonts.units", "px")).strip().lower()
        except Exception:
            self._font_units = "px"
        if self._font_units not in ("px", "pt"):
            self._font_units = "px"

        # Индивидуальные размеры для колонок (обратная совместимость)
        self.col_opened_px = _get_px("table_opened_col_px")  # колонка "Открывалась" (index=2)
        self.col_notes_px = _get_px("table_notes_col_px")    # колонка "Заметки" (index=3)

        # Новый способ: массив размеров для всех колонок
        self.col_sizes: dict[int, int] = {}
        try:
            arr = app_config.ui.get("ui.fonts.table_cols_px")  # ожидается список чисел или None
        except Exception:
            arr = None
        if isinstance(arr, (list, tuple)):
            for i, v in enumerate(arr):
                try:
                    if v is None:
                        continue
                    iv = int(v)
                    if iv > 0:
                        self.col_sizes[i] = iv
                except Exception:
                    continue

    def paint(self, painter, option, index):
        # Подсветка всей строки при hover (если не выбрана)
        is_hovered_row = self.hovered_row == index.row()
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if is_hovered_row and not is_selected:
            painter.save()
            painter.fillRect(option.rect, self.hover_color)
            painter.restore()

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # Применяем единые размеры шрифтов для конкретных колонок, если заданы в конфиге
        try:
            col = index.column()
            # Приоритет: общий массив table_cols_px, затем старые ключи для 2/3
            val = self.col_sizes.get(col)
            if val is None:
                if col == 2:
                    val = self.col_opened_px
                elif col == 3:
                    val = self.col_notes_px
            if val and int(val) > 0:
                f = opt.font
                if self._font_units == "pt":
                    f.setPointSize(int(val))
                else:
                    f.setPixelSize(int(val))
                opt.font = f
        except Exception:
            pass

        # Цвет текста для колонки "Открывалась" (index=2) — из qproperty LinksTableView.openedColColor
        try:
            if index.column() == 2:
                view = self.parent() if hasattr(self, 'parent') else None
                color = None
                if view is not None and hasattr(view, 'openedColColor'):
                    color = view.openedColColor
                if isinstance(color, QColor) and color.isValid():
                    pal = QPalette(opt.palette)
                    pal.setColor(QPalette.ColorRole.Text, color)
                    pal.setColor(QPalette.ColorRole.WindowText, color)
                    opt.palette = pal
        except Exception:
            pass

        # Цвет текста для колонки "Заметки" (index=3) — из qproperty LinksTableView.notesColColor
        try:
            if index.column() == 3:
                view = self.parent() if hasattr(self, 'parent') else None
                color = None
                if view is not None and hasattr(view, 'notesColColor'):
                    color = view.notesColColor
                if isinstance(color, QColor) and color.isValid():
                    pal = QPalette(opt.palette)
                    pal.setColor(QPalette.ColorRole.Text, color)
                    pal.setColor(QPalette.ColorRole.WindowText, color)
                    opt.palette = pal
        except Exception:
            pass

        # Для колонки 'Название' (index 1) — жёсткое однострочное элидирование по символам
        if index.column() == 1:
            opt.textElideMode = Qt.TextElideMode.ElideRight
            try:
                available_w = max(0, opt.rect.width() - 4)
            except Exception:
                available_w = opt.rect.width()
            opt.text = opt.fontMetrics.elidedText(
                opt.text, Qt.TextElideMode.ElideRight, available_w
            )
            opt.displayAlignment = (
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )

        super().paint(painter, opt, index)

        # Границы верхнего левого угла (ячейка над строкой 1 и перед колонкой 0)
        # рендерятся через QSS (QTableView QTableCornerButton::section) в dark.qss


class LinksTableView(
    BaseDragDropTableWidget,
    ItemBuildersMixin,
    DataManagementMixin,
    RowOperationsMixin,
    PopulationManagerMixin,
    DragDropHandlerMixin,
    ):
    """Основной класс таблицы ссылок с модульной архитектурой."""

    # qproperty для задания цвета колонки "Открывалась" из темы (QSS: qproperty-openedColColor)
    def _get_opened_col_color(self) -> QColor:
        try:
            return getattr(self, "_opened_col_color", QColor())
        except Exception:
            return QColor()

    def _set_opened_col_color(self, value) -> None:
        try:
            if isinstance(value, QColor):
                self._opened_col_color = value
            else:
                self._opened_col_color = QColor(str(value))
            self.viewport().update()
        except Exception:
            pass

    openedColColor = pyqtProperty(QColor, fget=_get_opened_col_color, fset=_set_opened_col_color)

    # qproperty для задания цвета колонки "Заметки" из темы (QSS: qproperty-notesColColor)
    def _get_notes_col_color(self) -> QColor:
        try:
            return getattr(self, "_notes_col_color", QColor())
        except Exception:
            return QColor()

    def _set_notes_col_color(self, value) -> None:
        try:
            if isinstance(value, QColor):
                self._notes_col_color = value
            else:
                self._notes_col_color = QColor(str(value))
            self.viewport().update()
        except Exception:
            pass

    notesColColor = pyqtProperty(QColor, fget=_get_notes_col_color, fset=_set_notes_col_color)

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
        # Имя объекта для точечного применения QSS (в т.ч. размера шрифта шапки)
        try:
            self.setObjectName("linksTable")
        except Exception:
            pass
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
        self.delegate = TableDelegate(self)
        self.setItemDelegate(self.delegate)
        # Глобально: не переносим слова, элидируем справа
        try:
            self.setWordWrap(False)
        except Exception:
            pass
        try:
            self.setTextElideMode(Qt.TextElideMode.ElideRight)
        except Exception:
            pass
        # Используем единый делегат для всех колонок, чтобы подсветка hover применялась ко всей строке
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
        # Режим изменения ширины колонки 2 ("Открывалась") — из конфига
        try:
            col2_mode = str(app_config.ui.get("ui.links_table_col2_mode", "fixed")).lower()
        except Exception:
            col2_mode = "fixed"
        try:
            if col2_mode in ("fixed", "f"):
                header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            elif col2_mode in ("interactive", "i"):
                header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
            elif col2_mode in ("contents", "content", "auto", "resizeToContents".lower()):
                header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            else:
                header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        except Exception:
            # Фолбэк — Fixed
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
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

    def __del__(self):
        """Отписываемся от сигналов для предотвращения утечек памяти."""
        try:
            if hasattr(self, 'entered'):
                self.entered.disconnect()
            if hasattr(self, 'horizontalHeader'):
                header = self.horizontalHeader()
                if header:
                    header.sectionClicked.disconnect()
            if hasattr(self, 'model'):
                model = self.model()
                if model and hasattr(model, 'layoutChanged'):
                    model.layoutChanged.disconnect()
            if hasattr(self, 'items_reordered'):
                self.items_reordered.disconnect()
        except (RuntimeError, TypeError):
            # Объект уже удалён или сигнал не подключён
            pass
