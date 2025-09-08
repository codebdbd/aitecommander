# app/views/category_tiles.py

"""Простые плитки категорий с иконками.

Рефакторинг: Вид больше не создаёт/исполняет контекстное меню сам.
Вместо этого он генерирует сигналы, а контроллер показывает меню и
выполняет команды. Это снижает связность и устраняет утечки логики
в слой представления.
"""

import logging

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QCursor,
    QDrag,
    QFont,
    QFontMetrics,
    QIcon,
    QMouseEvent,
    QPen,
    QTextLayout,
    QTextOption,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QListView,
    QStyledItemDelegate,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.config_data import app_config
from app.models.categories_list_model import CategoriesListModel
from app.utils.ui.dnd.mime import MimeDataParser

logger = logging.getLogger("category_tiles")


class _CategoryListView(QListView):
    """QListView with custom drag that serialises category id from model UserRole."""

    MIME_TYPE = app_config.settings.get_category_mime_type()
    # Сигнал активации по клавише Enter/Return
    enterActivated = pyqtSignal(object)

    def mousePressEvent(self, event: QMouseEvent):
        # Гарантируем установку currentIndex по месту клика (для DnD и контекстного меню)
        try:
            p = event.position().toPoint()
            self._press_pos = p
            idx = self.indexAt(p)
            if idx.isValid():
                self.setCurrentIndex(idx)
                self.selectionModel().setCurrentIndex(
                    idx, QAbstractItemView.SelectionFlag.ClearAndSelect
                )
        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            logger.debug("CategoryListView.mousePressEvent: %s", e)
        except Exception:
            logger.exception("CategoryListView.mousePressEvent: unexpected error")
        super().mousePressEvent(event)

    def startDrag(self, supportedActions):
        index = self.currentIndex()
        if not index or not index.isValid():
            logger.debug("CategoryListView.startDrag: no current index")
            return
        cat_id = index.data(Qt.ItemDataRole.UserRole)
        if cat_id is None:
            logger.debug("CategoryListView.startDrag: no category id in UserRole")
            return

        name = index.data(Qt.ItemDataRole.DisplayRole)
        logger.debug(
            "CategoryListView.startDrag: starting drag for category %s (%s)",
            cat_id,
            name,
        )
        drag = QDrag(self)
        mime = MimeDataParser.create_mime_data([int(cat_id)], self.MIME_TYPE)
        drag.setMimeData(mime)
        logger.debug(
            "CategoryListView.startDrag: MIME type = %s, data = %s",
            self.MIME_TYPE,
            cat_id,
        )

        result = drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        logger.debug("CategoryListView.startDrag: drag result = %s", result)

    def mouseMoveEvent(self, event):
        # Явный запуск DnD при достаточном смещении курсора
        try:
            if event.buttons() & Qt.MouseButton.LeftButton:
                idx = self.currentIndex()
                if idx.isValid():
                    # Порог из системных настроек
                    threshold = QApplication.startDragDistance()
                    start = getattr(self, "_press_pos", event.position().toPoint())
                    if (event.position().toPoint() - start).manhattanLength() >= threshold:
                        self.startDrag(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
                        return
        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            logger.debug("CategoryListView.mouseMoveEvent: %s", e)
        except Exception:
            logger.exception("CategoryListView.mouseMoveEvent: unexpected error")
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        # Активация плитки по Enter/Return
        try:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                idx = self.currentIndex()
                if idx and idx.isValid():
                    try:
                        self.enterActivated.emit(idx)
                    except (RuntimeError, AttributeError) as e:
                        logger.warning("CategoryListView.keyPressEvent: failed to emit enterActivated: %s", e)
                    except Exception:
                        logger.exception("CategoryListView.keyPressEvent: unexpected error on emit")
                    event.accept()
                    return
        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            logger.debug("CategoryListView.keyPressEvent: %s", e)
        except Exception:
            logger.exception("CategoryListView.keyPressEvent: unexpected error")
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        # Всегда устанавливаем текущий индекс по правому клику и прокидываем сигнал
        try:
            idx = self.indexAt(event.pos())
            if idx.isValid():
                self.setCurrentIndex(idx)
                self.selectionModel().setCurrentIndex(
                    idx, QAbstractItemView.SelectionFlag.ClearAndSelect
                )
        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            logger.debug("CategoryListView.contextMenuEvent: %s", e)
        except Exception:
            logger.exception("CategoryListView.contextMenuEvent: unexpected error while setting current index")
        try:
            self.customContextMenuRequested.emit(event.pos())
            event.accept()
            return
        except (RuntimeError, AttributeError) as e:
            logger.warning("CategoryListView.contextMenuEvent: failed to emit customContextMenuRequested: %s", e)
        except Exception:
            logger.exception("CategoryListView.contextMenuEvent: unexpected error on emit")
        super().contextMenuEvent(event)


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
            # Централизованный приоритет: если родительский виджет передал явный pt, используем его
            explicit_pt = None
            try:
                parent = self.parent()
                explicit_pt = getattr(parent, "_font_point_size", None)
            except Exception:
                explicit_pt = None
            if isinstance(explicit_pt, (int, float)) and explicit_pt > 0:
                f = painter.font()
                f.setPointSize(int(explicit_pt))
                painter.setFont(f)
            else:
                # Fallback: берем из конфигурации, чтобы сохранить обратную совместимость
                cfg_sz = app_config.ui.get_tile_text_font_size()
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
                style.drawPrimitive(
                    QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, w
                )
        except (AttributeError, RuntimeError) as e:
            logger.debug("Style primitive draw skipped: %s", e)

        icon_rect = QRect(
            rect.left() + (rect.width() - self.icon_size.width()) // 2,
            rect.top() + self.padding,
            self.icon_size.width(),
            self.icon_size.height(),
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
                placeholder_font.setPointSize(
                    max(8, int(self.icon_size.height() * 0.45))
                )
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
                            app_config.ui.get_tile_text_font_size(),
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
                0,
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
                max_lines = int(app_config.ui.get_tile_text_max_lines())
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
                line_text = text[
                    line.textStart() : line.textStart() + line.textLength()
                ]
                natural_w = line.naturalTextWidth()
                draw_x = text_rect.x() + max(0, (available_w - int(natural_w)) // 2)
                draw_y = text_rect.y() + int(line.position().y()) + fm.ascent()
                if idx == len(lines) - 1 and has_more:
                    elided = fm.elidedText(
                        line_text, Qt.TextElideMode.ElideRight, available_w
                    )
                    if elided == line_text:
                        ellipsis = "…"
                        ell_w = fm.horizontalAdvance(ellipsis)
                        max_w = max(0, available_w - ell_w)
                        core = fm.elidedText(
                            line_text, Qt.TextElideMode.ElideRight, max_w
                        )
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
            # Централизованный приоритет: использовать явный размер от родителя
            explicit_pt = None
            try:
                parent = self.parent()
                explicit_pt = getattr(parent, "_font_point_size", None)
            except Exception:
                explicit_pt = None
            if isinstance(explicit_pt, (int, float)) and explicit_pt > 0:
                font.setPointSize(int(explicit_pt))
            else:
                cfg_sz = app_config.ui.get_tile_text_font_size()
                if isinstance(cfg_sz, (int, float)) and cfg_sz > 0:
                    font.setPointSize(int(cfg_sz))
        except (TypeError, ValueError, AttributeError) as e:
            logger.debug("Failed to set font size from config in sizeHint: %s", e)
        try:
            max_lines = int(app_config.ui.get_tile_text_max_lines())
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
                max_lines = int(app_config.ui.get_tile_text_max_lines())
            except (TypeError, ValueError, AttributeError) as e:
                logger.debug(
                    "Invalid max_lines config in helpEvent, fallback to 3: %s", e
                )
                max_lines = 3

            available_w = max(0, option.rect.width() - 2 * self.padding)

            font = QFont(option.font)
            try:
                explicit_pt = None
                try:
                    parent = self.parent()
                    explicit_pt = getattr(parent, "_font_point_size", None)
                except Exception:
                    explicit_pt = None
                if isinstance(explicit_pt, (int, float)) and explicit_pt > 0:
                    font.setPointSize(int(explicit_pt))
                else:
                    cfg_sz = app_config.ui.get_tile_text_font_size()
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

    def __init__(
        self,
        parent=None,
        structure_controller=None,
        ui_state_manager=None,
        dialog_provider=None,
    ):
        """Простой UI-компонент для отображения плиток категорий."""
        super().__init__(parent)

        self._current_item_id = None

        self.structure_controller = structure_controller
        self.ui_state_manager = ui_state_manager
        self.dialog_provider = dialog_provider

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.view = _CategoryListView()
        self.view.setObjectName("categoryTiles")
        self.view.setViewMode(QListView.ViewMode.IconMode)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setMovement(QListView.Movement.Static)
        self.view.setMouseTracking(True)
        vp = self.view.viewport()
        try:
            vp.setMouseTracking(True)
            vp.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        except (AttributeError, RuntimeError) as e:
            logger.debug("Viewport hover setup skipped: %s", e)
        # Перехват контекстного меню даже если оно блокируется родителями/стилями
        try:
            vp.installEventFilter(self)
        except Exception as e:
            logger.debug("Failed to install event filter on viewport: %s", e)
        self.delegate = CategoryTileDelegate(parent=self)
        self.view.setItemDelegate(self.delegate)

        self.view.setUniformItemSizes(False)
        try:
            self.view.setWordWrap(True)
        except (AttributeError, RuntimeError) as e:
            logger.debug("WordWrap not supported on list widget: %s", e)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setSpacing(8)

        self.view.setDragEnabled(True)
        self.view.setAcceptDrops(False)
        self.view.setDropIndicatorShown(False)
        self.view.setDefaultDropAction(Qt.DropAction.MoveAction)

        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # Контекстное меню: обрабатываем и сигнал от view, и от viewport
        # a) от view — координаты в системе view
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._show_context_menu)
        # b) от viewport — координаты в системе viewport
        vp = self.view.viewport()
        vp.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        vp.customContextMenuRequested.connect(self._show_context_menu)
        # Открываем категорию ТОЛЬКО по двойному клику или Enter
        try:
            self.view.doubleClicked.connect(self._on_index_activated)
        except Exception:
            pass
        try:
            self.view.enterActivated.connect(self._on_index_activated)
        except Exception:
            pass

        self.layout.addWidget(self.view, 1)
        # Явно включаем режим только перетаскивания (DragOnly) для стабильной работы DnD
        try:
            self.view.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        except Exception as e:
            logger.debug("Failed to set DragOnly mode: %s", e)

        # Контекстное меню строит контроллер — вид только генерирует сигнал

    def update_font_size(self, fs: int) -> None:
        """Применяет централизованный размер шрифта к плиткам категорий.

        Если передан невалидный размер — сбрасывает в None (делегат возьмёт конфиг/глобальный).
        """
        try:
            if isinstance(fs, bool):
                return
            val = int(fs)
            if val > 0:
                self._font_point_size = val
            else:
                self._font_point_size = None
        except Exception:
            self._font_point_size = None
        # Перерисовать и обновить расчёты размеров
        try:
            self.view.viewport().update()
            self.view.reset()  # пересчитать sizeHint через делегат
        except Exception:
            pass

    def set_categories(self, categories: list):
        """Обновление списка категорий через модель."""
        logger.debug("Loading %d categories", len(categories))
        model = getattr(self, "_model", None)
        if model is None:
            model = CategoriesListModel(categories)
            self._model = model
            self.view.setModel(model)
        else:
            model.set_categories(categories)

    def _on_index_activated(self, index):
        if not index or not index.isValid():
            logger.debug("No index selected")
            self._current_item_id = None
            return
        cat_id = index.data(Qt.ItemDataRole.UserRole)
        name = index.data(Qt.ItemDataRole.DisplayRole)
        if cat_id is None:
            logger.debug("No category id in UserRole for index")
            return
        self._current_item_id = int(cat_id)
        logger.debug("Selected category tile ID %s (%s)", cat_id, name)
        # Эмитим сигнал на активацию (клик/даблклик)
        try:
            self.category_selected.emit(int(cat_id))
        except Exception as e:
            logger.warning("Failed to emit category_selected: %s", e)

    def inject_dependencies(
        self, structure_controller=None, ui_state_manager=None, dialog_provider=None
    ):
        """Инжектирует зависимости после создания контроллеров."""
        if structure_controller:
            self.structure_controller = structure_controller
        if ui_state_manager:
            self.ui_state_manager = ui_state_manager
        if dialog_provider:
            self.dialog_provider = dialog_provider

    def eventFilter(self, obj, event):
        # Гарантированный перехват QContextMenuEvent из viewport()
        try:
            if obj is self.view.viewport() and event.type() == QEvent.Type.ContextMenu:
                pos = event.pos()
                logger.debug("Viewport eventFilter: ContextMenu at %s", pos)
                self._show_context_menu(pos)
                event.accept()
                return True
        except Exception as e:
            logger.debug("eventFilter failed: %s", e)
        return super().eventFilter(obj, event)

    def _show_context_menu(self, pos: QPoint):
        """Запрашивает показ контекстного меню через контроллер (сигнал)."""
        logger.debug("Context menu requested at position %s", pos)
        index = self.view.indexAt(pos)
        source = "viewport"
        if not index.isValid():
            # Возможно, pos пришёл в координатах view — конвертируем
            vpos = self.view.viewport().mapFrom(self.view, pos)
            index = self.view.indexAt(vpos)
            source = "view"
        if not index.isValid():
            # Fallback: берём позицию курсора и маппим в viewport
            try:
                gpos = QCursor.pos()
                vpos2 = self.view.viewport().mapFromGlobal(gpos)
                index = self.view.indexAt(vpos2)
                source = "cursor"
            except Exception:
                pass
        if not index.isValid():
            logger.debug("Invalid index at position")
            return

        item_id = index.data(Qt.ItemDataRole.UserRole)
        if item_id is None:
            logger.debug("No item_id found in UserRole")
            return

        self._current_item_id = int(item_id)
        logger.debug(
            "Emitting contextMenuRequested for category %s (%s)",
            item_id,
            index.data(Qt.ItemDataRole.DisplayRole),
        )
        # Определяем глобальные координаты показа
        if source == "viewport":
            global_pos = self.view.viewport().mapToGlobal(pos)
        elif source == "view":
            global_pos = self.view.mapToGlobal(pos)
        else:
            global_pos = QCursor.pos()

        # Чисто сигнальный путь: внешний контроллер строит меню
        try:
            self.contextMenuRequested.emit(int(item_id), global_pos)
        except Exception as e:
            logger.warning("Failed to emit contextMenuRequested: %s", e)

    def select_category(self, category_id: int) -> None:
        """Выбрать категорию по ID."""
        model = getattr(self, "_model", None)
        if not model:
            logger.debug("Model is not set; cannot select category")
            return
        row = model.find_row_by_id(category_id)
        if row >= 0:
            idx = model.index(row, 0)
            self.view.setCurrentIndex(idx)
            self._current_item_id = category_id
            self.view.scrollTo(idx)
            logger.debug("Selected category tile ID %s", category_id)
            return
        logger.debug("Could not find category tile ID %s", category_id)

    def get_categories_count(self) -> int:
        """Получить общее количество категорий."""
        model = getattr(self, "_model", None)
        return int(model.rowCount()) if model else 0

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
