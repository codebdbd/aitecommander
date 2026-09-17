from __future__ import annotations

import html
import logging
import os
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import QCoreApplication, QPoint, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QImageReader,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPalette,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSizeGrip,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.models.types.link_type import LinkType
from app.utils.ui.icon.icon_service import get_icon
from app.views.windows.dialogs.base_dialog import BaseDialog

logger = logging.getLogger(__name__)
_TR_CONTEXT = "QuickLookDialog"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".svg"}
TEXT_EXTENSIONS = {
    ".txt", ".py", ".json", ".md", ".bat", ".ps1", ".log",
    ".yaml", ".yml", ".ini", ".csv", ".sh", ".cmd", ".xml",
    ".html", ".css", ".js", ".ts", ".sql", ".conf", ".cfg", ".env"
}


def _format_file_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    elif num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"


class QuickLookDialog(BaseDialog):
    """macOS-style Quick Look preview dialog for links."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_open_callback=None,
        on_navigate_callback=None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("QuickLookDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.installEventFilter(self)
        self.resize(760, 520)

        self._on_open_callback = on_open_callback
        self._on_navigate_callback = on_navigate_callback
        self._current_link: Optional[dict[str, Any]] = None
        self._drag_pos: Optional[QPoint] = None

        self._setup_ui()
        self.retranslateUi()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        self._container = QFrame(self)
        self._container.setObjectName("quickLookContainer")
        
        pal = self.palette()
        bg_hex = pal.color(QPalette.ColorRole.Window).name()
        base_hex = pal.color(QPalette.ColorRole.Base).name()
        mid_hex = pal.color(QPalette.ColorRole.Mid).name()
        highlight_hex = pal.color(QPalette.ColorRole.Highlight).name()
        highlight_text_hex = pal.color(QPalette.ColorRole.HighlightedText).name()

        self._container.setStyleSheet(
            f"#quickLookContainer {{"
            f" background-color: {bg_hex};"
            f" border: 1px solid {mid_hex};"
            f" border-radius: 10px;"
            f"}}"
        )

        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(14, 12, 14, 10)
        container_layout.setSpacing(8)
        root_layout.addWidget(self._container)

        # Header
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(24, 24)
        self._icon_lbl.setScaledContents(True)
        header_layout.addWidget(self._icon_lbl)

        self._title_lbl = QLabel()
        self._title_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        header_layout.addWidget(self._title_lbl, 1)

        self._type_badge = QLabel()
        self._type_badge.setStyleSheet(
            f"background-color: {base_hex}; color: {highlight_hex};"
            f" font-size: 11px; font-weight: bold; border-radius: 4px; padding: 2px 8px;"
        )
        header_layout.addWidget(self._type_badge)

        self._open_btn = QPushButton()
        self._open_btn.setStyleSheet(
            f"QPushButton {{ background-color: {highlight_hex}; color: {highlight_text_hex}; font-weight: bold; border-radius: 4px; padding: 4px 14px; }}"
        )
        self._open_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._open_btn.clicked.connect(self._handle_open)
        header_layout.addWidget(self._open_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; font-size: 14px; border: none; border-radius: 4px; }"
            "QPushButton:hover { background-color: #e81123; color: #FFFFFF; }"
        )
        close_btn.clicked.connect(self.close)
        header_layout.addWidget(close_btn)
        container_layout.addLayout(header_layout)

        # Content Stack
        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background-color: {base_hex}; border-radius: 6px;")
        container_layout.addWidget(self._stack, 1)

        # Page 0: Image Preview
        self._image_page = QWidget()
        img_layout = QVBoxLayout(self._image_page)
        img_layout.setContentsMargins(6, 6, 6, 6)
        self._image_lbl = QLabel()
        self._image_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        img_layout.addWidget(self._image_lbl, 1)
        self._image_info_lbl = QLabel()
        self._image_info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_info_lbl.setStyleSheet("color: gray; font-size: 11px;")
        img_layout.addWidget(self._image_info_lbl)
        self._stack.addWidget(self._image_page)

        # Page 1: Text / Code Preview
        self._text_page = QWidget()
        text_layout = QVBoxLayout(self._text_page)
        text_layout.setContentsMargins(4, 4, 4, 4)
        self._text_edit = QPlainTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setFont(QFont("Consolas", 10))
        self._text_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._text_edit.setStyleSheet("QPlainTextEdit { border: none; }")
        text_layout.addWidget(self._text_edit, 1)
        self._text_info_lbl = QLabel()
        self._text_info_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._text_info_lbl.setStyleSheet("color: gray; font-size: 11px; padding: 2px 6px;")
        text_layout.addWidget(self._text_info_lbl)
        self._stack.addWidget(self._text_page)

        # Page 2: Folder Content List
        self._folder_page = QWidget()
        folder_layout = QVBoxLayout(self._folder_page)
        folder_layout.setContentsMargins(6, 6, 6, 6)
        self._folder_list = QListWidget()
        self._folder_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._folder_list.setStyleSheet("QListWidget { border: none; font-size: 12px; }")
        folder_layout.addWidget(self._folder_list, 1)
        self._folder_info_lbl = QLabel()
        self._folder_info_lbl.setStyleSheet("color: gray; font-size: 11px;")
        folder_layout.addWidget(self._folder_info_lbl)
        self._stack.addWidget(self._folder_page)

        # Page 3: Generic / Web / Program Card
        self._card_page = QWidget()
        card_layout = QVBoxLayout(self._card_page)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(12)
        self._card_icon_lbl = QLabel()
        self._card_icon_lbl.setFixedSize(64, 64)
        self._card_icon_lbl.setScaledContents(True)
        self._card_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self._card_icon_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        self._card_desc_lbl = QLabel()
        self._card_desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._card_desc_lbl.setWordWrap(True)
        self._card_desc_lbl.setStyleSheet("font-size: 13px; line-height: 1.4;")
        card_layout.addWidget(self._card_desc_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._card_page)

        # Footer
        footer_layout = QHBoxLayout()
        self._path_lbl = QLabel()
        self._path_lbl.setStyleSheet("color: gray; font-size: 11px;")
        self._path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        footer_layout.addWidget(self._path_lbl, 1)

        self._hints_lbl = QLabel()
        self._hints_lbl.setStyleSheet("color: gray; font-size: 10px;")
        footer_layout.addWidget(self._hints_lbl)
        container_layout.addLayout(footer_layout)

    def retranslateUi(self) -> None:
        if not hasattr(self, "_open_btn") or not hasattr(self, "_hints_lbl"):
            return
        self._open_btn.setText(_tr("Open"))
        self._hints_lbl.setText(
            _tr("Space / Esc: Close  •  Enter: Open  •  ↑ / ↓: Navigate")
        )

    def set_link(self, link: dict[str, Any]) -> None:
        self._current_link = link
        name = str(link.get("name") or _tr("Untitled"))
        url = str(link.get("url") or "").strip()
        raw_type = link.get("type") or "web"
        link_type = LinkType.from_value(raw_type)
        icon_name = link.get("icon")

        self._title_lbl.setText(name)
        self._path_lbl.setText(url)
        self._type_badge.setText(link_type.value.upper())

        qicon = get_icon(icon_name) if icon_name else QIcon()
        if qicon and not qicon.isNull():
            self._icon_lbl.setPixmap(qicon.pixmap(24, 24))
        else:
            self._icon_lbl.clear()

        if link_type == LinkType.FILE:
            self._render_file_preview(url, name, qicon)
        elif link_type == LinkType.FOLDER:
            self._render_folder_preview(url, name)
        elif link_type == LinkType.SCRIPT:
            self._render_script_preview(url, link)
        elif link_type == LinkType.PROGRAM:
            self._render_program_preview(url, link, qicon)
        else:
            self._render_web_preview(url, link, qicon)

    def _render_file_preview(self, path_str: str, name: str, qicon: QIcon) -> None:
        path = Path(path_str)
        if not path.exists():
            not_found = _tr("File not found on disk:")
            self._render_generic_card(
                qicon,
                f"<b>{html.escape(name)}</b><br><br><span style='color: #ff6b6b;'>{not_found}</span><br>{html.escape(path_str)}",
            )
            return

        ext = path.suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            reader = QImageReader(path_str)
            reader.setAutoTransform(True)
            orig_sz = reader.size()
            if orig_sz.isValid():
                target_sz = self._image_page.size() - QSize(20, 40)
                if orig_sz.width() > target_sz.width() or orig_sz.height() > target_sz.height():
                    reader.setScaledSize(orig_sz.scaled(target_sz, Qt.AspectRatioMode.KeepAspectRatio))
                img = reader.read()
                if not img.isNull():
                    pix = QPixmap.fromImage(img)
                    self._stack.setCurrentWidget(self._image_page)
                    self._image_lbl.setPixmap(pix)
                    sz_str = _format_file_size(path.stat().st_size)
                    self._image_info_lbl.setText(
                        f"{orig_sz.width()} × {orig_sz.height()} px  •  {sz_str}  •  {ext.upper().lstrip('.')}"
                    )
                    return

        if ext in TEXT_EXTENSIONS:
            try:
                with open(path, "rb") as f:
                    chunk = f.read(65536)
                text = chunk.decode("utf-8", errors="replace")
                self._stack.setCurrentWidget(self._text_page)
                self._text_edit.setPlainText(text)
                sz_str = _format_file_size(path.stat().st_size)
                lines_count = text.count("\n") + 1
                self._text_info_lbl.setText(
                    f"{_tr('Lines')}: ~{lines_count}  •  {_tr('Size')}: {sz_str}  •  UTF-8"
                )
                return
            except Exception as e:
                logger.debug("Failed to read text file %s: %s", path_str, e)

        sz_str = _format_file_size(path.stat().st_size)
        info_html = (
            f"<b>{html.escape(name)}</b><br><br>"
            f"{_tr('Size')}: {sz_str}<br>"
            f"{_tr('Type')}: {ext.upper().lstrip('.') or _tr('File')}<br>"
            f"{_tr('Path')}: {html.escape(path_str)}"
        )
        self._render_generic_card(qicon, info_html)

    def _render_folder_preview(self, path_str: str, name: str) -> None:
        path = Path(path_str)
        if not path.exists() or not path.is_dir():
            not_found = _tr("Folder not found:")
            self._render_generic_card(
                QIcon(),
                f"<b>{html.escape(name)}</b><br><br><span style='color: #ff6b6b;'>{not_found}</span><br>{html.escape(path_str)}",
            )
            return

        self._folder_list.clear()
        items_count = 0
        try:
            with os.scandir(path) as it:
                for entry in it:
                    items_count += 1
                    if items_count <= 40:
                        prefix = "📁 " if entry.is_dir() else "📄 "
                        size_part = (
                            f" ({_format_file_size(entry.stat().st_size)})"
                            if entry.is_file()
                            else ""
                        )
                        self._folder_list.addItem(
                            QListWidgetItem(f"{prefix}{entry.name}{size_part}")
                        )
                    if items_count > 500:
                        break
        except Exception as e:
            self._folder_list.addItem(QListWidgetItem(f"{_tr('Access error')}: {e}"))

        self._folder_info_lbl.setText(f"{_tr('Total items in root')}: {items_count}")
        self._stack.setCurrentWidget(self._folder_page)

    def _render_script_preview(self, path_str: str, link: dict[str, Any]) -> None:
        path = Path(path_str)
        cmd_args = link.get("cmd_args") or ""
        work_dir = link.get("work_dir") or ""

        if path.exists() and path.is_file():
            try:
                with open(path, "rb") as f:
                    chunk = f.read(65536)
                code = chunk.decode("utf-8", errors="replace")
                self._stack.setCurrentWidget(self._text_page)
                self._text_edit.setPlainText(code)
                self._text_info_lbl.setText(
                    f"{_tr('Script')}: {path.name}  •  {_tr('Arguments')}: {cmd_args or _tr('None')}"
                )
                return
            except Exception:
                pass

        info_html = (
            f"<b>{html.escape(str(link.get('name')))}</b><br><br>"
            f"{_tr('Script')}: {html.escape(path_str)}<br>"
            f"{_tr('Arguments')}: {html.escape(str(cmd_args)) or '—'}<br>"
            f"{_tr('Working Directory')}: {html.escape(str(work_dir)) or '—'}"
        )
        self._render_generic_card(QIcon(), info_html)

    def _render_program_preview(
        self, path_str: str, link: dict[str, Any], qicon: QIcon
    ) -> None:
        cmd_args = link.get("cmd_args") or ""
        work_dir = link.get("work_dir") or ""
        info_html = (
            f"<b>{html.escape(str(link.get('name')))}</b><br><br>"
            f"{_tr('Program')}: {html.escape(path_str)}<br>"
            f"{_tr('Arguments')}: {html.escape(str(cmd_args)) or '—'}<br>"
            f"{_tr('Working Directory')}: {html.escape(str(work_dir)) or '—'}"
        )
        self._render_generic_card(qicon, info_html)

    def _render_web_preview(self, url: str, link: dict[str, Any], qicon: QIcon) -> None:
        profile = link.get("browser_profile") or ""
        notes = link.get("notes") or ""
        info_html = (
            f"<b>{html.escape(str(link.get('name')))}</b><br><br>"
            f"URL: <span style='color: #7cb7ff;'>{html.escape(url)}</span><br>"
            f"{_tr('Profile')}: {html.escape(str(profile)) or _tr('Default')}"
        )
        if notes:
            info_html += f"<br><br>{_tr('Notes')}: <i>{html.escape(str(notes))}</i>"
        self._render_generic_card(qicon, info_html)

    def _render_generic_card(self, qicon: QIcon, text_html: str) -> None:
        if qicon and not qicon.isNull():
            self._card_icon_lbl.setPixmap(qicon.pixmap(64, 64))
            self._card_icon_lbl.setVisible(True)
        else:
            self._card_icon_lbl.setVisible(False)
        self._card_desc_lbl.setText(text_html)
        self._stack.setCurrentWidget(self._card_page)

    def _handle_open(self) -> None:
        if self._on_open_callback and self._current_link:
            self._on_open_callback(self._current_link)
        self.close()

    def eventFilter(self, obj, event) -> bool:
        if event.type() == event.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Space, Qt.Key.Key_Escape):
                self.close()
                return True
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._handle_open()
                return True
            elif key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                if self._on_navigate_callback:
                    self._on_navigate_callback(1 if key == Qt.Key.Key_Down else -1)
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Escape):
            self.close()
            event.accept()
            return
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._handle_open()
            event.accept()
            return
        elif key == Qt.Key.Key_Down:
            if self._on_navigate_callback:
                self._on_navigate_callback(1)
            event.accept()
            return
        elif key == Qt.Key.Key_Up:
            if self._on_navigate_callback:
                self._on_navigate_callback(-1)
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        if self.parent() and hasattr(self.parent(), "table"):
            table = self.parent().table
            if table:
                table.setFocus()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None
        event.accept()
