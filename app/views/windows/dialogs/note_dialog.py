"""Distraction-free, full-screen Zen viewer and editor for notes."""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import (
    QCloseEvent,
    QFont,
    QIcon,
    QKeyEvent,
    QMouseEvent,
    QTextBlockFormat,
    QTextCursor,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMenu,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.controllers.ui.theme_controller import theme_registry
from app.utils.i18n.common import tr as tr_common
from app.utils.ui.icon.icon_operations.creators import _create_tinted_svg_icon
from app.utils.ui.icon.path_service import icon_path_service
from app.views.windows.dialogs.base_dialog import BaseDialog


class _ExitZoneWidget(QWidget):
    """Side exit zone widget matching AiteBar LeftExitZone/RightExitZone."""

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setStyleSheet("background: transparent;")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class NoteDialog(BaseDialog):
    """Distraction-free, full-screen Zen viewer and editor for notes."""

    def __init__(
        self,
        initial_text: str = "",
        title: str = "",
        parent: QWidget | None = None,
    ) -> None:
        self._notes_text = str(initial_text or "")
        self._title = str(title or "")
        self.notes_te: QTextEdit | None = None
        self.center_container: QWidget | None = None

        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        )
        target_screen = (
            parent.screen()
            if parent and hasattr(parent, "screen") and parent.screen()
            else QApplication.primaryScreen()
        )

        # Match AiteBar Zen themes: Paper (#F4F0E7/#282622) for light, Graphite (#1E2023/#E4E2DC) for dark
        self.setAutoFillBackground(True)
        current_theme_id = app_config.get("theme", "dark")
        theme = theme_registry.get_theme(current_theme_id)
        if theme and theme.is_dark:
            self._zen_bg = "#1E2023"
            self._zen_fg = "#E4E2DC"
            self._zen_sel = "#41474D"
            self._zen_sel_fg = "#FFFFFF"
        else:
            self._zen_bg = "#F4F0E7"
            self._zen_fg = "#282622"
            self._zen_sel = "#D8D0C2"
            self._zen_sel_fg = "#1F1D1A"
        self.setStyleSheet(f"QDialog {{ background-color: {self._zen_bg}; }}")

        self._init_ui()
        self.retranslateUi()

        if target_screen is not None:
            self.setGeometry(target_screen.geometry())
        self.showFullScreen()

    def get_notes_text(self) -> str:
        """Return the current notes text stripped of outer whitespace."""
        if self.notes_te is not None:
            return self.notes_te.toPlainText().strip()
        return self._notes_text.strip()

    def _init_ui(self) -> None:
        """Initialize full-screen Zen layout with centered 760px text column."""
        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.left_exit_zone = _ExitZoneWidget(self)
        self.left_exit_zone.clicked.connect(self._save_and_close)
        outer_layout.addWidget(self.left_exit_zone, 1)

        outer_layout.addSpacing(48)

        self.center_container = QWidget(self)
        target_screen = (
            self.parent().screen()
            if self.parent() and hasattr(self.parent(), "screen") and self.parent().screen()
            else (self.screen() or QApplication.primaryScreen())
        )
        screen_geo = target_screen.availableGeometry() if target_screen else QRect(0, 0, 1920, 1080)
        screen_h = screen_geo.height()
        self.center_container.setFixedWidth(760)

        top_margin = int(screen_h * 0.18)
        bottom_margin = 32
        col_layout = QVBoxLayout(self.center_container)
        col_layout.setContentsMargins(0, top_margin, 0, bottom_margin)
        col_layout.setSpacing(0)

        self.notes_te = QTextEdit(self.center_container)
        self.notes_te.setFrameShape(QTextEdit.Shape.NoFrame)
        self.notes_te.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.notes_te.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.notes_te.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.notes_te.setCursorWidth(2)
        self.notes_te.setStyleSheet(
            f"QTextEdit {{ font-size: 20px; background: transparent; border: none; padding: 0px; color: {self._zen_fg}; "
            f"selection-background-color: {self._zen_sel}; selection-color: {self._zen_sel_fg}; }}"
        )
        read_font = QFont(QApplication.font())
        read_font.setPixelSize(20)
        self.notes_te.setFont(read_font)
        self.notes_te.document().setDefaultFont(read_font)
        self.notes_te.document().setDefaultStyleSheet(
            f"body, p, div, span, li {{ font-size: 20px; color: {self._zen_fg}; }}"
        )

        raw_notes = self._notes_text
        if "<html" in raw_notes.lower() or "<!doctype" in raw_notes.lower():
            temp = QTextDocument()
            temp.setHtml(raw_notes)
            clean_notes = temp.toPlainText().strip()
            self.notes_te.setPlainText(clean_notes)
        else:
            self.notes_te.setPlainText(raw_notes)

        self._apply_typography()

        self.notes_te.textChanged.connect(self._on_text_changed)
        self.notes_te.installEventFilter(self)

        col_layout.addWidget(self.notes_te)
        outer_layout.addWidget(self.center_container)
        outer_layout.addSpacing(48)

        self.right_exit_zone = _ExitZoneWidget(self)
        self.right_exit_zone.clicked.connect(self._save_and_close)
        outer_layout.addWidget(self.right_exit_zone, 1)

    def _apply_typography(self) -> None:
        """Apply uniform Zen reading typography: 150% line height and 15px paragraph spacing (exact AiteBar formula)."""
        if self.notes_te is None:
            return
        doc = self.notes_te.document()
        block = doc.firstBlock()
        while block.isValid():
            cursor = QTextCursor(block)
            bf = QTextBlockFormat()
            bf.setLineHeight(30.0, int(QTextBlockFormat.LineHeightTypes.FixedHeight.value))
            bf.setTopMargin(0.0)
            bf.setBottomMargin(15.0)
            cursor.mergeBlockFormat(bf)
            block = block.next()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        target_screen = self.screen() or QApplication.primaryScreen()
        if target_screen is not None:
            self.setGeometry(target_screen.geometry())
        if not self.isFullScreen():
            self.showFullScreen()
        if self.notes_te is not None:
            self.notes_te.setFocus()
            cursor = self.notes_te.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.notes_te.setTextCursor(cursor)
            self.notes_te.verticalScrollBar().setValue(0)

    def retranslateUi(self) -> None:
        self.setWindowTitle(self._title or tr_common("Notes"))
        if self.notes_te is not None:
            self.notes_te.setPlaceholderText(self.tr("Enter notes here..."))

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ensure notes are saved on window close (e.g. Alt+F4)."""
        self._save_and_close()
        event.accept()

    def _on_text_changed(self) -> None:
        """Autosave note to memory on every change."""
        if self.notes_te is not None:
            self._notes_text = self.notes_te.toPlainText().strip()

    def _save_and_close(self) -> None:
        """Persist notes and close dialog."""
        if self.notes_te is not None:
            self._notes_text = self.notes_te.toPlainText().strip()
        self.accept()

    def eventFilter(self, obj, event) -> bool:
        """Intercept shortcuts and wheel zoom on editor."""
        if obj is self.notes_te:
            if event.type() == QEvent.Type.KeyPress:
                key = event.key()
                mods = event.modifiers()
                if key == Qt.Key.Key_Tab and mods == Qt.KeyboardModifier.NoModifier:
                    self.notes_te.insertPlainText("    ")
                    return True
                if key in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
                    self._save_and_close()
                    return True
                if mods == Qt.KeyboardModifier.ControlModifier:
                    if key in (
                        Qt.Key.Key_Return,
                        Qt.Key.Key_Enter,
                        Qt.Key.Key_W,
                        Qt.Key.Key_N,
                        Qt.Key.Key_S,
                    ):
                        self._save_and_close()
                        return True
                    if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                        self._zoom_in()
                        return True
                    if key == Qt.Key.Key_Minus:
                        self._zoom_out()
                        return True
                    if key == Qt.Key.Key_0:
                        self._reset_zoom()
                        return True

            elif event.type() == QEvent.Type.Wheel:
                if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                    delta = event.angleDelta().y()
                    if delta > 0:
                        self._zoom_in()
                    elif delta < 0:
                        self._zoom_out()
                    return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle escape and fullscreen keys from dialog background."""
        key = event.key()
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
            self._save_and_close()
            return
        super().keyPressEvent(event)

    def _zoom_in(self) -> None:
        if self.notes_te is not None:
            self.notes_te.zoomIn(1)

    def _zoom_out(self) -> None:
        if self.notes_te is not None:
            self.notes_te.zoomOut(1)

    def _reset_zoom(self) -> None:
        if self.notes_te is not None:
            read_font = QFont(QApplication.font())
            read_font.setPixelSize(20)
            self.notes_te.setFont(read_font)
            self.notes_te.document().setDefaultFont(read_font)
            self._apply_typography()

    def _get_action_icon(self, icon_name: str) -> QIcon:
        """Resolve and tint icon for context menu action."""
        p = icon_path_service.get_ui_icon_path(icon_name)
        if not p or not p.exists():
            return QIcon()
        try:
            current_theme_id = app_config.get("theme", "dark")
            theme = theme_registry.get_theme(current_theme_id)
            icon_color = "#FFFFFF" if (theme and theme.is_dark) else "#1F2430"
            return _create_tinted_svg_icon(str(p), icon_color)
        except Exception:
            return QIcon(str(p))

    def _show_context_menu(self, widget: QWidget, pos: QPoint) -> None:
        """Build and show context menu for notes editor."""
        if self.notes_te is None:
            return

        menu = QMenu(self)
        self._context_menus.append(menu)

        # Undo / Redo
        doc = self.notes_te.document()
        act_undo = menu.addAction(
            self._get_action_icon("undo.svg"),
            self.tr("Undo"),
            self.notes_te.undo,
        )
        act_undo.setShortcut("Ctrl+Z")
        act_undo.setEnabled(doc.isUndoAvailable())

        act_redo = menu.addAction(
            self._get_action_icon("redo.svg"),
            self.tr("Redo"),
            self.notes_te.redo,
        )
        act_redo.setShortcut("Ctrl+Y")
        act_redo.setEnabled(doc.isRedoAvailable())

        menu.addSeparator()

        # Clipboard actions
        cursor = self.notes_te.textCursor()
        has_sel = cursor.hasSelection()

        act_cut = menu.addAction(
            self._get_action_icon("cut.svg"),
            self.tr("Cut"),
            self.notes_te.cut,
        )
        act_cut.setShortcut("Ctrl+X")
        act_cut.setEnabled(has_sel)

        act_copy = menu.addAction(
            self._get_action_icon("copy.svg"),
            self.tr("Copy"),
            self.notes_te.copy,
        )
        act_copy.setShortcut("Ctrl+C")
        act_copy.setEnabled(has_sel)

        act_paste = menu.addAction(
            self._get_action_icon("paste.svg"),
            self.tr("Paste"),
            self.notes_te.paste,
        )
        act_paste.setShortcut("Ctrl+V")
        clipboard = QApplication.clipboard()
        act_paste.setEnabled(bool(clipboard and clipboard.text()))

        act_sel_all = menu.addAction(
            self._get_action_icon("select_all.svg"),
            self.tr("Select All"),
            self.notes_te.selectAll,
        )
        act_sel_all.setShortcut("Ctrl+A")

        menu.addSeparator()

        # Note actions
        menu.addAction(
            self._get_action_icon("copy.svg"),
            self.tr("Copy All Text"),
            self._copy_all_text,
        )

        act_clear = menu.addAction(
            self._get_action_icon("clear_note.svg"),
            self.tr("Clear Note"),
            self._clear_note,
        )
        act_clear.setEnabled(bool(self.notes_te.toPlainText().strip()))

        menu.addSeparator()

        # Close
        act_close = menu.addAction(
            self._get_action_icon("exit.svg"),
            self.tr("Close"),
            self._save_and_close,
        )
        act_close.setShortcut("Esc")
        menu.exec(widget.mapToGlobal(pos))

    def _copy_all_text(self) -> None:
        if self.notes_te is not None:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(self.notes_te.toPlainText())

    def _clear_note(self) -> None:
        if self.notes_te is not None:
            self.notes_te.clear()
