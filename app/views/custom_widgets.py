from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
)

from app.config_data import app_config
from app.utils.ui.dnd.tree import DragDropHandler
from app.views.tree_components.move_operations_handler import MoveOperationsHandler
import logging

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
        except (TypeError, ValueError) as e:
            logging.warning("HighQualityTreeDelegate.__init__: invalid item_height=%r: %s", item_height, e)
            self._item_height = None
        # Кэш подготовленных пиксмапов: ключ = (icon_cache_key, width, height, dpr)
        # Это значительно снижает количество перерасчётов и аллокаций в paint()
        self._pixmap_cache: dict[tuple, QIcon] = {}

    def clear_cache(self):
        """Очистить кэш иконок (например, при смене параметров размера/масштаба)."""
        try:
            self._pixmap_cache.clear()
        except AttributeError as e:
            logging.warning("HighQualityTreeDelegate.clear_cache: cache attribute missing, recreating: %s", e)
            self._pixmap_cache = {}

    def set_item_height(self, item_height: int | None):
        """Установить новую высоту элемента и очистить кэш."""
        try:
            self._item_height = int(item_height) if item_height is not None else None
        except (TypeError, ValueError) as e:
            logging.warning("HighQualityTreeDelegate.set_item_height: invalid item_height=%r: %s", item_height, e)
            self._item_height = None
        self.clear_cache()

    def paint(self, painter, option, index):
        # Убираем рамку фокуса у элементов дерева
        option.state &= ~QStyle.StateFlag.State_HasFocus

        # Получаем иконку из модели
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QIcon) and not icon.isNull():
            # Если по какой-то причине QPainter не активен, не пытаемся рисовать
            if hasattr(painter, "isActive") and not painter.isActive():
                logging.error(
                    "HighQualityTreeDelegate.paint: painter is not active; index=%r", index
                )
                return
            # Вычисляем размер иконки
            icon_size = option.decorationSize
            if icon_size.width() <= 0 or icon_size.height() <= 0:
                icon_size = option.widget.iconSize() if option.widget else QSize(16, 16)

            # DPR устройства вывода
            device_pixel_ratio = 1.0
            # Предпочитаем DPR от виджета/экрана, чтобы не обращаться к painter.device()
            try:
                if option.widget is not None and hasattr(option.widget, "devicePixelRatioF"):
                    device_pixel_ratio = float(option.widget.devicePixelRatioF())
                elif hasattr(painter, "device") and painter.device() is not None and hasattr(painter.device(), "devicePixelRatio"):
                    device_pixel_ratio = float(painter.device().devicePixelRatio())
            except Exception as e:
                logging.warning("HighQualityTreeDelegate.paint: failed to get devicePixelRatio, fallback to 1.0: %s", e)

            # Ключ кэша: используем cacheKey() QIcon, размеры и DPR
            try:
                icon_key = icon.cacheKey()  # int
            except AttributeError as e:
                logging.warning("HighQualityTreeDelegate.paint: icon has no cacheKey(), using id(): %s", e)
                icon_key = id(icon)
            cache_key = (icon_key, icon_size.width(), icon_size.height(), float(device_pixel_ratio))

            cached_icon = self._pixmap_cache.get(cache_key)
            if cached_icon is None:
                # Создаем временную опцию с высококачественной иконкой
                temp_option = QStyleOptionViewItem(option)

                # Создаём исходный пиксмап с учётом DPR
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

                # Создаем QIcon на основе подготовленного пиксмапа и кладём в кэш
                high_quality_icon = QIcon()
                high_quality_icon.addPixmap(pixmap)
                self._pixmap_cache[cache_key] = high_quality_icon
                cached_icon = high_quality_icon

            # Рисуем стандартным способом с кэшированной иконкой
            temp_option = QStyleOptionViewItem(option)
            temp_option.icon = cached_icon
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
        except (AttributeError, TypeError, ValueError) as e:
            logging.warning("HighQualityTreeDelegate.sizeHint: using fallback height due to config error: %s", e)
            row_h = self._item_height if self._item_height else base.height()
        return QSize(base.width(), row_h)


