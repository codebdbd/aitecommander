from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
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


class StructureTreeWidget(QTreeWidget, AsyncTaskMixin):
    """
    Кастомный QTreeWidget с правилами drag-and-drop для структуры приложения
    (Разделы и Категории).
    """

    # Сигналы слабой связанности: внешний код подписывается и решает, что делать.
    itemsMoved: pyqtSignal = pyqtSignal(
        object
    )  # payload: произвольная структура о перемещенных элементах
    invalidDrop: pyqtSignal = pyqtSignal(str)  # причина недопустимого drop
    dragFeedback: pyqtSignal = pyqtSignal(object)  # сведения для UI/логов о ходе DnD

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_tree_widget()
        self.move_operations_handler = MoveOperationsHandler(self)
        self.drag_drop_handler = DragDropHandler(self)

    # --- Emit helpers for handlers/внутренних методов ---
    def emit_items_moved(self, payload):
        """Эмитит сигнал о перемещении элементов (используется хендлерами)."""
        try:
            self.itemsMoved.emit(payload)
        except Exception as exc:
            # Без жестких зависимостей: просто даем обратную связь через сигнал dragFeedback
            self.dragFeedback.emit(
                {"type": "emit_error", "signal": "itemsMoved", "error": str(exc)}
            )

    def emit_invalid_drop(self, reason: str):
        """Эмитит сигнал о недопустимой операции drop (используется хендлерами)."""
        try:
            self.invalidDrop.emit(reason)
        except Exception as exc:
            self.dragFeedback.emit(
                {"type": "emit_error", "signal": "invalidDrop", "error": str(exc)}
            )

    def emit_drag_feedback(self, info):
        """Эмитит произвольные сведения о ходе DnD (лог/диагностика/UI)."""
        try:
            self.dragFeedback.emit(info)
        except Exception:
            pass

    def _setup_tree_widget(self):
        """Настройка параметров дерева."""
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        # Явно применяем высоту строк из конфигурации через делегат (используем ui.row_height)
        try:
            item_h = int(app_config.get_row_height())
        except Exception:
            item_h = None
        self.setItemDelegate(HighQualityTreeDelegate(item_height=item_h))
        # Для производительности и единообразия высоты
        try:
            self.setUniformRowHeights(True)
        except Exception:
            pass
        # Включаем отслеживание мыши, чтобы работал hover без нажатий
        self.setMouseTracking(True)
        # Убираем специальные hover-обработчики (возврат к стандартному поведению)

    def update_font_size(self, font_size: int):
        """Применяет локальный размер шрифта ко всем элементам дерева."""
        from PyQt6.QtGui import QFont

        font = QFont(self.font().family(), font_size)
        self.setFont(font)

        def apply_font(item):
            item.setFont(0, font)
            for i in range(item.childCount()):
                apply_font(item.child(i))

        for i in range(self.topLevelItemCount()):
            apply_font(self.topLevelItem(i))
        self.viewport().update()

    def dragEnterEvent(self, event):
        """Обработка входа drag операции."""
        self.drag_drop_handler.handle_drag_enter_event(event)

    def dragMoveEvent(self, event):
        """Визуальная обратная связь во время перетаскивания."""
        self.drag_drop_handler.handle_drag_move_event(event)

    def dragLeaveEvent(self, event):
        """Обработка выхода из drag зоны."""
        self.drag_drop_handler.handle_drag_leave_event(event)

    def dropEvent(self, event):
        """Основной обработчик drop событий."""
        self.drag_drop_handler.handle_drop_event(event)
