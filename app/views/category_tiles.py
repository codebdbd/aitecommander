# app/views/category_tiles.py

"""Простые плитки категорий с иконками и контекстным меню."""

import logging

from PyQt6.QtCore import QPoint, QPointF, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QDrag, QFont, QFontMetrics, QIcon, QPen, QColor, QTextLayout, QTextOption
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
    QLabel,
    QToolTip,
    QMenu,
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
        # Диагностика: логируем фактический размер шрифта один раз
        self._font_diag_logged = False


    def paint(self, painter, option, index):
        """Простая отрисовка плитки: иконка сверху, текст снизу."""
        painter.save()
        rect = option.rect
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        # Применяем размер шрифта из конфигурации (если указан)
        try:
            cfg_sz = app_config.get_tile_text_font_size()
            if isinstance(cfg_sz, (int, float)) and cfg_sz > 0:
                f = painter.font()
                # Используем point size, чтобы соответствовать глобальному стилю
                f.setPointSize(int(cfg_sz))
                painter.setFont(f)
        except (TypeError, ValueError, AttributeError) as e:
            logger.warning(f"Failed to set font size from config in paint: {e}")
        
        # Дать Qt/QSS нарисовать фон/рамку элемента (hover/selected) перед нашей отрисовкой
        try:
            from PyQt6.QtWidgets import QStyle
            w = option.widget
            style = w.style() if w is not None else None
            if style is not None:
                style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, w)
        except (AttributeError, RuntimeError) as e:
            logger.debug(f"Style primitive draw skipped: {e}")
        
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
            mid = option.palette.color(option.palette.ColorRole.Mid)
            dark = option.palette.color(option.palette.ColorRole.Dark)
            text_col = option.palette.color(option.palette.ColorRole.BrightText)
            painter.setBrush(QBrush(mid))
            painter.setPen(QPen(dark))
            painter.drawEllipse(icon_rect)
            # Отрисуем «?» в центре как индикатор отсутствующей иконки
            try:
                placeholder_font = QFont(painter.font())
                placeholder_font.setBold(True)
                # Подберём размер относительно иконки
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
                logger.debug(f"Placeholder '?' draw skipped: {e}")
        
        # Рисуем текст (перенос по словам, высота = по содержимому, но не более N строк из конфига)
        if text:
            # Диагностика фактического размера шрифта (однократно на сессию)
            try:
                if not self._font_diag_logged:
                    fm_diag = QFontMetrics(painter.font())
                    logger.info(
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
                logger.debug(f"Font diagnostics skipped: {e}")
            text_rect = QRect(
                rect.left() + self.padding,
                rect.top() + self.padding + self.icon_size.height() + 5,
                rect.width() - 2 * self.padding,
                # Высота под текст будет установлена по содержимому (wrap), ограничено N строками
                0
            )
            fm = QFontMetrics(painter.font())
            # Лэйаут: сначала по словам, при необходимости по буквам
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
                logger.debug(f"Invalid max_lines config, fallback to 3: {e}")
                max_lines = 3
            has_more = False
            # Оптимизированный цикл разметки строк: без фиксированного большого лимита
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(available_w)
                line.setPosition(QPointF(0.0, float(y)))
                lines.append(line)
                y += int(line.height())
                if len(lines) >= max_lines:
                    # Проверим, есть ли ещё строки сверх лимита
                    probe = layout.createLine()
                    has_more = probe.isValid()
                    # Обрезаем до max_lines, последнюю строку элидим при необходимости
                    break
            layout.endLayout()

            # Высота текстового блока
            text_rect.setHeight(y)

            # Цвет текста берём из палитры; QSS управляет фоном/рамкой
            painter.setPen(option.palette.color(option.palette.ColorRole.WindowText))

            # Отрисовка построчно по центру
            # Для последней строки применяем эллипсис, если есть больше строк
            for idx, line in enumerate(lines):
                line_text = text[line.textStart(): line.textStart() + line.textLength()]
                # Центрирование по горизонтали вручную
                natural_w = line.naturalTextWidth()
                draw_x = text_rect.x() + max(0, (available_w - int(natural_w)) // 2)
                draw_y = text_rect.y() + int(line.position().y()) + fm.ascent()
                if idx == len(lines) - 1 and has_more:
                    # Эллипсис для последней видимой строки. Гарантируем «…», даже если ширина позволяет исходный текст.
                    elided = fm.elidedText(line_text, Qt.TextElideMode.ElideRight, available_w)
                    if elided == line_text:
                        ellipsis = "…"
                        ell_w = fm.horizontalAdvance(ellipsis)
                        max_w = max(0, available_w - ell_w)
                        core = fm.elidedText(line_text, Qt.TextElideMode.ElideRight, max_w)
                        text_to_draw = (core if core else "") + ellipsis
                    else:
                        # elidedText уже добавил многоточие
                        text_to_draw = elided
                    # Пересчитаем центрирование по ширине нарисованной строки
                    draw_w = fm.horizontalAdvance(text_to_draw)
                    draw_x = text_rect.x() + max(0, (available_w - draw_w) // 2)
                    painter.drawText(QPoint(draw_x, draw_y), text_to_draw)
                else:
                    painter.drawText(QPoint(draw_x, draw_y), line_text)
        
        painter.restore()

    def sizeHint(self, option, index):
        """Простой расчет размера плитки."""
        # pylint: disable=unused-argument
        # Высота: padding + icon + 5 + высота текста по содержимому (wrap, но не более N строк) + padding
        # Используем шрифт из option, но применяем размер из конфигурации, если задан
        font = QFont(option.font)
        try:
            cfg_sz = app_config.get_tile_text_font_size()
            if isinstance(cfg_sz, (int, float)) and cfg_sz > 0:
                font.setPointSize(int(cfg_sz))
        except (TypeError, ValueError, AttributeError) as e:
            logger.warning(f"Failed to set font size from config in sizeHint: {e}")
        fm = QFontMetrics(font)
        try:
            max_lines = int(app_config.get_tile_text_max_lines())
        except (TypeError, ValueError, AttributeError) as e:
            logger.debug(f"Invalid max_lines config in sizeHint, fallback to 3: {e}")
            max_lines = 3
        # Получаем текст элемента
        try:
            text = index.data(Qt.ItemDataRole.DisplayRole)
        except (RuntimeError, AttributeError) as e:
            logger.debug(f"Failed to read DisplayRole in sizeHint: {e}")
            text = ""
        # Доступная ширина текста в плитке
        available_w = self.tile_size.width() - 2 * self.padding
        # Подсчёт высоты через QTextLayout с режимом WrapAtWordBoundaryOrAnywhere
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
        """Показывает тултип с полным названием ТОЛЬКО если текст усечён (за пределами max_lines).

        Имитация поведения Windows Explorer: после переноса и усечения многоточием
        показываем полный текст в подсказке.
        """
        try:
            if not index.isValid() or event is None:
                return False
            # Получаем исходный текст
            text = index.data(Qt.ItemDataRole.DisplayRole) or ""
            if not text:
                return super().helpEvent(event, view, option, index)

            # Вычисляем, был ли усечён текст (существуют строки за пределами лимита)
            try:
                max_lines = int(app_config.get_tile_text_max_lines())
            except (TypeError, ValueError, AttributeError) as e:
                logger.debug(f"Invalid max_lines config in helpEvent, fallback to 3: {e}")
                max_lines = 3

            # Доступная ширина для текста основывается на реальном rect элемента
            available_w = max(0, option.rect.width() - 2 * self.padding)

            # Применим шрифт с конфигурационным размером
            font = QFont(option.font)
            try:
                cfg_sz = app_config.get_tile_text_font_size()
                if isinstance(cfg_sz, (int, float)) and cfg_sz > 0:
                    font.setPointSize(int(cfg_sz))
            except (TypeError, ValueError, AttributeError) as e:
                logger.debug(f"Failed to set font size in helpEvent: {e}")

            layout = QTextLayout(text, font)
            opt = QTextOption()
            opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            opt.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            layout.setTextOption(opt)
            layout.beginLayout()
            lines_count = 0
            has_more = False
            any_line_overflow = False
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(available_w)
                # Если естественная ширина строки больше доступной — значит есть горизонтальное усечение
                if line.naturalTextWidth() > available_w:
                    any_line_overflow = True
                lines_count += 1
                if lines_count >= max_lines:
                    probe = layout.createLine()
                    has_more = probe.isValid()
                    break
            layout.endLayout()

            # Показываем тултип всегда для непустого текста.
            # Если текст усечён (has_more или any_line_overflow), поведение прежнее — показать полный текст.
            # Если не усечён — всё равно показываем тот же текст как подсказку для единообразия UX.
            QToolTip.showText(event.globalPos(), text, view)
            return True
        except (RuntimeError, AttributeError, ValueError) as e:
            # В случае сбоев логируем и не ломаем стандартное поведение
            logger.warning(f"helpEvent failed, using default tooltip handling: {e}")
            return super().helpEvent(event, view, option, index)

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
        except (AttributeError, RuntimeError) as e:
            logger.debug(f"Viewport hover setup skipped: {e}")
        # Простой делегат для отрисовки (нужен для параметров размеров)
        self.delegate = CategoryTileDelegate(parent=self)
        self.list_widget.setItemDelegate(self.delegate)

        # Разрешаем динамическую высоту элементов (sizeHint делегата)
        self.list_widget.setUniformItemSizes(False)
        try:
            self.list_widget.setWordWrap(True)
        except (AttributeError, RuntimeError) as e:
            logger.debug(f"WordWrap not supported on list widget: {e}")
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

        # Отладочная контрольная метка для визуального сравнения шрифта плиток (отображаем НАД списком)
        try:
            if getattr(app_config, 'get_debug_show_tile_font_sample', None) and app_config.get_debug_show_tile_font_sample():
                sample = QLabel("Sample: Абв ABC 123")
                # Не принуждаем размер — пусть наследует глобальный pt, чтобы сравнить визуально
                sample.setObjectName('tileFontSample')
                self.layout.addWidget(sample, 0)
                logger.info("CategoryTiles: debug font sample label added (inherits global font)")
        except (AttributeError, RuntimeError) as e:
            logger.debug(f"Debug font sample init skipped: {e}")

        # Список плиток занимает оставшееся пространство
        self.layout.addWidget(self.list_widget, 1)

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
            # Нормализуем и валидируем ID категории
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
                logger.warning(f"Skip category with invalid id '{raw_id}' and name '{name}'")
                continue
            
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
        # Синхронизируем глобальный UI-стейт, если поддерживается
        try:
            if self.ui_state_manager and hasattr(self.ui_state_manager, 'set_tiles_selection'):
                self.ui_state_manager.set_tiles_selection(item_id)
        except (RuntimeError, AttributeError) as e:
            logger.debug(f"Tiles selection sync failed: {e}")
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
            # Пытаемся лениво инициализировать билдер, если зависимости уже есть
            if self.structure_controller:
                try:
                    self._menu_builder = CategoryMenuBuilder(self.list_widget, self.dialog_provider)
                    logger.info("CategoryTiles: Lazy-initialized Menu builder in _show_context_menu")
                except (Exception,) as e:
                    logger.debug(f"Context menu builder init failed: {e}")
        if not self._menu_builder:
            # Фолбэк: показывать пустое/минимальное меню нецелесообразно — просто тихо выходим
            logger.warning("CategoryTiles: Context menu is unavailable (builder not ready yet)")
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
                # Оптимистично удаляем плитку сразу, чтобы правая панель обновилась мгновенно
                try:
                    self._remove_tile_by_id(category_id)
                except Exception:
                    pass
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

    def _remove_tile_by_id(self, category_id: int) -> None:
        """Удаляет плитку категории с указанным ID, если она существует (оптимистичное обновление UI)."""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == category_id:
                self.list_widget.takeItem(i)
                if self._current_item_id == category_id:
                    self._current_item_id = None
                    try:
                        if self.ui_state_manager and hasattr(self.ui_state_manager, 'clear_tiles_selection'):
                            self.ui_state_manager.clear_tiles_selection()
                    except Exception:
                        pass
                logger.debug(f"Optimistically removed category tile ID {category_id}")
                break
