# app/views/category_tiles.py

"""Простые плитки категорий с иконками.

Рефакторинг: Вид больше не создаёт/исполняет контекстное меню сам.
Вместо этого он генерирует сигналы, а контроллер показывает меню и
выполняет команды. Это снижает связность и устраняет утечки логики
в слой представления.
"""

import logging

from PyQt6.QtCore import QPoint, QPointF, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QDrag,
    QFont,
    QFontMetrics,
    QIcon,
    QPen,
    QTextLayout,
    QTextOption,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStyledItemDelegate,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.config_data import app_config
from app.utils.ui.dnd.mime import MimeDataParser
from app.utils.ui.icon import resolve_category_icon_path
from app.utils.ui.icon.cache_manager import get_cached_category_icon
from app.utils.ui.qt.roles import get_item_int

logger = logging.getLogger("category_tiles")


class _CategoryListWidget(QListWidget):
    """QListWidget with custom drag that serialises category id."""
    MIME_TYPE = app_config.get_category_mime_type()

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            logger.debug("CategoryListWidget.startDrag: no current item")
            return
        cat_id = get_item_int(item)
        if cat_id is None:
            logger.debug("CategoryListWidget.startDrag: no category id")
            return
        
        logger.debug("CategoryListWidget.startDrag: starting drag for category %s (%s)", cat_id, item.text())
        drag = QDrag(self)
        mime = MimeDataParser.create_mime_data([int(cat_id)], self.MIME_TYPE)
        drag.setMimeData(mime)
        logger.debug("CategoryListWidget.startDrag: MIME type = %s, data = %s", self.MIME_TYPE, cat_id)
        
        result = drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        logger.debug("CategoryListWidget.startDrag: drag result = %s", result)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)