class StructureTreeView(QTreeView):
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

    def update_font_size(self, font_size: int):
        """
        Явно применяет локальный размер шрифта к дереву структуры.
        Делает поведение согласованным с таблицей ссылок (LinksTableView.update_font_size).
        """
        try:
            # Ничего не делаем, если размер не менялся
            if hasattr(self, "_current_font_size") and self._current_font_size == int(font_size):
                return
            self._current_font_size = int(font_size)
        except Exception:
            # В случае некорректного значения просто выходим
            return

        try:
            from PyQt6.QtGui import QFont

            f = QFont(self.font().family(), int(self._current_font_size))
            self.setFont(f)
            # Обновляем отображение
            self.viewport().update()
        except Exception as e:
            logging.warning("StructureTreeView.update_font_size: failed to apply font size %r: %s", font_size, e)

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
        except (AttributeError, TypeError, ValueError) as e:
            logging.warning("StructureTreeView._setup_tree_view: invalid row_height in config, fallback to None: %s", e)
            item_h = None
        self.setItemDelegate(HighQualityTreeDelegate(item_height=item_h))

        # Производительность: одинаковая высота строк
        try:
            self.setUniformRowHeights(True)
        except AttributeError as e:
            logging.warning("StructureTreeView._setup_tree_view: setUniformRowHeights not available: %s", e)

        # Hover-поведение как в прежней версии
        self.setMouseTracking(True)

    # --- Emit helpers (совместимость с прежним API) ---
    def emit_items_moved(self, payload):
        try:
            self.itemsMoved.emit(payload)
        except (RuntimeError, TypeError, AttributeError) as e:
            logging.error("StructureTreeView.emit_items_moved: emit failed: payload=%r, error=%s", payload, e)
            # Без жестких зависимостей: даем обратную связь через dragFeedback
            try:
                self.dragFeedback.emit(
                    {"type": "emit_error", "signal": "itemsMoved", "error": str(e)}
                )
            except (RuntimeError, TypeError, AttributeError) as e2:
                logging.error("StructureTreeView.emit_items_moved: dragFeedback emit failed: %s", e2)

    def emit_invalid_drop(self, reason: str):
        try:
            self.invalidDrop.emit(reason)
        except (RuntimeError, TypeError, AttributeError) as e:
            logging.error("StructureTreeView.emit_invalid_drop: emit failed: reason=%r, error=%s", reason, e)
            try:
                self.dragFeedback.emit(
                    {"type": "emit_error", "signal": "invalidDrop", "error": reason}
                )
            except (RuntimeError, TypeError, AttributeError) as e2:
                logging.error("StructureTreeView.emit_invalid_drop: dragFeedback emit failed: %s", e2)

    def emit_drag_feedback(self, info):
        try:
            self.dragFeedback.emit(info)
        except (RuntimeError, TypeError, AttributeError) as e:
            logging.error("StructureTreeView.emit_drag_feedback: emit failed: info=%r, error=%s", info, e)

    # --- DnD события: сначала собственный обработчик, затем (при необходимости) стандартная обработка ---
    # Подход сочетает кастомную логику (DragDropHandler) и базовое поведение Qt.
    # Если пользовательский обработчик НЕ принял событие (event.isAccepted() == False),
    # передаём его родительскому классу для стандартной обработки.
    def dragEnterEvent(self, event):
        self.drag_drop_handler.handle_drag_enter_event(event)
        if not event.isAccepted():
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        self.drag_drop_handler.handle_drag_move_event(event)
        if not event.isAccepted():
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self.drag_drop_handler.handle_drag_leave_event(event)
        if not event.isAccepted():
            super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.drag_drop_handler.handle_drop_event(event)
        if not event.isAccepted():
            super().dropEvent(event)
