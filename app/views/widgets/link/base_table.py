# Core module for the links table
# Contains the main ``LinksTableView`` class and foundational functionality

import logging

from PyQt6.QtCore import QModelIndex, QSize, Qt, pyqtSignal

try:
    from PyQt6.QtCore import pyqtProperty  # type: ignore[attr-defined]
except ImportError:
    pyqtProperty = property  # type: ignore[misc,assignment]
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.utils.ui.dnd.link import DragDropHandlerMixin
from app.utils.ui.dnd.mime import get_link_mime
from app.views.widgets.base.base_widgets import BaseDragDropTableWidget
from app.views.widgets.link.links_model import LinksTableModel
from i18n.language_service import LanguageService

from .data_management import DataManagementMixin

# Import all mixins
from .item_builders import ItemBuildersMixin
from .population_manager import PopulationManagerMixin
from .row_operations import RowOperationsMixin

# Module-level logger
logger = logging.getLogger(__name__)


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
        self.col_opened_px = _get_px("table_opened_col_px")  # "Opened" column (index=2)
        self.col_notes_px = _get_px("table_notes_col_px")  # "Notes" column (index=3)

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
            painter.save()
            painter.fillRect(option.rect, self.hover_color)
            painter.restore()

    def _apply_column_font_size(self, opt, col):
        """Apply font size for specific column."""
        try:
            val = self.col_sizes.get(col)
            if val is None:
                if col == 2:
                    val = self.col_opened_px
                elif col == 3:
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
            available_w = max(0, opt.rect.width() - 4)
        except Exception:
            available_w = opt.rect.width()
        opt.text = opt.fontMetrics.elidedText(
            opt.text, Qt.TextElideMode.ElideRight, available_w
        )
        opt.displayAlignment = (
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )

    def paint(self, painter, option, index):
        self._paint_hover_highlight(painter, option, index)

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        col = index.column()
        self._apply_column_font_size(opt, col)

        if col == 2:
            self._apply_column_color(opt, col, "openedColColor")
        elif col == 3:
            self._apply_column_color(opt, col, "notesColColor")

        if col == 1:
            self._apply_name_column_elision(opt)

        super().paint(painter, opt, index)

        # Top-left corner borders (cell above row 1 and before column 0)
        # are rendered via QSS (`QTableView QTableCornerButton::section`) in `dark.qss`


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

    # Signal emitted after bulk population/update of the table
    table_populated: pyqtSignal = pyqtSignal()

    def update_font_size(self, font_size: int):
        """Apply the local font size to every table cell."""
        # Check whether the font size actually changed
        if hasattr(self, "_current_font_size") and getattr(self, "_current_font_size", None) == font_size:
            return

        self._current_font_size = font_size

        # Create a new font instance and apply it to the table
        from PyQt6.QtGui import QFont

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
        col_widths = app_config.ui.get_col_widths()
        try:
            self.setColumnWidth(0, col_widths[0])
        except Exception:
            pass
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        _icon_sz = app_config.ui.get_icon_size()
        self.setIconSize(QSize(_icon_sz[0], _icon_sz[1]))
        self.verticalHeader().setDefaultSectionSize(app_config.ui.get_row_height())
        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        try:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        except Exception:
            logger.debug(
                "LinksTableView: failed to set resize mode for column 0", exc_info=True
            )
        try:
            self.setColumnWidth(1, col_widths[1])
            self.setColumnWidth(2, col_widths[2])
        except Exception:
            logger.debug(
                "LinksTableView: failed to set column widths for 1/2", exc_info=True
            )
        # Column 2 ("Opened") resize mode is driven by config
        try:
            col2_mode = str(
                app_config.ui.get("ui.links_table_col2_mode", "fixed")
            ).lower()
        except Exception:
            col2_mode = "fixed"
        try:
            if col2_mode in ("fixed", "f"):
                header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            elif col2_mode in ("interactive", "i"):
                header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
            elif col2_mode in ("contents", "content", "auto", "resizetocontents"):
                header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            else:
                header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        except Exception:
            # Fallback to Fixed
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.setSortingEnabled(True)
        header.setSortIndicatorShown(True)
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

    def _on_index_entered(self, index: QModelIndex):
        row = index.row()
        if self.delegate.hovered_row != row:
            self.delegate.hovered_row = row

    def _on_leave_event(self, event):
        if self.delegate.hovered_row != -1:
            self.delegate.hovered_row = -1
        event.accept()

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
        header = self.horizontalHeader()
        if not self.isSortingEnabled():
            self.setSortingEnabled(True)
            try:
                header.setSortIndicatorShown(True)
            except Exception:
                logger.debug(
                    "LinksTableView: failed to setSortIndicatorShown(True)",
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
        col, order = self._load_sort_from_settings()
        if isinstance(col, int) and isinstance(order, Qt.SortOrder):
            return col, order
        return 1, Qt.SortOrder.AscendingOrder

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
        """Pick default sort: name asc or last_used asc when any launch info exists."""
        try:
            if links and any(
                link.get("last_used") for link in links if isinstance(link, dict)
            ):
                # Ascending keeps most recently opened at bottom
                return 2, Qt.SortOrder.AscendingOrder
        except Exception:
            logger.debug("LinksTableView: default sort detection failed", exc_info=True)
        return 1, Qt.SortOrder.AscendingOrder

    def ensure_initial_sort(self, links: list[dict] | None = None) -> None:
        """Apply initial sort once, preferring saved settings then heuristics."""
        if self._sort_initialized:
            return
        self._sort_initialized = True
        col, order = self._load_sort_from_settings()
        if not (isinstance(col, int) and isinstance(order, Qt.SortOrder)):
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