class CategoryTileDelegate(QStyledItemDelegate):
    """Простой делегат для отрисовки плиток категорий."""
    
    def __init__(self, icon_size=None, tile_size=None, parent=None):
        super().__init__(parent)
        self.icon_size = icon_size or QSize(48, 48)
        self.tile_size = tile_size or QSize(120, 100)
        self.padding = 8
        self.border_radius = 4
        self._font_diag_logged = False


    def paint(self, painter, option, index):
        """Простая отрисовка плитки: иконка сверху, текст снизу."""
        painter.save()
        rect = option.rect
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        try:
            cfg_sz = app_config.get_tile_text_font_size()
            if isinstance(cfg_sz, (int, float)) and cfg_sz > 0:
                f = painter.font()
                f.setPointSize(int(cfg_sz))
                painter.setFont(f)
        except (TypeError, ValueError, AttributeError) as e:
            logger.debug("Failed to set font size from config in paint: %s", e)
        
        try:
            from PyQt6.QtWidgets import QStyle
            w = option.widget
            style = w.style() if w is not None else None
            if style is not None:
                style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, w)
        except (AttributeError, RuntimeError) as e:
            logger.debug("Style primitive draw skipped: %s", e)
        
        icon_rect = QRect(
            rect.left() + (rect.width() - self.icon_size.width()) // 2,
            rect.top() + self.padding,
            self.icon_size.width(), self.icon_size.height()
        )
        
        if isinstance(icon, QIcon) and not icon.isNull():
            icon.paint(painter, icon_rect)
        else:
            mid = option.palette.color(option.palette.ColorRole.Mid)
            dark = option.palette.color(option.palette.ColorRole.Dark)
            text_col = option.palette.color(option.palette.ColorRole.BrightText)
            painter.setBrush(QBrush(mid))
            painter.setPen(QPen(dark))
            painter.drawEllipse(icon_rect)
            try:
                placeholder_font = QFont(painter.font())
                placeholder_font.setBold(True)
                placeholder_font.setPointSize(max(8, int(self.icon_size.height() * 0.45)))
                painter.setFont(placeholder_font)
                painter.setPen(QPen(text_col))
                qmark = "?"
                fm_q = QFontMetrics(placeholder_font)
                tw = fm_q.horizontalAdvance(qmark)
                th = fm_q.ascent()
                cx = icon_rect.left() + (icon_rect.width() - tw) // 2
                cy = icon_rect.top() + (icon_rect.height() + th) // 2 - 2
                painter.drawText(QPoint(cx, cy), qmark)
            except (RuntimeError, ValueError) as e:
                logger.debug("Placeholder '?' draw skipped: %s", e)
        
        if text:
            try:
                if not self._font_diag_logged:
                    fm_diag = QFontMetrics(painter.font())
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "CategoryTileDelegate font diag: family='%s', requested_px=%s, pixelSize=%s, pointSizeF=%.2f, fm.height=%s, fm.lineSpacing=%s",
                            painter.font().family(),
                            app_config.get_tile_text_font_size(),
                            painter.font().pixelSize(),
                            painter.font().pointSizeF(),
                            fm_diag.height(),
                            fm_diag.lineSpacing(),
                        )
                    self._font_diag_logged = True
            except (RuntimeError, AttributeError) as e:
                logger.debug("Font diagnostics skipped: %s", e)
            text_rect = QRect(
                rect.left() + self.padding,
                rect.top() + self.padding + self.icon_size.height() + 5,
                rect.width() - 2 * self.padding,
                0
            )
            fm = QFontMetrics(painter.font())
            layout = QTextLayout(text, painter.font())
            opt = QTextOption()
            opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            opt.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            layout.setTextOption(opt)
            layout.beginLayout()
            lines = []
            y = 0
            available_w = text_rect.width()
            try:
                max_lines = int(app_config.get_tile_text_max_lines())
            except (TypeError, ValueError, AttributeError) as e:
                logger.debug("Invalid max_lines config, fallback to 3: %s", e)
                max_lines = 3
            has_more = False
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(available_w)
                line.setPosition(QPointF(0.0, float(y)))
                lines.append(line)
                y += int(line.height())
                if len(lines) >= max_lines:
                    probe = layout.createLine()
                    has_more = probe.isValid()
                    break
            layout.endLayout()

            text_rect.setHeight(y)

            painter.setPen(option.palette.color(option.palette.ColorRole.WindowText))

            for idx, line in enumerate(lines):
                line_text = text[line.textStart(): line.textStart() + line.textLength()]
                natural_w = line.naturalTextWidth()
                draw_x = text_rect.x() + max(0, (available_w - int(natural_w)) // 2)
                draw_y = text_rect.y() + int(line.position().y()) + fm.ascent()
                if idx == len(lines) - 1 and has_more:
                    elided = fm.elidedText(line_text, Qt.TextElideMode.ElideRight, available_w)
                    if elided == line_text:
                        ellipsis = "…"
                        ell_w = fm.horizontalAdvance(ellipsis)
                        max_w = max(0, available_w - ell_w)
                        core = fm.elidedText(line_text, Qt.TextElideMode.ElideRight, max_w)
                        text_to_draw = (core if core else "") + ellipsis
                    else:
                        text_to_draw = elided
                    draw_w = fm.horizontalAdvance(text_to_draw)
                    draw_x = text_rect.x() + max(0, (available_w - draw_w) // 2)
                    painter.drawText(QPoint(draw_x, draw_y), text_to_draw)
                else:
                    painter.drawText(QPoint(draw_x, draw_y), line_text)
        
        painter.restore()

    def sizeHint(self, option, index):
        """Простой расчет размера плитки."""
        font = QFont(option.font)
        try:
            cfg_sz = app_config.get_tile_text_font_size()
            if isinstance(cfg_sz, (int, float)) and cfg_sz > 0:
                font.setPointSize(int(cfg_sz))
        except (TypeError, ValueError, AttributeError) as e:
            logger.debug("Failed to set font size from config in sizeHint: %s", e)
        try:
            max_lines = int(app_config.get_tile_text_max_lines())
        except (TypeError, ValueError, AttributeError) as e:
            logger.debug("Invalid max_lines config in sizeHint, fallback to 3: %s", e)
            max_lines = 3
        try:
            text = index.data(Qt.ItemDataRole.DisplayRole)
        except (RuntimeError, AttributeError) as e:
            logger.debug("Failed to read DisplayRole in sizeHint: %s", e)
            text = ""
        available_w = self.tile_size.width() - 2 * self.padding
        layout = QTextLayout(text or "", font)
        opt = QTextOption()
        opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        opt.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        layout.setTextOption(opt)
        layout.beginLayout()
        y = 0
        lines = 0
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(available_w)
            y += int(line.height())
            lines += 1
            if lines >= max_lines:
                break
        layout.endLayout()
        text_h = y
        height = self.padding + self.icon_size.height() + 5 + text_h + self.padding
        return QSize(self.tile_size.width(), height)

    def helpEvent(self, event, view, option, index):
        """Показывает тултип с полным названием, если текст усечён или для единообразия UX."""
        try:
            if not index.isValid() or event is None:
                return False
            text = index.data(Qt.ItemDataRole.DisplayRole) or ""
            if not text:
                return super().helpEvent(event, view, option, index)

            try:
                max_lines = int(app_config.get_tile_text_max_lines())
            except (TypeError, ValueError, AttributeError) as e:
                logger.debug("Invalid max_lines config in helpEvent, fallback to 3: %s", e)
                max_lines = 3

            available_w = max(0, option.rect.width() - 2 * self.padding)

            font = QFont(option.font)
            try:
                cfg_sz = app_config.get_tile_text_font_size()
                if isinstance(cfg_sz, (int, float)) and cfg_sz > 0:
                    font.setPointSize(int(cfg_sz))
            except (TypeError, ValueError, AttributeError) as e:
                logger.debug("Failed to set font size in helpEvent: %s", e)

            layout = QTextLayout(text, font)
            opt = QTextOption()
            opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            opt.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            layout.setTextOption(opt)
            layout.beginLayout()
            lines_count = 0
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(available_w)
                lines_count += 1
                if lines_count >= max_lines:
                    break
            layout.endLayout()

            QToolTip.showText(event.globalPos(), text, view)
            return True
        except (RuntimeError, AttributeError, ValueError) as e:
            logger.warning("helpEvent failed, using default tooltip handling: %s", e)
            return super().helpEvent(event, view, option, index)

class CategoryTiles(QWidget):
    category_selected: pyqtSignal = pyqtSignal(int)
    # Сигналы, которые должен обрабатывать контроллер
    editRequested: pyqtSignal = pyqtSignal(int)
    deleteRequested: pyqtSignal = pyqtSignal(int)
    addLinkRequested: pyqtSignal = pyqtSignal(int)
    contextMenuRequested: pyqtSignal = pyqtSignal(int, QPoint)

    def __init__(self, parent=None, structure_controller=None, ui_state_manager=None, dialog_provider=None):
        """Простой UI-компонент для отображения плиток категорий."""
        super().__init__(parent)
        
        self._current_item_id = None

        self.structure_controller = structure_controller
        self.ui_state_manager = ui_state_manager
        self.dialog_provider = dialog_provider

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.list_widget = _CategoryListWidget()
        self.list_widget.setObjectName('categoryTiles')
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.setMouseTracking(True)
        vp = self.list_widget.viewport()
        try:
            vp.setMouseTracking(True)
            vp.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        except (AttributeError, RuntimeError) as e:
            logger.debug("Viewport hover setup skipped: %s", e)
        self.delegate = CategoryTileDelegate(parent=self)
        self.list_widget.setItemDelegate(self.delegate)

        self.list_widget.setUniformItemSizes(False)
        try:
            self.list_widget.setWordWrap(True)
        except (AttributeError, RuntimeError) as e:
            logger.debug("WordWrap not supported on list widget: %s", e)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_widget.setSpacing(8)

        self.list_widget.setDragEnabled(True)
        self.list_widget.setAcceptDrops(False)
        self.list_widget.setDropIndicatorShown(False)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        
        self.list_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._on_item_clicked)
        self.list_widget.itemClicked.connect(self._on_item_selected)
        self.list_widget.currentItemChanged.connect(self._on_item_selected)

        try:
            if getattr(app_config, 'get_debug_show_tile_font_sample', None) and app_config.get_debug_show_tile_font_sample():
                sample = QLabel("Sample: Абв ABC 123")
                sample.setObjectName('tileFontSample')
                self.layout.addWidget(sample, 0)
                logger.debug("CategoryTiles: debug font sample label added (inherits global font)")
        except (AttributeError, RuntimeError) as e:
            logger.debug("Debug font sample init skipped: %s", e)

        self.layout.addWidget(self.list_widget, 1)
        
        # Контекстное меню строит контроллер — вид только генерирует сигнал
        
    def set_categories(self, categories: list):
        """Простое обновление списка категорий."""
        logger.debug("Loading %d categories", len(categories))
        
        self.list_widget.clear()
        
        for category in categories:
            name = category.get('name', '')
            icon_path = category.get('icon_path', '')
            raw_id = category.get('id')
            category_id = None
            try:
                if raw_id is None:
                    raise ValueError("id is None")
                if isinstance(raw_id, int):
                    category_id = raw_id
                elif isinstance(raw_id, str):
                    category_id = int(raw_id)
                else:
                    category_id = int(raw_id)  # попытка для типов вроде numpy.int64 etc
            except Exception:
                logger.warning("Skip category with invalid id '%s' and name '%s'", raw_id, name)
                continue
            
            if icon_path:
                resolved_path = resolve_category_icon_path(icon_path)
                icon = get_cached_category_icon(resolved_path)
            else:
                icon = QIcon()
            
            item = QListWidgetItem(icon, name)
            item.setData(Qt.ItemDataRole.UserRole, category_id)
            self.list_widget.addItem(item)



    def _on_item_selected(self, item, previous=None):
        """Обновляем текущий выбранный элемент при клике."""
        if item is None:
            logger.debug("No item selected")
            # Избегаем жёсткой зависимости от UIStateManager API здесь
            self._current_item_id = None
            return
        
        item_id = get_item_int(item)
        if item_id is None:
            logger.debug("No item_id found in item data")
            return
        
        self._current_item_id = item_id
        logger.debug("Selected category tile ID %s (%s)", item_id, item.text())

    def _on_item_clicked(self, item):
        logger.debug("Category tile activated: %s", item.text())
        cat_id = get_item_int(item)
        if cat_id is not None:
            self._current_item_id = cat_id
            self.category_selected.emit(cat_id)

    def inject_dependencies(self, structure_controller=None, ui_state_manager=None, dialog_provider=None):
        """Инжектирует зависимости после создания контроллеров."""
        if structure_controller:
            self.structure_controller = structure_controller
        if ui_state_manager:
            self.ui_state_manager = ui_state_manager
        if dialog_provider:
            self.dialog_provider = dialog_provider
    
    def _show_context_menu(self, pos: QPoint):
        """Запрашивает показ контекстного меню через контроллер (сигнал)."""
        logger.debug("Context menu requested at position %s", pos)

        index = self.list_widget.indexAt(pos)
        if not index.isValid():
            logger.debug("Invalid index at position")
            return

        item = self.list_widget.itemFromIndex(index)
        if not item:
            logger.debug("No item found at index")
            return
            
        item_id = get_item_int(item)
        if item_id is None:
            logger.debug("No item_id found in item data")
            return

        self._current_item_id = item_id
        logger.debug("Emitting contextMenuRequested for category %s (%s)", item_id, item.text())
        try:
            self.contextMenuRequested.emit(item_id, self.list_widget.mapToGlobal(pos))
        except Exception as e:
            logger.warning("Failed to emit contextMenuRequested: %s", e)
    
    def select_category(self, category_id: int) -> None:
        """Выбрать категорию по ID."""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == category_id:
                self.list_widget.setCurrentItem(item)
                self._current_item_id = category_id
                self.list_widget.scrollToItem(item)
                logger.debug("Selected category tile ID %s", category_id)
                return
        logger.debug("Could not find category tile ID %s", category_id)
    
    def get_categories_count(self) -> int:
        """Получить общее количество категорий."""
        return self.list_widget.count()
    

    def _execute_edit_category(self, category_id: int):
        """Устаревший путь: теперь просто эмитим сигнал для контроллера."""
        logger.debug("Emit editRequested for ID %s", category_id)
        self.editRequested.emit(category_id)
    
    def _execute_delete_category(self, category_id: int):
        """Устаревший путь: теперь просто эмитим сигнал для контроллера."""
        logger.debug("Emit deleteRequested for ID %s", category_id)
        self.deleteRequested.emit(category_id)
    
    def _execute_add_link(self, category_id: int):
        """Устаревший путь: теперь просто эмитим сигнал для контроллера."""
        logger.debug("Emit addLinkRequested for ID %s", category_id)
        self.addLinkRequested.emit(category_id)

