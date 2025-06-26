# app/views/category_tiles.py

import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QStyledItemDelegate
from PyQt6.QtGui import QIcon, QPainter, QFont, QFontMetrics, QColor, QPen, QBrush, QDrag
from PyQt6.QtCore import QMimeData, Qt, QSize, QRect


logger = logging.getLogger("category_tiles")

class _CategoryListWidget(QListWidget):
    """QListWidget with custom drag that serialises category id."""
    MIME_TYPE = 'application/x-category-id'

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        cat_id = item.data(Qt.ItemDataRole.UserRole)
        if cat_id is None:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(self.MIME_TYPE, str(cat_id).encode('utf-8'))
        drag.setMimeData(mime)
        # Разрешаем копирование/перемещение. Qt игнорирует, если цель не примет перетаскивание.
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)

    # Ensure we claim we can start drag when left button pressed
    def mouseMoveEvent(self, event):
        # Default implementation already triggers startDrag; keep behaviour
        super().mouseMoveEvent(event)

# Helper to wrap text into up to 4 lines fitting a given max width

def _wrap_text_smart(text: str, fm: QFontMetrics, max_width: int, max_lines: int = 4):
    """Split text into up to *max_lines* so that each line fits *max_width* pixels.
    Words are wrapped, very long words are split per-character. Last line gets an ellipsis
    if the text does not fit completely.
    """
    lines = []
    current = ""
    words = text.split()
    for w_i, word in enumerate(words):
        # If word itself too long, split char-wise
        if fm.horizontalAdvance(word) > max_width:
            for ch in word:
                test = current + ch
                if fm.horizontalAdvance(test) > max_width:
                    if current:
                        lines.append(current)
                        if len(lines) == max_lines:
                            return lines[:-1] + [fm.elidedText(text[text.index(ch):], Qt.TextElideMode.ElideRight, max_width)]
                    current = ch
                else:
                    current = test
            current += " "
            continue
        test = (current + " " if current else "") + word
        if fm.horizontalAdvance(test) > max_width:
            lines.append(current)
            if len(lines) == max_lines:
                return lines[:-1] + [fm.elidedText(" ".join(words[w_i:]), Qt.TextElideMode.ElideRight, max_width)]
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    # Ensure max lines
    if len(lines) > max_lines:
        lines = lines[: max_lines]
        lines[-1] = fm.elidedText(lines[-1], Qt.TextElideMode.ElideRight, max_width)
    return lines

class CategoryTileDelegate(QStyledItemDelegate):
    def __init__(self, icon_size=48, tile_size=QSize(110, 110), parent=None):
        super().__init__(parent)
        self.icon_size = icon_size
        self.tile_size = tile_size
        self.text_color = QColor('#222')
        self.bg_selected = QColor('#e0eaff')
        self.bg_hover = QColor('#f5f7fa')
        self.border_radius = 8

    def paint(self, painter, option, index):
        painter.save()
        rect = option.rect
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        # Background
        from PyQt6.QtWidgets import QStyle
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setBrush(QBrush(self.bg_selected))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, self.border_radius, self.border_radius)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setBrush(QBrush(self.bg_hover))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, self.border_radius, self.border_radius)
        # Icon
        icon_rect = QRect(
            rect.left() + (rect.width() - self.icon_size) // 2,
            rect.top() + 10,
            self.icon_size, self.icon_size
        )
        if isinstance(icon, QIcon) and not icon.isNull():
            icon.paint(painter, icon_rect)
        else:
            # Нарисовать placeholder
            painter.setBrush(QBrush(QColor('#cccccc')))
            painter.setPen(QPen(QColor('#999999')))
            painter.drawEllipse(icon_rect)
        # Text — wrap into up to 4 lines like Windows Explorer
        painter.setPen(QPen(self.text_color))
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        fm = QFontMetrics(font)
        max_width = rect.width() - 10
        lines = _wrap_text_smart(text, fm, max_width, max_lines=4)
        line_height = fm.height()
        start_y = icon_rect.bottom() + 5
        for i, line in enumerate(lines):
            painter.drawText(QRect(rect.left() + 5, start_y + i * line_height, max_width, line_height),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, line)
        painter.restore()

    def sizeHint(self, option, index):
        return self.tile_size

