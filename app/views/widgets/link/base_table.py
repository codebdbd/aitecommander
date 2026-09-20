# Core module for the links table
# Contains the main ``LinksTableView`` class and foundational functionality

import logging

from PyQt6.QtCore import (
    QEvent,
    QModelIndex,
    QPointF,
    QRect,
    QSize,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QKeyEvent,
    QPainter,
    QPalette,
    QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QProxyStyle,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionHeader,
    QStyleOptionViewItem,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.services.theme_registry import theme_registry
from app.utils.ui.dnd.link import DragDropHandlerMixin
from app.utils.ui.dnd.mime import get_link_mime
from app.utils.ui.icon.path_service import get_current_theme
from app.views.widgets.base.base_widgets import BaseDragDropTableWidget
from app.views.widgets.link.links_model import HEADER_CHEVRON_PADDING_ROLE, LinksTableModel
from i18n.language_service import LanguageService

from .data_management import DataManagementMixin

# Import all mixins
from .item_builders import ItemBuildersMixin
from .population_manager import PopulationManagerMixin
from .row_operations import RowOperationsMixin

# Module-level logger
logger = logging.getLogger(__name__)


def _header_text_width(header: QHeaderView, text: str, *, min_width: int) -> int:
    """Return a header column width that leaves room for text and sort toggle."""
    try:
        text_width = header.fontMetrics().horizontalAdvance(str(text))
        return max(min_width, text_width + 40)
    except Exception:
        return min_width


class TableDelegate(QStyledItemDelegate):
    """Unified delegate: row hover highlight and character-based elision for the ``Name`` column."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rebuild_in_progress = False
        self.hovered_row = -1
        # Unified hover color across themes (Win11 accent blue @30% alpha)
        self.hover_color = QColor(0, 120, 212, 77)

        # Font size settings pulled from the centralized ``ui.fonts.*`` registry
        def _get_px(key: str) -> int | None:
            try:
                v = app_config.ui.get(f"ui.fonts.{key}")
                return int(v) if v is not None else None
            except Exception:
                return None

        # Font units: ``px`` or ``pt``
        try:
            self._font_units = (
                str(app_config.ui.get("ui.fonts.units", "px")).strip().lower()
            )
        except Exception:
            self._font_units = "px"
        if self._font_units not in ("px", "pt"):
            self._font_units = "px"

        # Individual column sizes (backward compatibility)
        self.col_opened_px = _get_px("table_opened_col_px")  # "Launch" column (index=3)
        self.col_notes_px = _get_px("table_notes_col_px")  # "Notes" column (index=4)

        # Modern approach: array of sizes for all columns
        self.col_sizes: dict[int, int] = {}
        try:
            arr = app_config.ui.get(
                "ui.fonts.table_cols_px"
            )  # expected to be a list of numbers or None
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

    def update_column_sizes(self, font_size: int):
        """Update column font sizes based on new base font size.
        
        Scales all column sizes proportionally to the new font size.
        """
        try:
            # Update individual column sizes
            if self.col_opened_px:
                self.col_opened_px = font_size
            if self.col_notes_px:
                self.col_notes_px = font_size
            
            # Update column sizes dict
            for col in self.col_sizes:
                self.col_sizes[col] = font_size
                
        except Exception as e:
            logger.debug("TableDelegate.update_column_sizes failed: %s", e)

    def _paint_hover_highlight(self, painter, option, index):
        """Paint hover highlight for row."""
        is_hovered_row = self.hovered_row == index.row()
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if is_hovered_row and not is_selected:
            view = self.parent() if hasattr(self, "parent") else None
            hover_color = getattr(view, "hoverRowColor", self.hover_color)
            if not isinstance(hover_color, QColor) or not hover_color.isValid():
                hover_color = self.hover_color
            painter.save()
            painter.fillRect(option.rect, hover_color)
            painter.restore()

    def _apply_column_font_size(self, opt, col):
        """Apply font size for specific column."""
        try:
            if col == 0:
                return

            val = self.col_sizes.get(col)
            if val is None:
                if col == 3:
                    val = self.col_opened_px
                elif col == 4:
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

    def _apply_column_color(self, opt, col, color_attr):
        """Apply text color for specific column."""
        try:
            view = self.parent() if hasattr(self, "parent") else None
            color = None
            if view is not None and hasattr(view, color_attr):
                color = getattr(view, color_attr)
            if isinstance(color, QColor) and color.isValid():
                pal = QPalette(opt.palette)
                pal.setColor(QPalette.ColorRole.Text, color)
                pal.setColor(QPalette.ColorRole.WindowText, color)
                opt.palette = pal
        except Exception:
            pass

    def _apply_name_column_elision(self, opt):
        """Apply text elision for name column."""
        opt.textElideMode = Qt.TextElideMode.ElideRight
        try:
            icon_w = opt.decorationSize.width() + 8 if not opt.icon.isNull() else 0
            available_w = max(0, opt.rect.width() - icon_w - 4)
        except Exception:
            available_w = opt.rect.width()
        opt.text = opt.fontMetrics.elidedText(
            opt.text, Qt.TextElideMode.ElideRight, available_w
        )
        opt.displayAlignment = (
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        super().initStyleOption(option, index)
        if index.column() == 0:
            option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator

    def paint(self, painter, option, index):
        self._paint_hover_highlight(painter, option, index)

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        col = index.column()
        self._apply_column_font_size(opt, col)

        if col == 3:
            self._apply_column_color(opt, col, "openedColColor")
        elif col == 4:
            self._apply_column_color(opt, col, "notesColColor")

        if col == 1:
            self._apply_name_column_elision(opt)

        super().paint(painter, opt, index)

        if col == 0:
            widget = option.widget
            style = widget.style() if widget else QApplication.style()
            check_opt = QStyleOptionViewItem(option)
            super().initStyleOption(check_opt, index)

            state = index.data(Qt.ItemDataRole.CheckStateRole)
            check_opt.state = check_opt.state & ~QStyle.StateFlag.State_HasFocus
            if state in (Qt.CheckState.Checked.value, Qt.CheckState.Checked):
                check_opt.state |= QStyle.StateFlag.State_On
                check_opt.state &= ~QStyle.StateFlag.State_Off
            else:
                check_opt.state |= QStyle.StateFlag.State_Off
                check_opt.state &= ~QStyle.StateFlag.State_On

            check_rect = style.subElementRect(
                QStyle.SubElement.SE_ItemViewItemCheckIndicator, check_opt, widget
            )
            w = check_rect.width()
            h = check_rect.height()
            x = option.rect.x() + (option.rect.width() - w) // 2
            y = option.rect.y() + (option.rect.height() - h) // 2
            check_opt.rect = QRect(x, y, w, h)

            style.drawPrimitive(
                QStyle.PrimitiveElement.PE_IndicatorItemViewItemCheck,
                check_opt,
                painter,
                widget,
            )

    def editorEvent(self, event, model, option, index):
        if index.column() == 0:
            if (
                event.type() == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
            ):
                current_state = index.data(Qt.ItemDataRole.CheckStateRole)
                new_state = (
                    Qt.CheckState.Unchecked
                    if current_state in (Qt.CheckState.Checked.value, Qt.CheckState.Checked)
                    else Qt.CheckState.Checked
                )
                model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
                return True
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                return True
        # Top-left corner borders (cell above row 1 and before column 0)
        # are rendered via QSS (`QTableView QTableCornerButton::section`) in `dark.qss`
        return super().editorEvent(event, model, option, index)

class ExplorerHeaderStyle(QProxyStyle):
    """Proxy style that narrows label geometry for header sections with a
    right-hand sort-chevron compartment.

    The style itself has zero knowledge about concrete column indexes. Instead,
    it asks the attached model via ``HEADER_CHEVRON_PADDING_ROLE`` whether a
    given section needs symmetric label padding. Padding width is read from
    the owning ``ExplorerHeaderView.CHEVRON_COMPARTMENT_WIDTH`` class-level
    constant, so it stays single source of truth for both the chevron painter
    and the label-layout engine.
    """

    def __init__(self, header: "ExplorerHeaderView", base_style: QStyle | None = None):
        super().__init__(base_style)
        self._header = header

    def subElementRect(
        self, element: QStyle.SubElement, opt: QStyleOptionHeader, widget=None
    ) -> QRect:
        rect = super().subElementRect(element, opt, widget)
        if element != QStyle.SubElement.SE_HeaderLabel:
            return rect
        section = getattr(opt, "section", -1)
        header = self._header
        model = header.model() if header is not None else None
        if model is None:
            return rect
        try:
            needs_padding = bool(
                model.headerData(
                    section,
                    Qt.Orientation.Horizontal,
                    HEADER_CHEVRON_PADDING_ROLE,
                )
            )
        except Exception:
            needs_padding = False
        if needs_padding:
            try:
                px = int(header.CHEVRON_COMPARTMENT_WIDTH)
            except Exception:
                px = 24
            rect = rect.adjusted(px, 0, -px, 0)
        return rect


class ExplorerHeaderView(QHeaderView):
    """Header view with Windows Explorer style split-button sort toggles."""

    CHEVRON_COMPARTMENT_WIDTH = 24

    def __init__(self, orientation: Qt.Orientation, parent=None):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self.setSectionsClickable(True)
        self._hovered_section = -1
        self._hovered_toggle = False
        try:
            self.setStyle(ExplorerHeaderStyle(self, self.style()))
        except Exception:
            pass

    @staticmethod
    def _get_icon_colors() -> tuple[QColor, QColor]:
        try:
            cur_theme = get_current_theme()
            normal_hex = theme_registry.get_theme_icon_color(cur_theme)
            normal = QColor(normal_hex)
        except Exception:
            pal = QApplication.instance().palette() if QApplication.instance() else None
            if pal is None:
                return QColor("#FFFFFF"), QColor("#FFFFFF")
            normal = pal.windowText().color()
        hover = QColor(normal)
        hover.setAlpha(255)
        return normal, hover

    def changeEvent(self, event):
        t = event.type() if event is not None else None
        if t in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange, QEvent.Type.FontChange):
            self.viewport().update()
        super().changeEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        sec = self.logicalIndexAt(pos)
        on_toggle = bool(sec >= 0 and sec != 0)
        if sec != self._hovered_section or on_toggle != self._hovered_toggle:
            self._hovered_section = sec
            self._hovered_toggle = on_toggle
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hovered_section = -1
        self._hovered_toggle = False
        self.viewport().update()
        super().leaveEvent(event)

    def paintSection(self, painter, rect, logicalIndex):
        if logicalIndex == 0:
            opt = QStyleOptionHeader()
            self.initStyleOption(opt)
            opt.rect = rect
            opt.section = logicalIndex
            opt.text = ""
            opt.icon = QIcon()
            self.style().drawControl(QStyle.ControlElement.CE_Header, opt, painter, self)
            model = self.model()
            if model is not None:
                icon = model.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.DecorationRole)
                if isinstance(icon, QIcon) and not icon.isNull():
                    sz = 20
                    ix = rect.x() + (rect.width() - sz) // 2
                    iy = rect.y() + (rect.height() - sz) // 2
                    icon.paint(painter, ix, iy, sz, sz, Qt.AlignmentFlag.AlignCenter)
            return

        super().paintSection(painter, rect, logicalIndex)

    def paintEvent(self, event):
        super().paintEvent(event)
        is_sorted = self.sortIndicatorSection() >= 0
        sorted_sec = self.sortIndicatorSection() if is_sorted else -1
        hovered_sec = self._hovered_section
        if hovered_sec <= 0:
            return
        pal = self.palette()

        parent_table = self.parent()
        table_hover_color: QColor | None = None
        try:
            if hasattr(parent_table, "property"):
                v = parent_table.property("hoverRowColor")
                if isinstance(v, QColor) and v.isValid():
                    table_hover_color = QColor(v)
                    table_hover_color.setAlpha(70)
        except Exception:
            table_hover_color = None
        if table_hover_color is None:
            hc = pal.color(QPalette.ColorRole.Highlight)
            hc.setAlpha(40)
            table_hover_color = hc

        bg = pal.window().color()
        separator_color = pal.color(QPalette.ColorRole.Dark)
        if not separator_color.isValid() or separator_color.rgb() == 0xFF000000:
            separator_color = bg.lighter(150) if bg.lightness() < 128 else bg.darker(150)

        sec = hovered_sec
        sec_x = self.sectionViewportPosition(sec)
        sec_w = self.sectionSize(sec)
        toggle_w = self.CHEVRON_COMPARTMENT_WIDTH
        min_w = 3 * toggle_w
        if sec_w < min_w:
            return
        h = self.viewport().height()
        sorted_here = is_sorted and sec == sorted_sec

        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        p.fillRect(QRect(sec_x, 0, sec_w, h), table_hover_color)

        tx = sec_x + sec_w - toggle_w
        separator_pen = QPen(separator_color, 1)
        separator_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(separator_pen)
        p.drawLine(QPointF(tx, 2), QPointF(tx, h - 2))

        icon_normal, icon_hover = self._get_icon_colors()
        chev_color = icon_hover
        pen = QPen(chev_color, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        cx = tx + toggle_w / 2.0
        cy = h / 2.0 + 1.0
        if sorted_here and self.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder:
            pts = [QPointF(cx - 4, cy + 2), QPointF(cx, cy - 2), QPointF(cx + 4, cy + 2)]
        else:
            pts = [QPointF(cx - 4, cy - 2), QPointF(cx, cy + 2), QPointF(cx + 4, cy - 2)]
        p.drawPolyline(QPolygonF(pts))
        p.end()


class LinksTableView(
    BaseDragDropTableWidget,
    ItemBuildersMixin,
    DataManagementMixin,
    RowOperationsMixin,
    PopulationManagerMixin,
    DragDropHandlerMixin,
):
    """Primary links table view with modular architecture."""

    _sort_initialized: bool = False
    _allow_sort_persist: bool = False

    # qproperty: color for the "Opened" column (QSS: ``qproperty-openedColColor``)
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
            viewport = self.viewport()
            if viewport is not None:
                viewport.update()
        except Exception:
            pass

    openedColColor = pyqtProperty(
        QColor, fget=_get_opened_col_color, fset=_set_opened_col_color
    )

    # qproperty: color for the "Notes" column (QSS: ``qproperty-notesColColor``)
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
            viewport = self.viewport()
            if viewport is not None:
                viewport.update()
        except Exception:
            pass

    notesColColor = pyqtProperty(
        QColor, fget=_get_notes_col_color, fset=_set_notes_col_color
    )

    # qproperty: full-row hover color (QSS: ``qproperty-hoverRowColor``)
    def _get_hover_row_color(self) -> QColor:
        try:
            return getattr(self, "_hover_row_color", QColor())
        except Exception:
            return QColor()

    def _set_hover_row_color(self, value) -> None:
        try:
            if isinstance(value, QColor):
                self._hover_row_color = value
            else:
                self._hover_row_color = QColor(str(value))
            viewport = self.viewport()
            if viewport is not None:
                viewport.update()
        except Exception:
            pass

    hoverRowColor = pyqtProperty(
        QColor, fget=_get_hover_row_color, fset=_set_hover_row_color
    )

    # Signal emitted after bulk population/update of the table
    table_populated: pyqtSignal = pyqtSignal()
    externalLinkDropped: pyqtSignal = pyqtSignal(object)

    def update_font_size(self, font_size: int):
        """Apply the local font size to every table cell."""
        # Check whether the font size actually changed
        if hasattr(self, "_current_font_size") and getattr(self, "_current_font_size", None) == font_size:
            return

        self._current_font_size = font_size

        # Create a new font instance and apply it to the table

        font = QFont(self.font().family(), font_size)
        self.setFont(font)
        
        # Update delegate column sizes to match new font size
        delegate = self.itemDelegate()
        if delegate and hasattr(delegate, 'update_column_sizes'):
            try:
                delegate.update_column_sizes(font_size)
            except Exception as e:
                logger.debug("Failed to update delegate column sizes: %s", e)

        # Refresh the viewport
        viewport = self.viewport()
        if viewport is not None:
            viewport.update()

    # Override base-class constants (align with centralized helpers)
    MIME_TYPE = get_link_mime()

    # Rename signal for compatibility
    links_reordered: pyqtSignal = pyqtSignal(
        list
    )  # List[int] - link IDs in the new order
    quickLookRequested: pyqtSignal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = getattr(parent, "settings", None)
        # Object name used for QSS tweaks (e.g., header font size)
        try:
            self.setObjectName("linksTable")
        except Exception:
            pass
        self._current_links = {}  # Cache of current data: {row: link_data}
        self._current_mode = "normal"  # Active presentation mode
        self._rebuild_in_progress = False
        self._cleanup_done = False
        self._sort_initialized = False
        self._allow_sort_persist = False
        self._setup_table()

        # Forward base-class signal to our alias for compatibility
        self.items_reordered.connect(self.links_reordered.emit)
        try:
            self.destroyed.connect(self._cleanup_connections)  # type: ignore[arg-type]
        except Exception:
            pass

    def _setup_table(self):
        model = LinksTableModel([])
        self.setModel(model)

        # Subscribe to language changes to update table headers
        try:
            self._lang_service = LanguageService.instance()
            self._lang_service.languageChanged.connect(self._on_language_changed)
        except Exception:
            self._lang_service = None

        # Visual configuration
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setShowGrid(False)
        header = ExplorerHeaderView(Qt.Orientation.Horizontal, self)
        self.setHorizontalHeader(header)
        header.setSectionsClickable(True)
        col_widths = app_config.ui.get_col_widths()
        try:
            order_header = model.headerData(
                2, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
            )
            self.setColumnWidth(0, 32)
            self.setColumnWidth(1, col_widths[1])
            self.setColumnWidth(
                2,
                _header_text_width(header, str(order_header or "Order"), min_width=112),
            )
            self.setColumnWidth(3, col_widths[2])
            self.setColumnWidth(5, 104)
        except Exception:
            logger.debug(
                "LinksTableView: failed to set column widths", exc_info=True
            )
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        _icon_sz = app_config.ui.get_icon_size()
        self.setIconSize(QSize(_icon_sz[0], _icon_sz[1]))
        self.verticalHeader().setDefaultSectionSize(app_config.ui.get_row_height())
        header.setStretchLastSection(False)
        try:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        except Exception:
            logger.debug(
                "LinksTableView: failed to set resize mode for column 0/1", exc_info=True
            )
        # Column 3 ("Launch") resize mode is driven by config
        try:
            col2_mode = str(
                app_config.ui.get("ui.links_table_col2_mode", "fixed")
            ).lower()
        except Exception:
            col2_mode = "fixed"
        try:
            if col2_mode in ("fixed", "f"):
                header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            elif col2_mode in ("interactive", "i"):
                header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
            elif col2_mode in ("contents", "content", "auto", "resizetocontents"):
                header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            else:
                header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        except Exception:
            # Fallback to Fixed
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.setSortingEnabled(True)
        header.setSortIndicatorShown(False)
        header.sortIndicatorChanged.connect(self.sortByColumn)
        initial_col, initial_order = self._load_initial_sort()
        self._apply_sort(initial_col, initial_order)
        self.delegate = TableDelegate(self)
        self.setItemDelegate(self.delegate)
        # Global table settings: no word wrap, elide on the right
        try:
            self.setWordWrap(False)
        except Exception:
            pass
        try:
            self.setTextElideMode(Qt.TextElideMode.ElideRight)
        except Exception:
            pass
        # Use the single delegate for every column so hover applies to entire rows
        self.setMouseTracking(True)
        # QTableView: rely on ``entered(QModelIndex)`` instead of ``cellEntered``
        try:
            self.entered.connect(self._on_index_entered)
        except Exception:
            logger.debug(
                "LinksTableView: failed to connect entered signal", exc_info=True
            )
        self.leaveEvent = self._on_leave_event

        # Sorting on header click: re-enable if disabled after drag-and-drop and perform one sort
        self.horizontalHeader().sectionClicked.connect(self._on_sort_clicked)
        try:
            header.sortIndicatorChanged.connect(self._on_sort_indicator_changed)
        except Exception:
            logger.debug(
                "LinksTableView: failed to connect sortIndicatorChanged", exc_info=True
            )
        # Rebuild the cache when the model layout changes or rows are moved
        model = self.model()
        try:
            model.layoutChanged.connect(self._rebuild_cache_on_layout)
        except Exception:
            logger.debug(
                "LinksTableView: failed to connect layoutChanged", exc_info=True
            )
        try:
            model.rowsMoved.connect(self._on_rows_moved)
        except Exception:
            logger.debug(
                "LinksTableView: failed to connect rowsMoved", exc_info=True
            )
        try:
            model.dataChanged.connect(self._on_model_data_changed)
        except Exception:
            pass
        try:
            model.modelReset.connect(self._on_model_data_changed)
        except Exception:
            pass
        try:
            model.rowsInserted.connect(self._on_model_data_changed)
        except Exception:
            pass
        try:
            model.rowsRemoved.connect(self._on_model_data_changed)
        except Exception:
            pass
        try:
            model.orderEdited.connect(self.links_reordered.emit)
        except Exception:
            logger.debug(
                "LinksTableView: failed to connect orderEdited", exc_info=True
            )

    def _on_model_data_changed(self, *args, **kwargs) -> None:
        try:
            main_win = self.window()
            if main_win and hasattr(main_win, "update_group_launch_action_state"):
                main_win.update_group_launch_action_state()
        except Exception:
            pass

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        try:
            main_win = self.window()
            if main_win and hasattr(main_win, "update_group_launch_action_state"):
                main_win.update_group_launch_action_state()
        except Exception:
            pass

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        try:
            main_win = self.window()
            if main_win and hasattr(main_win, "update_group_launch_action_state"):
                main_win.update_group_launch_action_state()
        except Exception:
            pass

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if self._has_external_link_targets(event):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._has_external_link_targets(event):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        targets = self._external_link_targets_from_event(event)
        if targets:
            try:
                self.externalLinkDropped.emit(
                    {
                        "type": "external_link_to_current_category",
                        "targets": targets,
                        "urls": targets,
                    }
                )
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
            except Exception:
                logger.warning("Failed to emit external URL table drop", exc_info=True)
                event.ignore()
            return
        super().dropEvent(event)

    def _has_external_link_targets(self, event) -> bool:
        return bool(self._external_link_targets_from_event(event))

    def _external_link_targets_from_event(self, event) -> list[str]:
        try:
            if self._is_internal_drop(event):
                return []
            mime = event.mimeData() if hasattr(event, "mimeData") else None
            from app.utils.ui.dnd.mime import MimeDataParser

            return MimeDataParser.extract_external_link_targets(mime)
        except Exception:
            logger.debug("Failed to extract external URLs from table drop", exc_info=True)
            return []

    def _on_index_entered(self, index: QModelIndex):
        row = index.row()
        if self.delegate.hovered_row != row:
            self.delegate.hovered_row = row
            viewport = self.viewport()
            if viewport is not None:
                viewport.update()

    def _on_leave_event(self, event):
        if self.delegate.hovered_row != -1:
            self.delegate.hovered_row = -1
            viewport = self.viewport()
            if viewport is not None:
                viewport.update()
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.quickLookRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    # Override abstract methods from ``BaseDragDropTableWidget``
    def _extract_item_ids_from_items(self, items):
        """Extract link IDs from selected items."""
        # Delegate to ``DragDropHandlerMixin`` implementation
        return DragDropHandlerMixin._extract_item_ids_from_items(self, items)

    def _move_row_visually(self, source_row: int, target_row: int):
        """Move a row visually inside the table."""
        # Delegate to ``DragDropHandlerMixin`` implementation
        return DragDropHandlerMixin._move_row_visually(self, source_row, target_row)

    def _get_current_order(self):
        """Return the current order of links."""
        # Delegate to ``DragDropHandlerMixin`` implementation
        return DragDropHandlerMixin._get_current_order(self)

    def _on_sort_clicked(self, logical_index):
        """Enable sorting on click if manual ordering disabled it."""
        if logical_index == 0:
            return
        header = self.horizontalHeader()
        if not self.isSortingEnabled():
            self.setSortingEnabled(True)
            try:
                header.setSortIndicatorShown(False)
            except Exception:
                logger.debug(
                    "LinksTableView: failed to setSortIndicatorShown(False)",
                    exc_info=True,
                )
            # Execute a single ascending sort; Qt will handle subsequent toggles
            try:
                self.sortByColumn(logical_index, Qt.SortOrder.AscendingOrder)
            except Exception:
                logger.debug(
                    "LinksTableView: sortByColumn on header click failed", exc_info=True
                )

    def _on_rows_moved(self, *_args) -> None:
        """Handle rows moved signal to rebuild cache."""
        self._rebuild_cache_on_layout()

    def _rebuild_cache_on_layout(self):
        """Rebuild cache after the model layout changes (sorting/reordering)."""
        if self._rebuild_in_progress:
            return
        self._rebuild_in_progress = True
        try:
            self.rebuild_cache_from_items()
        except Exception as e:
            logger.debug(
                "[SORT] Cache rebuild failed on layoutChanged: %s", e, exc_info=True
            )
        finally:
            self._rebuild_in_progress = False

    def _cleanup_connections(self, *_args) -> None:
        """Disconnect signals to prevent memory leaks."""
        if getattr(self, "_cleanup_done", False):
            return
        self._cleanup_done = True
        try:
            if hasattr(self, "entered"):
                try:
                    self.entered.disconnect()
                except (RuntimeError, TypeError):
                    pass
            header = self.horizontalHeader() if hasattr(self, "horizontalHeader") else None
            if header:
                try:
                    header.sectionClicked.disconnect()
                    header.sortIndicatorChanged.disconnect()
                except (RuntimeError, TypeError):
                    pass
            model = self.model() if hasattr(self, "model") else None
            if model and hasattr(model, "layoutChanged"):
                try:
                    model.layoutChanged.disconnect()
                except (RuntimeError, TypeError):
                    pass
            try:
                self.items_reordered.disconnect()
            except (RuntimeError, TypeError):
                pass
            lang = getattr(self, "_lang_service", None)
            if lang is not None:
                try:
                    lang.languageChanged.disconnect(self._on_language_changed)
                except (RuntimeError, TypeError):
                    pass
                self._lang_service = None
        except Exception:
            pass

    def _on_language_changed(self, _code: str) -> None:
        """Update localized headers on language change."""
        try:
            m = self.model()
            if m is not None and hasattr(m, "retranslateUi"):
                m.retranslateUi()
        except Exception:
            pass

    # --- Sorting helpers ---
    def _load_sort_from_settings(self) -> tuple[int | None, Qt.SortOrder | None]:
        """Fetch saved sort state from settings if available."""
        settings = getattr(self, "_settings", None)
        if settings and hasattr(settings, "get_table_sort"):
            try:
                col, order = settings.get_table_sort()
                return col, order
            except Exception:
                logger.debug("LinksTableView: get_table_sort failed", exc_info=True)
        return None, None

    def _load_initial_sort(self) -> tuple[int, Qt.SortOrder]:
        """Return initial sort (saved or default)."""
        return 2, Qt.SortOrder.AscendingOrder

    def _save_sort_to_settings(self, col: int, order: Qt.SortOrder) -> None:
        if not getattr(self, "_allow_sort_persist", False):
            return
        settings = getattr(self, "_settings", None)
        if settings and hasattr(settings, "set_table_sort"):
            try:
                settings.set_table_sort(int(col), Qt.SortOrder(order))
            except Exception:
                logger.debug("LinksTableView: set_table_sort failed", exc_info=True)

    def _apply_sort(self, column: int | None, order: Qt.SortOrder) -> None:
        """Apply sort safely, updating header indicator as well."""
        if column is None or column < 0:
            return
        try:
            self.sortByColumn(column, order)
            header = self.horizontalHeader()
            if header:
                header.setSortIndicatorShown(True)
                header.setSortIndicator(column, order)
        except Exception:
            logger.debug("LinksTableView: applying sort failed", exc_info=True)

    def _default_sort_from_links(
        self, links: list[dict] | None
    ) -> tuple[int, Qt.SortOrder]:
        """Use saved user order when no persisted user preference exists."""
        return 2, Qt.SortOrder.AscendingOrder

    def reset_default_sort_for_next_populate(self) -> None:
        """Force the next normal load to start from the saved user order."""
        self._sort_initialized = False
        self._allow_sort_persist = False

    def ensure_initial_sort(self, links: list[dict] | None = None) -> None:
        """Apply initial sort once, always defaulting to user order."""
        if self._sort_initialized:
            return
        self._sort_initialized = True
        col, order = self._default_sort_from_links(links)
        self._apply_sort(col, order)
        self._allow_sort_persist = True
        try:
            self._save_sort_to_settings(col, order)
        except Exception:
            logger.debug("LinksTableView: failed to persist initial sort", exc_info=True)

    def _on_sort_indicator_changed(
        self, logical_index: int, order: Qt.SortOrder
    ) -> None:
        """Persist sort changes."""
        try:
            self._save_sort_to_settings(logical_index, order)
        except Exception:
            logger.debug("LinksTableView: failed to persist sort change", exc_info=True)
