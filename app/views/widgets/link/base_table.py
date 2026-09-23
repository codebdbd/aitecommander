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
from app.views.widgets.link.columns import (
    LINK_TABLE_COLUMNS,
    LinkTableColumn,
    is_column,
    resize_mode_name_for_descriptor,
)
from app.views.widgets.link.links_model import HEADER_CHEVRON_PADDING_ROLE, LinksTableModel
from app.views.widgets.link.sort_controller import LinkSortAction, LinkTableSortController
from i18n.language_service import LanguageService

from .data_management import DataManagementMixin

# Import all mixins
from .item_builders import ItemBuildersMixin
from .population_manager import PopulationManagerMixin
from .row_operations import RowOperationsMixin

# Module-level logger
logger = logging.getLogger(__name__)

_PRIMARY_TEXT_COLUMNS = frozenset((int(LinkTableColumn.NAME), int(LinkTableColumn.NOTES)))
_SECONDARY_TEXT_COLUMNS = frozenset(
    (int(LinkTableColumn.ORDER), int(LinkTableColumn.LAUNCH), int(LinkTableColumn.TYPE))
)


def _header_text_width(header: QHeaderView, text: str, *, min_width: int) -> int:
    """Return a header column width that leaves room for text and sort toggle."""
    try:
        text_width = header.fontMetrics().horizontalAdvance(str(text))
        return max(min_width, text_width + 40)
    except Exception:
        return min_width


