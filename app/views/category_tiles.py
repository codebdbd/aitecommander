# app/views/category_tiles.py

"""Простые плитки категорий с иконками и контекстным меню."""

import logging

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QDrag, QFontMetrics, QIcon, QPen, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from app.config_data import app_config
from app.utils.ui.dnd.mime import MimeDataParser
from app.utils.ui.icon.cache_manager import get_cached_category_icon
from app.utils.ui.icon.path_service import resolve_category_icon_path
from app.utils.ui.menu_builders.category_menu_builder import CategoryMenuBuilder
from app.utils.ui.qt.roles import get_item_int

logger = logging.getLogger("category_tiles")


class _CategoryListWidget(QListWidget):
    """QListWidget with custom drag that serialises category id."""
    MIME_TYPE = app_config.get_category_mime_type()

    def startDrag(self, supportedActions):
        # pylint: disable=unused-argument
        item = self.currentItem()
        if not item:
            logger.debug("CategoryListWidget.startDrag: no current item")
            return
        cat_id = get_item_int(item)
        if cat_id is None:
            logger.debug("CategoryListWidget.startDrag: no category id")
            return
        
        logger.debug(f"CategoryListWidget.startDrag: starting drag for category {cat_id} ({item.text()})")
        drag = QDrag(self)
        # Централизованный JSON-only MIME
        mime = MimeDataParser.create_mime_data([int(cat_id)], self.MIME_TYPE)
        drag.setMimeData(mime)
        logger.debug(f"CategoryListWidget.startDrag: MIME type = {self.MIME_TYPE}, data = {cat_id}")
        
        # Разрешаем копирование/перемещение. Qt игнорирует, если цель не примет перетаскивание.
        result = drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        logger.debug(f"CategoryListWidget.startDrag: drag result = {result}")

    # Ensure we claim we can start drag when left button pressed
    def mouseMoveEvent(self, event):
        # Default implementation already triggers startDrag; keep behaviour
        super().mouseMoveEvent(event)


class CategoryTileDelegate(QStyledItemDelegate):
    """Простой делегат для отрисовки плиток категорий."""
    
    def __init__(self, icon_size=None, tile_size=None, parent=None):
        super().__init__(parent)
        self.icon_size = icon_size or QSize(48, 48)
        self.tile_size = tile_size or QSize(120, 100)
        self.padding = 8
        self.border_radius = 4


    def paint(self, painter, option, index):
        """Простая отрисовка плитки: иконка сверху, текст снизу."""
        painter.save()
        rect = option.rect
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        
        # Дать Qt/QSS нарисовать фон/рамку элемента (hover/selected) перед нашей отрисовкой
        try:
            from PyQt6.QtWidgets import QStyle
            w = option.widget
            style = w.style() if w is not None else None
            if style is not None:
                style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, w)
        except Exception:
            pass
        
        # Рисуем иконку
        icon_rect = QRect(
            rect.left() + (rect.width() - self.icon_size.width()) // 2,
            rect.top() + self.padding,
            self.icon_size.width(), self.icon_size.height()
        )
        
        if isinstance(icon, QIcon) and not icon.isNull():
            icon.paint(painter, icon_rect)
        else:
            # Placeholder для отсутствующей иконки
            painter.setBrush(QBrush(option.palette.color(option.palette.ColorRole.Mid)))
            painter.setPen(QPen(option.palette.color(option.palette.ColorRole.Dark)))
            painter.drawEllipse(icon_rect)
        
        # Рисуем текст (перенос по словам, высота = по содержимому, но не более N строк из конфига)
        if text:
            # Применяем размер шрифта из конфига (в пикселях)
            try:
                font = painter.font()
                font.setPixelSize(app_config.get_tile_text_font_size())
                painter.setFont(font)
            except Exception:
                pass
            text_rect = QRect(
                rect.left() + self.padding,
                rect.top() + self.padding + self.icon_size.height() + 5,
                rect.width() - 2 * self.padding,
                # Высота под текст будет установлена по содержимому (wrap), ограничено N строками
                0
            )
            fm = QFontMetrics(painter.font())
            # Перенос слов и выравнивание по центру, без эллипсиса
            flags = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap
            # Фактическая высота текста с переносом по доступной ширине
            br = fm.boundingRect(QRect(0, 0, text_rect.width(), 10_000), int(flags), text)
            try:
                max_lines = int(app_config.get_tile_text_max_lines())
            except Exception:
                max_lines = 3
            max_text_h = fm.lineSpacing() * max_lines
            text_rect.setHeight(min(br.height(), max_text_h))

            # Цвет текста берём из палитры; QSS управляет фоном/рамкой
            painter.setPen(option.palette.color(option.palette.ColorRole.WindowText))

            # Рисуем текст в рассчитанный rect
            painter.drawText(text_rect, flags, text)
        
        painter.restore()

    def sizeHint(self, option, index):
        """Простой расчет размера плитки."""
        # pylint: disable=unused-argument
        # Высота: padding + icon + 5 + высота текста по содержимому (wrap, но не более N строк) + padding
        # Используем тот же размер шрифта, что и в paint()
        try:
            font = option.font
            font.setPixelSize(app_config.get_tile_text_font_size())
        except Exception:
            font = option.font
        fm = QFontMetrics(font)
        try:
            max_lines = int(app_config.get_tile_text_max_lines())
        except Exception:
            max_lines = 3
        # Получаем текст элемента
        try:
            text = index.data(Qt.ItemDataRole.DisplayRole)
        except Exception:
            text = ""
        # Доступная ширина текста в плитке
        available_w = self.tile_size.width() - 2 * self.padding
        flags = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap
        br = fm.boundingRect(QRect(0, 0, available_w, 10_000), int(flags), text or "")
        text_h = min(br.height(), fm.lineSpacing() * max_lines)
        height = self.padding + self.icon_size.height() + 5 + text_h + self.padding
        return QSize(self.tile_size.width(), height)

