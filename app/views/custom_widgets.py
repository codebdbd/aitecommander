from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
)

from app.config_data import app_config
from app.utils.db.db_workers import AsyncTaskMixin
from app.utils.ui.dnd.tree import DragDropHandler
from app.views.tree_components.move_operations_handler import MoveOperationsHandler

# Используем строковые литералы "section" и "category"

COLUMN_DATA = 0  # Индекс колонки с данными в таблицах


class NoFocusRectDelegate(QStyledItemDelegate):
    """Делегат для убирания рамки фокуса с элементов."""

    def paint(self, painter, option, index):
        option2 = QStyleOptionViewItem(option)
        option2.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option2, index)


class HighQualityTreeDelegate(QStyledItemDelegate):
    """Делегат для высококачественной отрисовки иконок в дереве разделов."""

    def __init__(self, item_height: int | None = None, parent=None):
        super().__init__(parent)
        try:
            self._item_height = int(item_height) if item_height is not None else None
        except Exception:
            self._item_height = None

    def paint(self, painter, option, index):
        # Убираем рамку фокуса у элементов дерева
        option.state &= ~QStyle.StateFlag.State_HasFocus

        # Получаем иконку из модели
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QIcon) and not icon.isNull():
            # Вычисляем размер иконки
            icon_size = option.decorationSize
            if icon_size.width() <= 0 or icon_size.height() <= 0:
                icon_size = option.widget.iconSize() if option.widget else QSize(16, 16)

            # Создаем временную опцию с высококачественной иконкой
            temp_option = QStyleOptionViewItem(option)

            # Создаем высококачественную иконку
            device_pixel_ratio = (
                painter.device().devicePixelRatio()
                if hasattr(painter.device(), "devicePixelRatio")
                else 1.0
            )
            actual_size = QSize(
                int(icon_size.width() * device_pixel_ratio),
                int(icon_size.height() * device_pixel_ratio),
            )
            pixmap = icon.pixmap(actual_size)
            pixmap.setDevicePixelRatio(device_pixel_ratio)

            # Масштабируем с высоким качеством если нужно
            if not pixmap.isNull():
                pixmap_size = pixmap.size() / device_pixel_ratio
                if (
                    pixmap_size.width() > icon_size.width()
                    or pixmap_size.height() > icon_size.height()
                ):
                    scale_factor = min(
                        icon_size.width() / pixmap_size.width(),
                        icon_size.height() / pixmap_size.height(),
                    )
                    new_size = QSize(
                        int(pixmap_size.width() * scale_factor),
                        int(pixmap_size.height() * scale_factor),
                    )
                    pixmap = pixmap.scaled(
                        new_size * device_pixel_ratio,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    pixmap.setDevicePixelRatio(device_pixel_ratio)

            # Создаем высококачественную иконку и устанавливаем в опцию
            high_quality_icon = QIcon()
            high_quality_icon.addPixmap(pixmap)
            temp_option.icon = high_quality_icon

            # Рисуем стандартным способом с улучшенной иконкой
            super().paint(painter, temp_option, index)
        else:
            # Рисуем без иконки
            super().paint(painter, option, index)

        # Без обводки при наведении для дерева согласно требованиям

    def sizeHint(self, option: QStyleOptionViewItem, index):
        # Базовый размер от Qt
        base = super().sizeHint(option, index)
        # Жёстко возвращаем единую высоту строки из глобальной конфигурации (ui.row_height)
        try:
            row_h = int(app_config.get_row_height())
        except Exception:
            row_h = self._item_height if self._item_height else base.height()
        return QSize(base.width(), row_h)


class StructureTreeView(QTreeView, AsyncTaskMixin):
    """
    Итоговый QTreeView для дерева структуры на Model/View.
    Сохраняет визуальные параметры и делегаты; сигналы оставлены для совместимости с прежним API.
    """

    # Совместимость: заготовленные сигналы, будут задействованы после DnD-рефактора
    itemsMoved: pyqtSignal = pyqtSignal(object)
    invalidDrop: pyqtSignal = pyqtSignal(str)
    dragFeedback: pyqtSignal = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_tree_view()
        # Интеграция обработчиков для совместимости с прежним API
        self.move_operations_handler = MoveOperationsHandler(self)
        self.drag_drop_handler = DragDropHandler(self)

    def _setup_tree_view(self):
        """Настройка параметров QTreeView под текущие UX-требования."""
        # DnD включен на уровне вида (логика обработчиков находится в обработчиках)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

        # Делегат высокого качества (иконки, высота строки)
        try:
            item_h = int(app_config.get_row_height())
        except Exception:
            item_h = None
        self.setItemDelegate(HighQualityTreeDelegate(item_height=item_h))

        # Производительность: одинаковая высота строк
        try:
            self.setUniformRowHeights(True)
        except Exception:
            pass

        # Hover-поведение как в прежней версии
        self.setMouseTracking(True)

    # --- Emit helpers (совместимость с прежним API) ---
    def emit_items_moved(self, payload):
        try:
            self.itemsMoved.emit(payload)
        except Exception:
            # Без жестких зависимостей: даем обратную связь через dragFeedback
            try:
                self.dragFeedback.emit(
                    {"type": "emit_error", "signal": "itemsMoved", "error": "emit failed"}
                )
            except Exception:
                pass

    def emit_invalid_drop(self, reason: str):
        try:
            self.invalidDrop.emit(reason)
        except Exception:
            try:
                self.dragFeedback.emit(
                    {"type": "emit_error", "signal": "invalidDrop", "error": reason}
                )
            except Exception:
                pass

    def emit_drag_feedback(self, info):
        try:
            self.dragFeedback.emit(info)
        except Exception:
            pass

    # --- DnD события делегируем обработчику ---
    def dragEnterEvent(self, event):
        self.drag_drop_handler.handle_drag_enter_event(event)

    def dragMoveEvent(self, event):
        self.drag_drop_handler.handle_drag_move_event(event)

    def dragLeaveEvent(self, event):
        self.drag_drop_handler.handle_drag_leave_event(event)

    def dropEvent(self, event):
        self.drag_drop_handler.handle_drop_event(event)