def _qt_resize_mode(mode_name: str) -> QHeaderView.ResizeMode:
    """Map declarative column resize policy to Qt resize modes."""
    modes = {
        "fixed": QHeaderView.ResizeMode.Fixed,
        "interactive": QHeaderView.ResizeMode.Interactive,
        "stretch": QHeaderView.ResizeMode.Stretch,
        "resize_to_contents": QHeaderView.ResizeMode.ResizeToContents,
    }
    return modes.get(mode_name, QHeaderView.ResizeMode.Interactive)


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

        self.body_font_size = _get_px("table_row_px")

    def update_column_sizes(self, font_size: int):
        """Update column font sizes based on new base font size.
        
        Scales all column sizes proportionally to the new font size.
        """
        try:
            self.body_font_size = font_size
                
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

    def _body_font_size_for_column(self, col: int) -> int | None:
        """Return the unified body font size for a table column."""
        if is_column(col, LinkTableColumn.GROUP_LAUNCH):
            return None
        return self.body_font_size

    def _apply_column_font_size(self, opt, col):
        """Apply the same body font size to every text cell."""
        try:
            val = self._body_font_size_for_column(col)
            if val and int(val) > 0:
                f = opt.font
                if self._font_units == "pt":
                    f.setPointSize(int(val))
                else:
                    f.setPixelSize(int(val))
                opt.font = f
        except Exception:
            pass

    def _color_attr_for_column(self, col: int) -> str | None:
        """Return the table text color role for a body column."""
        if col in _PRIMARY_TEXT_COLUMNS:
            return "primaryCellTextColor"
        if col in _SECONDARY_TEXT_COLUMNS:
            return "secondaryCellTextColor"
        return None

    def _fallback_color_attr_for_column(self, col: int) -> str | None:
        """Return legacy color property used until every theme defines roles."""
        if col in _PRIMARY_TEXT_COLUMNS:
            return "notesColColor"
        if col in _SECONDARY_TEXT_COLUMNS:
            return "openedColColor"
        return None

    def _resolve_column_color(self, col: int) -> QColor | None:
        view = self.parent() if hasattr(self, "parent") else None
        if view is None:
            return None
        for attr in (self._color_attr_for_column(col), self._fallback_color_attr_for_column(col)):
            if not attr or not hasattr(view, attr):
                continue
            color = getattr(view, attr)
            if isinstance(color, QColor) and color.isValid():
                return color
        return None

    def _apply_column_color(self, opt, col):
        """Apply role-based table text color for body columns."""
        try:
            color = self._resolve_column_color(col)
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
        if is_column(index.column(), LinkTableColumn.GROUP_LAUNCH):
            option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator

    def drawDisplay(self, painter, option, rect, text):
        """Override text rendering to enforce theme colors.

        QSS cascade prioritizes inherited ``QWidget { color: }`` over
        ``option.palette`` passed to ``drawControl``. Direct ``setPen``
        on the painter wins over any QSS rule, so theme-aware colors
        (``qproperty-primaryCellTextColor`` / ``openedColColor`` etc.)
        are applied here for non-selected rows. Selected rows keep the
        QSS rule ``QTableView::item:selected { color: }`` intact.
        """
        col = getattr(self, "_current_paint_col", -1)
        is_selected = bool(
            getattr(self, "_current_paint_selected", False)
            or (option.state & QStyle.StateFlag.State_Selected)
        )
        if not is_selected:
            color = self._resolve_column_color(col)
            if isinstance(color, QColor) and color.isValid():
                old_pen = painter.pen()
                painter.setPen(color)
                try:
                    super().drawDisplay(painter, option, rect, text)
                finally:
                    painter.setPen(old_pen)
                return
        super().drawDisplay(painter, option, rect, text)

    def paint(self, painter, option, index):
        self._paint_hover_highlight(painter, option, index)

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        col = index.column()
        self._apply_column_font_size(opt, col)

        self._apply_column_color(opt, col)

        if is_column(col, LinkTableColumn.NAME):
            self._apply_name_column_elision(opt)

        try:
            self._current_paint_col = col
            self._current_paint_selected = bool(
                opt.state & QStyle.StateFlag.State_Selected
            )
            super().paint(painter, opt, index)
        finally:
            self._current_paint_col = -1
            self._current_paint_selected = False

        if is_column(col, LinkTableColumn.GROUP_LAUNCH):
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
        if is_column(index.column(), LinkTableColumn.GROUP_LAUNCH):
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

    @staticmethod
    def _global_row_height() -> int:
        try:
            from app.config_data import app_config

            return int(app_config.ui.get_row_height())
        except Exception:
            return 32

    def _sync_row_height(self) -> None:
        """Pin header height exactly to ``ui.row_height`` (body row height).

        ``QHeaderView`` derives section heights from ``fontMetrics + QSS``
        which commonly diverges from the explicit body row height used for
        vertical sections. Fix by clamping all relevant sizes:
        ``defaultSectionSize``, ``minimumSectionSize``, widget-level fixed
        height. Also re-apply after Style/Font/Layout events since QSS
        re-application can reset geometry hints.
        """
        h = self._global_row_height()
        try:
            self.setDefaultSectionSize(h)
        except Exception:
            pass
        try:
            self.setMinimumSectionSize(h)
        except Exception:
            pass
        try:
            self.setFixedHeight(h)
        except Exception:
            try:
                self.setMinimumHeight(h)
                self.setMaximumHeight(h)
            except Exception:
                pass
        try:
            self.updateGeometry()
        except Exception:
            pass

    def __init__(self, orientation: Qt.Orientation, parent=None):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self.setSectionsClickable(True)
        self._hovered_section = -1
        self._hovered_toggle = False
        try:
            style = ExplorerHeaderStyle(self)
            style.setParent(self)
            self.setStyle(style)
        except Exception:
            pass
        try:
            self._sync_row_height()
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
            try:
                self._sync_row_height()
            except Exception:
                pass
            self.viewport().update()
        super().changeEvent(event)

    def resizeEvent(self, event):
        try:
            self._sync_row_height()
        except Exception:
            pass
        super().resizeEvent(event)

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

    def _resolve_header_text_color(self) -> QColor:
        """Return the color used for header text, glyphs, and sort arrows."""
        parent_table = self.parent()
        try:
            color = getattr(parent_table, "tableHeaderTextColor", QColor())
            if isinstance(color, QColor) and color.isValid():
                return color
        except Exception:
            pass
        normal, _hover = self._get_icon_colors()
        return normal

    @staticmethod
    def _paint_tinted_icon(
        painter: QPainter, icon: QIcon, x: int, y: int, size: int, color: QColor
    ) -> None:
        """Paint a monochrome icon using the header text role."""
        pixmap = icon.pixmap(size, size)
        if pixmap.isNull() or not color.isValid():
            icon.paint(painter, x, y, size, size, Qt.AlignmentFlag.AlignCenter)
            return
        tinted = pixmap.copy()
        tint_painter = QPainter(tinted)
        try:
            tint_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            tint_painter.fillRect(tinted.rect(), color)
        finally:
            tint_painter.end()
        painter.drawPixmap(x, y, tinted)

    def paintSection(self, painter, rect, logicalIndex):
        if logicalIndex == 0:
            opt = QStyleOptionHeader()
            self.initStyleOption(opt)
            opt.rect = rect
            opt.section = logicalIndex
            opt.orientation = Qt.Orientation.Horizontal
            opt.position = QStyleOptionHeader.SectionPosition.Beginning
            opt.text = ""
            opt.icon = QIcon()
            self.style().drawControl(QStyle.ControlElement.CE_Header, opt, painter, self)
            model = self.model()
            if model is not None:
                icon = model.headerData(
                    int(LinkTableColumn.GROUP_LAUNCH),
                    Qt.Orientation.Horizontal,
                    Qt.ItemDataRole.DecorationRole,
                )
                if isinstance(icon, QIcon) and not icon.isNull():
                    sz = 20
                    ix = rect.x() + (rect.width() - sz) // 2
                    iy = rect.y() + (rect.height() - sz) // 2
                    self._paint_tinted_icon(
                        painter, icon, ix, iy, sz, self._resolve_header_text_color()
                    )
            return

        super().paintSection(painter, rect, logicalIndex)

    def paintEvent(self, event):
        super().paintEvent(event)
        is_sorted = self.sortIndicatorSection() >= 0
        sorted_sec = self.sortIndicatorSection() if is_sorted else -1
        hovered_sec = self._hovered_section
        if hovered_sec <= int(LinkTableColumn.GROUP_LAUNCH):
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

        chev_color = self._resolve_header_text_color()
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

    @staticmethod
    def _coerce_color(value) -> QColor:
        return QColor(value) if isinstance(value, QColor) else QColor(str(value))

    def _update_viewport_after_style_change(self) -> None:
        viewport = self.viewport()
        if viewport is not None:
            viewport.update()

    def changeEvent(self, event) -> None:
        """Reset theme properties on style change.

        When the app calls ``QApplication.setStyleSheet()`` to switch themes,
        Qt re-evaluates QSS and calls each ``qproperty-`` setter. However,
        primary/secondary colors are only explicitly defined in a subset of
        themes — most rely on ``openedColColor``/``notesColColor`` fallbacks.
        Without resetting primary/secondary defaults here, a previous theme's
        explicit primary/secondary value would stick forever (since isValid()
        skips the legacy assignment), producing stale colors on light themes.
        Also re-syncs header row height because QSS re-application can reset
        ``QHeaderView`` geometry hints (font metrics + padding recalculated).
        """
        try:
            et = event.type() if event is not None else None
            if et in (
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.FontChange,
            ):
                try:
                    if hasattr(self, "_primary_cell_text_color"):
                        self._primary_cell_text_color = QColor()
                    if hasattr(self, "_secondary_cell_text_color"):
                        self._secondary_cell_text_color = QColor()
                except Exception:
                    pass
                try:
                    header = (
                        self.horizontalHeader()
                        if hasattr(self, "horizontalHeader")
                        else None
                    )
                    if header is not None and hasattr(header, "_sync_row_height"):
                        header._sync_row_height()
                except Exception:
                    pass
                try:
                    vh = (
                        self.verticalHeader()
                        if hasattr(self, "verticalHeader")
                        else None
                    )
                    if vh is not None:
                        try:
                            from app.config_data import app_config

                            vh.setDefaultSectionSize(
                                int(app_config.ui.get_row_height())
                            )
                        except Exception:
                            pass
                except Exception:
                    pass
                self._update_viewport_after_style_change()
        except Exception:
            pass
        super().changeEvent(event)

    # qproperty: color for header text/glyphs/sort arrow
    def _get_table_header_text_color(self) -> QColor:
        try:
            return getattr(self, "_table_header_text_color", QColor())
        except Exception:
            return QColor()

    def _set_table_header_text_color(self, value) -> None:
        try:
            self._table_header_text_color = self._coerce_color(value)
            header = self.horizontalHeader() if hasattr(self, "horizontalHeader") else None
            if header is not None:
                header.viewport().update()
        except Exception:
            pass

    tableHeaderTextColor = pyqtProperty(
        QColor, fget=_get_table_header_text_color, fset=_set_table_header_text_color
    )

    # qproperty: color for primary cell text (Name, Notes)
    def _get_primary_cell_text_color(self) -> QColor:
        try:
            return getattr(self, "_primary_cell_text_color", QColor())
        except Exception:
            return QColor()

    def _set_primary_cell_text_color(self, value) -> None:
        try:
            self._primary_cell_text_color = self._coerce_color(value)
            self._update_viewport_after_style_change()
        except Exception:
            pass

    primaryCellTextColor = pyqtProperty(
        QColor, fget=_get_primary_cell_text_color, fset=_set_primary_cell_text_color
    )

    # qproperty: color for secondary cell text (Order, Launch, Type)
    def _get_secondary_cell_text_color(self) -> QColor:
        try:
            return getattr(self, "_secondary_cell_text_color", QColor())
        except Exception:
            return QColor()

    def _set_secondary_cell_text_color(self, value) -> None:
        try:
            self._secondary_cell_text_color = self._coerce_color(value)
            self._update_viewport_after_style_change()
        except Exception:
            pass

    secondaryCellTextColor = pyqtProperty(
        QColor, fget=_get_secondary_cell_text_color, fset=_set_secondary_cell_text_color
    )

    # qproperty: color for the "Opened" column (QSS: ``qproperty-openedColColor``)
    def _get_opened_col_color(self) -> QColor:
        try:
            return getattr(self, "_opened_col_color", QColor())
        except Exception:
            return QColor()

    def _set_opened_col_color(self, value) -> None:
        try:
            color = self._coerce_color(value)
            self._opened_col_color = color
            # Legacy fallback: openedColColor always feeds secondaryCellTextColor
            # so themes that only define openedColColor/notesColColor keep working.
            # NOTE: always overwrite, never skip by isValid() — otherwise a
            # previous theme's value leaks across setStyleSheet() calls.
            if isinstance(color, QColor) and color.isValid():
                self._secondary_cell_text_color = QColor(color)
            self._update_viewport_after_style_change()
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
            color = self._coerce_color(value)
            self._notes_col_color = color
            # Legacy fallback: notesColColor always feeds primaryCellTextColor.
            # Always overwrite — never skip by isValid() to avoid stale values
            # leaking from a previously applied theme.
            if isinstance(color, QColor) and color.isValid():
                self._primary_cell_text_color = QColor(color)
            self._update_viewport_after_style_change()
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
            self._hover_row_color = self._coerce_color(value)
            self._update_viewport_after_style_change()
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
        self._sort_controller = LinkTableSortController()
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
            for descriptor in LINK_TABLE_COLUMNS:
                width = descriptor.fallback_width
                if descriptor.config_width_index is not None:
                    try:
                        width = col_widths[descriptor.config_width_index]
                    except Exception:
                        pass
                if descriptor.min_width:
                    header_text = model.headerData(
                        descriptor.index,
                        Qt.Orientation.Horizontal,
                        Qt.ItemDataRole.DisplayRole,
                    )
                    width = _header_text_width(
                        header,
                        str(header_text or descriptor.header_source),
                        min_width=descriptor.min_width,
                    )
                if width:
                    self.setColumnWidth(descriptor.index, int(width))
        except Exception:
            logger.debug(
                "LinksTableView: failed to set column widths", exc_info=True
            )
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        _icon_sz = app_config.ui.get_icon_size()
        self.setIconSize(QSize(_icon_sz[0], _icon_sz[1]))
        self.verticalHeader().setDefaultSectionSize(app_config.ui.get_row_height())
        try:
            if hasattr(header, "_sync_row_height"):
                header._sync_row_height()
        except Exception:
            pass
        header.setStretchLastSection(False)
        try:
            for descriptor in LINK_TABLE_COLUMNS:
                configured_mode = None
                if descriptor.resize_mode_config_key:
                    configured_mode = app_config.ui.get(
                        descriptor.resize_mode_config_key,
                        descriptor.resize_mode,
                    )
                mode_name = resize_mode_name_for_descriptor(
                    descriptor,
                    configured_mode,
                )
                header.setSectionResizeMode(
                    descriptor.index,
                    _qt_resize_mode(mode_name),
                )
        except Exception:
            logger.debug(
                "LinksTableView: failed to apply column resize policy",
                exc_info=True,
            )
        self.setSortingEnabled(True)
        header.setSortIndicatorShown(False)
        header.sortIndicatorChanged.connect(self.sortByColumn)
        self._apply_sort_action(self._sort_controller.initial_sort())
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
        action = self._sort_controller.header_click_action(
            logical_index,
            sorting_enabled=self.isSortingEnabled(),
        )
        if action is None:
            return
        header = self.horizontalHeader()
        self.setSortingEnabled(True)
        if not action.show_indicator:
            try:
                header.setSortIndicatorShown(False)
            except Exception:
                logger.debug(
                    "LinksTableView: failed to setSortIndicatorShown(False)",
                    exc_info=True,
                )
        try:
            self._apply_sort_action(action)
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
        return self._sort_controller.default_sort()

    def _save_sort_to_settings(self, col: int, order: Qt.SortOrder) -> None:
        if not self._sort_controller.should_persist():
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

    def _apply_sort_action(self, action: LinkSortAction | None) -> None:
        """Apply a sort action produced by the view-level sort controller."""
        if action is None:
            return
        self._apply_sort(action.column, action.order)
        if not action.show_indicator:
            try:
                self.horizontalHeader().setSortIndicatorShown(False)
            except Exception:
                logger.debug(
                    "LinksTableView: failed to hide sort indicator",
                    exc_info=True,
                )
        self._sort_controller.mark_action_applied(action)
        if action.persist_after_apply:
            self._save_sort_to_settings(action.column, action.order)

    def _default_sort_from_links(
        self, links: list[dict] | None
    ) -> tuple[int, Qt.SortOrder]:
        """Use saved user order when no persisted user preference exists."""
        return int(LinkTableColumn.ORDER), Qt.SortOrder.AscendingOrder

    def reset_default_sort_for_next_populate(self) -> None:
        """Force the next normal load to start from the saved user order."""
        self._sort_controller.reset_for_category_load()

    def should_apply_initial_sort_for_mode(self, mode: str) -> bool:
        """Return whether a populate mode should apply the initial default sort."""
        return self._sort_controller.should_apply_initial_sort_for_mode(mode)

    def ensure_initial_sort(self, links: list[dict] | None = None) -> None:
        """Apply initial sort once, always defaulting to user order."""
        try:
            self._apply_sort_action(self._sort_controller.ensure_initial_sort())
        except Exception:
            logger.debug("LinksTableView: failed to persist initial sort", exc_info=True)

    def restore_sort_after_populate(
        self,
        sort_col: int,
        sort_order: Qt.SortOrder,
        total_columns: int,
    ) -> bool:
        """Restore a captured sort state after model data changes."""
        action = self._sort_controller.restore_after_populate_action(
            sort_col,
            sort_order,
            total_columns=total_columns,
        )
        if action is None:
            return False
        self._apply_sort_action(action)
        return True

    def _on_sort_indicator_changed(
        self, logical_index: int, order: Qt.SortOrder
    ) -> None:
        """Persist sort changes."""
        try:
            self._save_sort_to_settings(logical_index, order)
        except Exception:
            logger.debug("LinksTableView: failed to persist sort change", exc_info=True)