class CategoryTiles(QWidget):
    # Единственный сигнал для выбора категории (остальные удалены в пользу прямой интеграции с командами)
    category_selected: pyqtSignal = pyqtSignal(int)  # int - ID выбранной категории

    def __init__(self, parent=None, structure_controller=None, ui_state_manager=None, dialog_provider=None):
        """Простой UI-компонент для отображения плиток категорий."""
        super().__init__(parent)
        
        # Текущий выбранный элемент
        self._current_item_id = None

        # Обязательные зависимости
        self.structure_controller = structure_controller
        self.ui_state_manager = ui_state_manager
        self.dialog_provider = dialog_provider

        # Основной layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Список плиток
        self.list_widget = _CategoryListWidget()
        self.list_widget.setObjectName('categoryTiles')
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        # Включаем hover-события: важно активировать на viewport
        self.list_widget.setMouseTracking(True)
        vp = self.list_widget.viewport()
        try:
            vp.setMouseTracking(True)
            vp.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        except Exception:
            pass
        # Простой делегат для отрисовки (нужен для параметров размеров)
        self.delegate = CategoryTileDelegate(parent=self)
        self.list_widget.setItemDelegate(self.delegate)

        # Разрешаем динамическую высоту элементов (sizeHint делегата)
        self.list_widget.setUniformItemSizes(False)
        try:
            self.list_widget.setWordWrap(True)
        except Exception:
            pass
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_widget.setSpacing(8)  # Простое значение по умолчанию

        # Drag & Drop
        self.list_widget.setDragEnabled(True)
        self.list_widget.setAcceptDrops(False)
        self.list_widget.setDropIndicatorShown(False)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        
        # События
        self.list_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._on_item_clicked)
        self.list_widget.itemClicked.connect(self._on_item_selected)
        self.list_widget.currentItemChanged.connect(self._on_item_selected)

        self.layout.addWidget(self.list_widget)

        # Контекстное меню через builder
        self._menu_builder = None  # Будет инициализирован при первом использовании
        self._menu = None
        self._add_action = None
        self._edit_action = None
        self._delete_action = None
        
    def set_categories(self, categories: list):
        """Простое обновление списка категорий."""
        logger.info(f"Loading {len(categories)} categories")
        
        self.list_widget.clear()
        
        for category in categories:
            name = category.get('name', '')
            icon_path = category.get('icon_path', '')
            category_id = category.get('id')
            
            # Получаем иконку через централизованную систему
            if icon_path:
                # Резолвим путь к иконке и получаем кэшированную иконку
                resolved_path = resolve_category_icon_path(icon_path)
                icon = get_cached_category_icon(resolved_path)
                logger.debug(f"Loading icon for category '{name}': {icon_path} -> {resolved_path}, isNull: {icon.isNull()}")
            else:
                icon = QIcon()
                logger.debug(f"No icon for category '{name}'")
            
            # Создаем элемент списка
            item = QListWidgetItem(icon, name)
            item.setData(Qt.ItemDataRole.UserRole, category_id)
            self.list_widget.addItem(item)



    def _on_item_selected(self, item, previous=None):
        """Обновляем текущий выбранный элемент при клике."""
        # pylint: disable=unused-argument
        if item is None:
            logger.debug("No item selected")
            # Используем инжектированный ui_state_manager
            if self.ui_state_manager:
                self.ui_state_manager.clear_tiles_selection()
            else:
                self._current_item_id = None
            return
        
        item_id = get_item_int(item)
        if item_id is None:
            logger.debug("No item_id found in item data")
            return
        
        # Обновляем текущий ID
        self._current_item_id = item_id
        logger.debug(f"Selected category tile ID {item_id} ({item.text()})")

    def _on_item_clicked(self, item):
        logger.debug(f"Category tile activated: {item.text()}")
        cat_id = get_item_int(item)
        if cat_id is not None:
            # Обновляем текущий выбранный элемент
            self._current_item_id = cat_id
            # Используем сигнал вместо прямого обращения к MainWindow
            self.category_selected.emit(cat_id)

    def set_menu_builder(self, menu_builder):
        """Устанавливает menu builder для контекстного меню."""
        self._menu_builder = menu_builder
    
    def inject_dependencies(self, structure_controller=None, ui_state_manager=None, dialog_provider=None):
        """Инжектирует зависимости после создания контроллеров."""
        if structure_controller:
            self.structure_controller = structure_controller
        if ui_state_manager:
            self.ui_state_manager = ui_state_manager
        if dialog_provider:
            self.dialog_provider = dialog_provider
            
        # Инициализируем menu builder если есть все зависимости
        if self.structure_controller and hasattr(self, 'list_widget'):
            from app.utils.ui.menu_builders.category_menu_builder import (
                CategoryMenuBuilder,
            )
            menu_builder = CategoryMenuBuilder(self.list_widget, dialog_provider)
            self.set_menu_builder(menu_builder)
            logger.info("CategoryTiles: Menu builder инициализирован после инъекции зависимостей")
    
    def _show_context_menu(self, pos: QPoint):
        """Показываем контекстное меню через CategoryMenuBuilder."""
        logger.debug(f"Context menu requested at position {pos}")
        
        if not self._menu_builder:
            logger.error("CategoryTiles: Menu builder not initialized. Dependencies not injected yet.")
            return
            
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

        # Обновляем текущий ID
        self._current_item_id = item_id
        logger.debug(f"Showing context menu for category {item_id} ({item.text()})")
        
        # Создаем унифицированное меню через builder (как в дереве структуры)
        menu, edit_action, delete_action, add_link_action = self._menu_builder.build(
            item_id,
            self._execute_edit_category,
            self._execute_delete_category,
            self._execute_add_link
        )
        
        # Сохраняем ссылки на действия
        self._menu = menu
        self._edit_action = edit_action
        self._delete_action = delete_action
        self._add_link_action = add_link_action
        
        # Показываем меню
        menu.popup(self.list_widget.mapToGlobal(pos))
        logger.debug(f"Context menu shown for category {item_id}")
    
    def select_category(self, category_id: int) -> None:
        """Выбрать категорию по ID."""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == category_id:
                self.list_widget.setCurrentItem(item)
                self._current_item_id = category_id
                self.list_widget.scrollToItem(item)
                logger.debug(f"Selected category tile ID {category_id}")
                return
        logger.debug(f"Could not find category tile ID {category_id}")
    
    def get_categories_count(self) -> int:
        """Получить общее количество категорий."""
        return self.list_widget.count()
    

    def _execute_edit_category(self, category_id: int):
        """Выполняет команду редактирования категории."""
        logger.debug(f"Executing edit category command for ID {category_id}")
        try:
            if self.structure_controller:
                self.structure_controller.handle_edit_category(category_id)
                logger.debug(f"Edit category command executed for ID {category_id}")
            else:
                logger.error("CategoryTiles: Structure controller not available")
        except Exception as exc:
            logger.error(f"CategoryTiles: Ошибка редактирования категории {category_id}: {exc}")
    
    def _execute_delete_category(self, category_id: int):
        """Выполняет команду удаления категории."""
        logger.debug(f"Executing delete category command for ID {category_id}")
        try:
            if self.structure_controller:
                self.structure_controller.handle_delete_category(category_id)
                logger.debug(f"Delete category command executed for ID {category_id}")
            else:
                logger.error("CategoryTiles: Structure controller not available")
        except Exception as exc:
            logger.error(f"CategoryTiles: Ошибка удаления категории {category_id}: {exc}")
    
    def _execute_add_link(self, category_id: int):
        """Выполняет команду добавления ссылки в категорию."""
        logger.debug(f"Executing add link command for category ID {category_id}")
        try:
            if self.dialog_provider:
                self.dialog_provider.show_link_dialog_for_category(category_id=category_id)
                logger.debug(f"Add link command executed for category ID {category_id}")
            else:
                logger.error("CategoryTiles: Dialog provider not available")
        except Exception as exc:
            logger.error(f"CategoryTiles: Ошибка добавления ссылки в категорию {category_id}: {exc}")