class CategoryTiles(QWidget):
    """
    Виджет плиток категорий с поддержкой drag-and-drop и кастомным делегатом.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)
        self.list_widget = _CategoryListWidget()
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_widget.setSpacing(12)
        self.list_widget.setIconSize(QSize(48, 48))
        self.list_widget.setDragEnabled(True)
        self.list_widget.setAcceptDrops(False)
        self.list_widget.setDropIndicatorShown(False)
        self.list_widget.setMouseTracking(True)
        self.list_widget.setItemDelegate(CategoryTileDelegate())
        # Обработчики двойного клика/активации плитки
        self.list_widget.itemDoubleClicked.connect(self._on_item_clicked)
        self.list_widget.itemActivated.connect(self._on_item_clicked)
        # На случай если itemDoubleClicked не срабатывает из-за делегата, подписываемся на signal doubleClicked (QModelIndex)
        self.list_widget.doubleClicked.connect(self._on_index_activated)
        self.layout.addWidget(self.list_widget)
        self.categories = []

    def set_categories(self, categories):
        """
        :param categories: список dict с ключами id, name, icon_path
        """
        import os
        from pathlib import Path
        from app.config import UI_ICONS_DIR, LINK_ICONS_DIR
        logger.info(f"set_categories input: {categories}")
        logger.info(f"Текущая рабочая директория: {os.getcwd()}")
        self.categories = categories
        self.list_widget.clear()
        from PyQt6.QtGui import QIcon
        for cat in categories:
            icon_path = cat.get('icon_path', '')
            resolved_path = ''
            if icon_path:
                if os.path.isabs(icon_path):
                    resolved_path = icon_path
                else:
                    # Сначала ищем в LINK_ICONS_DIR
                    user_path = str(Path(LINK_ICONS_DIR) / icon_path)
                    if os.path.isfile(user_path):
                        resolved_path = user_path
                    else:
                        # Потом ищем в UI_ICONS_DIR
                        default_path = str(Path(UI_ICONS_DIR) / icon_path)
                        if os.path.isfile(default_path):
                            resolved_path = default_path
            file_exists = os.path.isfile(resolved_path)
            logger.info(f"icon_path={icon_path} resolved={resolved_path} exists={file_exists}")
            icon = QIcon(resolved_path) if resolved_path else QIcon()
            logger.info(f"icon_full_path={resolved_path} isNull={icon.isNull()}")
            item = QListWidgetItem(icon, cat.get('name', ''))
            # Calculate height based on wrapped text lines (like Explorer)
            font = QFont()
            font.setPointSize(10)
            fm = QFontMetrics(font)
            lines = _wrap_text_smart(cat.get('name', ''), fm, 110 - 10, max_lines=4)
            tile_height = 10 + 48 + 5 + len(lines) * fm.height() + 5
            item.setSizeHint(QSize(110, max(tile_height, 110)))
            item.setData(Qt.ItemDataRole.UserRole, cat.get('id'))
            self.list_widget.addItem(item)

    def _on_index_activated(self, index):
        # Получить QListWidgetItem из QModelIndex и переиспользовать существующий обработчик
        item = self.list_widget.item(index.row())
        if item:
            self._on_item_clicked(item)

    def _on_item_clicked(self, item):
        logger.debug(f"Category tile activated: {item.text()}")
        cat_id = item.data(Qt.ItemDataRole.UserRole)
        if cat_id is not None:
            # Предполагается, что родитель — MainWindow
            main_win = self.window()
            if hasattr(main_win, "load_category"):
                main_win.load_category(cat_id)

    # Для интеграции с внешними обработчиками drag-and-drop можно расширить методы
