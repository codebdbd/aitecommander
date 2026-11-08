"""Floating global Command Palette dialog (Alt+~) with full theme token support."""

from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import (
    QAbstractListModel,
    QCoreApplication,
    QEvent,
    QModelIndex,
    QObject,
    QRect,
    QRectF,
    QSize,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QIcon,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from app.services.theme_registry import (
    DEFAULT_DARK_TOKENS,
    DEFAULT_LIGHT_TOKENS,
    theme_registry,
)
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.path_service import get_current_theme
from app.views.common.retranslatable import ReTranslatable

logger = logging.getLogger(__name__)

LINK_DATA_ROLE = int(Qt.ItemDataRole.UserRole) + 1


class CommandPaletteModel(QAbstractListModel):
    """List model backing the Command Palette results view."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._items: list[dict[str, Any]] = []
        self._icon_cache: dict[str, QIcon] = {}

    def set_items(self, items: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._items = list(items or [])
        self.endResetModel()

    def clear_icon_cache(self) -> None:
        self._icon_cache.clear()
        if self._items:
            top = self.index(0, 0)
            bottom = self.index(len(self._items) - 1, 0)
            self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.DecorationRole])

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def item_at(self, row: int) -> dict[str, Any] | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> Any:
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._items):
            return None
        item = self._items[row]

        if role == int(Qt.ItemDataRole.DisplayRole):
            return str(item.get("name") or "")
        if role == LINK_DATA_ROLE:
            return item
        if role == int(Qt.ItemDataRole.DecorationRole):
            return self._resolve_icon(item)
        if role == int(Qt.ItemDataRole.ToolTipRole):
            url = str(item.get("url") or "")
            notes = str(item.get("notes") or "").strip()
            if notes.startswith("aite_enc:v1:"):
                enc_label = QCoreApplication.translate("NotePasswordDialog", "Encrypted")
                notes = f"🔒 {enc_label}"
            return f"{url}\n{notes}".strip() if notes else url
        return None

    def _resolve_icon(self, item: dict[str, Any]) -> QIcon | None:
        try:
            resolved_path = resolve_icon_for_link(item)
            if not resolved_path:
                return None
            cached = self._icon_cache.get(resolved_path)
            if cached is not None:
                return cached
            icon = create_icon_from_path(resolved_path)
            if isinstance(icon, QIcon) and not icon.isNull():
                self._icon_cache[resolved_path] = icon
                return icon
        except Exception:
            logger.debug("CommandPaletteModel: failed to resolve icon", exc_info=True)
        return None


class CommandPaletteDelegate(QStyledItemDelegate):
    """Theme-aware item delegate rendering icon, title, breadcrumb hierarchy, and type badge."""

    ROW_HEIGHT = 48

    _TYPE_BADGES: dict[str, str] = {
        "web": "WEB",
        "script": "SCRIPT",
        "program": "APP",
        "folder": "FOLDER",
        "file": "FILE",
    }

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QSize:
        width = option.rect.width() if option.rect.width() > 0 else 600
        return QSize(width, self.ROW_HEIGHT)

    @staticmethod
    def _current_tokens() -> dict[str, str]:
        try:
            theme_id = get_current_theme() or "dark"
            tokens = theme_registry.get_theme_tokens(theme_id)
            if tokens:
                return tokens
        except Exception:
            pass
        return dict(DEFAULT_DARK_TOKENS if (get_current_theme() or "dark") != "light" else DEFAULT_LIGHT_TOKENS)

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        if painter is None or not index.isValid():
            return

        item = index.data(LINK_DATA_ROLE)
        if not isinstance(item, dict):
            super().paint(painter, option, index)
            return

        tokens = self._current_tokens()
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        row_rect = option.rect.adjusted(4, 2, -4, -2)

        # 1. Background
        if is_selected:
            bg_color = QColor(tokens.get("selection_bg", "#2E4066"))
            path = QPainterPath()
            path.addRoundedRect(QRectF(row_rect), 6.0, 6.0)
            painter.fillPath(path, bg_color)
        elif is_hovered:
            bg_color = QColor(tokens.get("hover_bg", "#252D3A"))
            path = QPainterPath()
            path.addRoundedRect(QRectF(row_rect), 6.0, 6.0)
            painter.fillPath(path, bg_color)

        # 2. Icon
        icon_size = 24
        icon_x = row_rect.left() + 10
        icon_y = row_rect.top() + (row_rect.height() - icon_size) // 2
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QIcon) and not icon.isNull():
            icon.paint(painter, QRect(icon_x, icon_y, icon_size, icon_size))

        # 3. Type badge on the right
        raw_type = str(item.get("type") or "file").strip().lower()
        badge_text = self._TYPE_BADGES.get(raw_type, raw_type.upper() or "LINK")

        badge_font = QFont(option.font)
        badge_font.setPointSize(max(8, badge_font.pointSize() - 2))
        badge_font.setBold(True)
        painter.setFont(badge_font)
        badge_fm = painter.fontMetrics()
        badge_w = badge_fm.horizontalAdvance(badge_text) + 14
        badge_h = 20
        badge_x = row_rect.right() - badge_w - 10
        badge_y = row_rect.top() + (row_rect.height() - badge_h) // 2
        badge_rect = QRectF(badge_x, badge_y, badge_w, badge_h)

        accent_color = QColor(tokens.get("text_accent", "#58A6FF"))
        border_color = QColor(tokens.get("border_subtle", "#30363D"))
        if is_selected:
            fg_sel = QColor(tokens.get("selection_fg", "#FFFFFF"))
            painter.setPen(QPen(fg_sel, 1.0))
            painter.drawRoundedRect(badge_rect, 4.0, 4.0)
            painter.drawText(
                badge_rect,
                int(Qt.AlignmentFlag.AlignCenter),
                badge_text,
            )
        else:
            painter.setPen(QPen(border_color, 1.0))
            painter.drawRoundedRect(badge_rect, 4.0, 4.0)
            painter.setPen(accent_color)
            painter.drawText(
                badge_rect,
                int(Qt.AlignmentFlag.AlignCenter),
                badge_text,
            )

        # 4. Title and Subtitle (Hierarchy + URL)
        text_left = icon_x + icon_size + 10
        text_right = int(badge_x) - 10
        avail_w = max(40, text_right - text_left)

        title_font = QFont(option.font)
        title_font.setBold(True)
        painter.setFont(title_font)
        title_fm = painter.fontMetrics()

        name_str = str(item.get("name") or "")
        if int(item.get("is_favorite") or 0) == 1:
            name_str = f"★ {name_str}"
        elided_title = title_fm.elidedText(
            name_str, Qt.TextElideMode.ElideRight, avail_w
        )

        primary_color = (
            QColor(tokens.get("selection_fg", "#FFFFFF"))
            if is_selected
            else QColor(tokens.get("text_primary", "#E6EDF3"))
        )
        painter.setPen(primary_color)
        title_rect = QRect(text_left, row_rect.top() + 4, avail_w, 20)
        painter.drawText(
            title_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            elided_title,
        )

        # Subtitle: Sphere › Section › Category — url
        sub_font = QFont(option.font)
        sub_font.setPointSize(max(8, sub_font.pointSize() - 1))
        sub_font.setBold(False)
        painter.setFont(sub_font)
        sub_fm = painter.fontMetrics()

        sphere_name = str(item.get("sphere_name") or "").strip()
        section_name = str(item.get("section_name") or "").strip()
        category_name = str(item.get("category_name") or "").strip()
        crumbs = " › ".join(p for p in (sphere_name, section_name, category_name) if p)
        url_str = str(item.get("url") or "").strip()
        subtitle_raw = f"{crumbs}  •  {url_str}" if (crumbs and url_str) else (crumbs or url_str)
        elided_sub = sub_fm.elidedText(
            subtitle_raw, Qt.TextElideMode.ElideRight, avail_w
        )

        if is_selected:
            sub_color = QColor(tokens.get("selection_fg", "#FFFFFF"))
            sub_color.setAlpha(210)
        else:
            sub_color = QColor(tokens.get("text_secondary", "#8B949E"))
        painter.setPen(sub_color)
        sub_rect = QRect(text_left, row_rect.top() + 24, avail_w, 18)
        painter.drawText(
            sub_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            elided_sub,
        )

        painter.restore()


class CommandPaletteDialog(QDialog, ReTranslatable):
    """Frameless floating Quick Command Palette window triggered by Alt+~."""

    query_changed = pyqtSignal(str)
    link_activated = pyqtSignal(dict)
    link_reveal_requested = pyqtSignal(dict)

    DEFAULT_WIDTH = 660
    DEFAULT_HEIGHT = 430

    def __init__(self, parent: QWidget | None = None) -> None:
        QDialog.__init__(self, parent)
        self.setObjectName("CommandPaletteDialog")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)

        self.model = CommandPaletteModel(self)
        self.delegate = CommandPaletteDelegate(self)

        self._build_ui()
        self.retranslateUi()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.container = QFrame(self)
        self.container.setObjectName("commandPaletteContainer")
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 12, 12, 0)
        container_layout.setSpacing(8)

        # Search input row
        self.search_frame = QFrame(self.container)
        self.search_frame.setObjectName("commandPaletteSearchFrame")
        self.search_frame.setProperty("focused", "true")
        search_layout = QHBoxLayout(self.search_frame)
        search_layout.setContentsMargins(10, 4, 10, 4)
        search_layout.setSpacing(8)

        self.search_icon_label = QLabel("🔍", self.search_frame)
        self.search_icon_label.setObjectName("commandPaletteSearchIcon")
        search_layout.addWidget(self.search_icon_label)

        self.search_input = QLineEdit(self.search_frame)
        self.search_input.setObjectName("commandPaletteInput")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(32)
        self.search_input.installEventFilter(self)
        self.search_input.textChanged.connect(self._on_text_changed)
        search_layout.addWidget(self.search_input, 1)

        container_layout.addWidget(self.search_frame)

        # Stacked results / empty state
        self.results_stack = QStackedWidget(self.container)

        self.results_view = QListView(self.results_stack)
        self.results_view.setObjectName("commandPaletteResults")
        self.results_view.setModel(self.model)
        self.results_view.setItemDelegate(self.delegate)
        self.results_view.setMouseTracking(True)
        self.results_view.setUniformItemSizes(True)
        self.results_view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.results_view.setSelectionMode(
            QListView.SelectionMode.SingleSelection
        )
        self.results_view.setEditTriggers(
            QListView.EditTrigger.NoEditTriggers
        )
        self.results_view.clicked.connect(self._on_item_clicked)
        self.list_view = self.results_view
        self.results_stack.addWidget(self.results_view)

        self.empty_label = QLabel(self.results_stack)
        self.empty_label.setObjectName("commandPaletteEmptyLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_stack.addWidget(self.empty_label)

        container_layout.addWidget(self.results_stack, 1)

        # Footer hints
        self.footer = QFrame(self.container)
        self.footer.setObjectName("commandPaletteFooter")
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(12, 6, 12, 6)
        self.hint_label = QLabel(self.footer)
        self.hint_label.setObjectName("commandPaletteHint")
        footer_layout.addWidget(self.hint_label)
        container_layout.addWidget(self.footer)

        outer_layout.addWidget(self.container)

    def retranslateUi(self) -> None:
        self.setWindowTitle(
            QCoreApplication.translate("CommandPaletteDialog", "Command Palette")
        )
        if not hasattr(self, "search_input"):
            return
        self.search_input.setPlaceholderText(
            QCoreApplication.translate(
                "CommandPaletteDialog",
                "Search links, scripts, categories...  (> scripts, @sphere, / files)",
            )
        )
        self.empty_label.setText(
            QCoreApplication.translate(
                "CommandPaletteDialog",
                "No matching links found",
            )
        )
        self.hint_label.setText(
            QCoreApplication.translate(
                "CommandPaletteDialog",
                "Enter: Launch  •  Ctrl+Enter: Show in window  •  > scripts  @sphere  / files  •  Esc: Close",
            )
        )

    def set_results(self, items: list[dict[str, Any]]) -> None:
        """Populate results list and automatically select the first item."""
        self.model.set_items(items)
        if items:
            self.results_stack.setCurrentWidget(self.results_view)
            first_idx = self.model.index(0, 0)
            self.results_view.setCurrentIndex(first_idx)
        else:
            self.results_stack.setCurrentWidget(self.empty_label)

    def selected_link(self) -> dict[str, Any] | None:
        """Return currently highlighted link dict or None."""
        idx = self.results_view.currentIndex()
        if not idx.isValid() and self.model.rowCount() > 0:
            idx = self.model.index(0, 0)
        if idx.isValid():
            return self.model.item_at(idx.row())
        return None

    def move_selection(self, delta: int) -> None:
        """Move current selection up/down by delta rows."""
        count = self.model.rowCount()
        if count <= 0:
            return
        curr = self.results_view.currentIndex()
        curr_row = curr.row() if curr.isValid() else 0
        next_row = (curr_row + delta) % count
        next_idx = self.model.index(next_row, 0)
        self.results_view.setCurrentIndex(next_idx)
        self.results_view.scrollTo(next_idx)

    def activate_selected(self, *, reveal_in_window: bool = False) -> bool:
        """Trigger launch or reveal for the currently selected link."""
        link = self.selected_link()
        if not link:
            return False
        self.hide()
        if reveal_in_window:
            self.link_reveal_requested.emit(link)
        else:
            self.link_activated.emit(link)
        return True

    def open_palette(self) -> None:
        """Center on active screen, clear search input, and focus."""
        self._center_on_cursor_screen()
        if self.search_input.text():
            self.search_input.blockSignals(True)
            self.search_input.clear()
            self.search_input.blockSignals(False)
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_input.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def refresh_theme(self) -> None:
        """Refresh cached icons and repaint results when theme changes."""
        self.model.clear_icon_cache()
        vp = self.results_view.viewport()
        if vp is not None:
            vp.update()
        self.update()

    def _center_on_cursor_screen(self) -> None:
        try:
            screen = QGuiApplication.screenAt(QCursor.pos())
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            if screen is not None:
                avail = screen.availableGeometry()
                x = avail.x() + (avail.width() - self.width()) // 2
                y = avail.y() + max(60, int(avail.height() * 0.20))
                self.move(x, y)
        except Exception:
            logger.debug("CommandPaletteDialog: failed to center on screen", exc_info=True)

    def _on_text_changed(self, text: str) -> None:
        self.query_changed.emit(text)

    def _on_item_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        self.results_view.setCurrentIndex(index)
        modifiers = QApplication.keyboardModifiers()
        reveal = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        self.activate_selected(reveal_in_window=reveal)

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if obj is self.search_input and event is not None:
            if event.type() == QEvent.Type.KeyPress:
                key_event = event  # type: ignore[assignment]
                if isinstance(key_event, QKeyEvent):
                    key = key_event.key()
                    mods = key_event.modifiers()
                    if key == Qt.Key.Key_Down:
                        self.move_selection(1)
                        return True
                    if key == Qt.Key.Key_Up:
                        self.move_selection(-1)
                        return True
                    if key == Qt.Key.Key_PageDown:
                        self.move_selection(5)
                        return True
                    if key == Qt.Key.Key_PageUp:
                        self.move_selection(-5)
                        return True
                    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                        reveal = bool(mods & Qt.KeyboardModifier.ControlModifier)
                        self.activate_selected(reveal_in_window=reveal)
                        return True
                    if key == Qt.Key.Key_Escape:
                        self.hide()
                        return True
            elif event.type() == QEvent.Type.FocusIn:
                self.search_frame.setProperty("focused", "true")
                self._repolish(self.search_frame)
            elif event.type() == QEvent.Type.FocusOut:
                self.search_frame.setProperty("focused", "false")
                self._repolish(self.search_frame)
        return super().eventFilter(obj, event)

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        try:
            style = widget.style()
            if style is not None:
                style.unpolish(widget)
                style.polish(widget)
        except Exception:
            pass

    def changeEvent(self, event: QEvent | None) -> None:
        super().changeEvent(event)
        if event is not None and event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow() and self.isVisible():
                self.hide()
