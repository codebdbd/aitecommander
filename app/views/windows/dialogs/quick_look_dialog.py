from __future__ import annotations

import base64
import csv
import html
import logging
import os
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import QCoreApplication, QFileInfo, QPoint, QPointF, QRect, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QImage,
    QImageReader,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPalette,
    QPixmap,
    QShortcut,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextOption,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFileIconProvider,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSizeGrip,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtPdf import QPdfDocument
    from PyQt6.QtPdfWidgets import QPdfView
    _HAS_PDF = True
except ImportError:
    _HAS_PDF = False

try:
    from PIL import Image, PsdImagePlugin
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

from app.core.hotkey_manager import HotkeyManager
from app.models.types.link_type import LinkType
from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.icon_service import get_icon
from app.utils.ui.icon.path_service import get_current_theme
from app.utils.ui.menu_builders.base import get_menu_icon
from app.views.windows.dialogs.base_dialog import BaseDialog

logger = logging.getLogger(__name__)
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


_DARK_PREVIEW_QSS = """
#QuickLookDialog {
    background-color: #1e1e1e;
    color: #e0e0e0;
}
#QuickLookDialog QTableWidget {
    background-color: #1e1e1e;
    alternate-background-color: #252526;
    color: #e0e0e0;
    gridline-color: #333333;
    border: none;
    selection-background-color: #264f78;
    selection-color: #ffffff;
}
#QuickLookDialog QTableWidget::item:selected {
    background-color: #264f78;
    color: #ffffff;
}
#QuickLookDialog QHeaderView::section {
    background-color: #2d2d2d;
    color: #cccccc;
    padding: 4px 8px;
    border: 1px solid #383838;
    font-weight: 600;
}
#QuickLookDialog QTableCornerButton::section {
    background-color: #2d2d2d;
    border: 1px solid #383838;
}
#QuickLookDialog QTextEdit {
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 13pt;
    background-color: #1e1e1e;
    color: #e0e0e0;
    border: none;
    selection-background-color: #264f78;
    selection-color: #ffffff;
}
#QuickLookDialog QListWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    border: none;
    selection-background-color: #264f78;
    selection-color: #ffffff;
}
#QuickLookDialog QListWidget::item:selected {
    background-color: #264f78;
    color: #ffffff;
}
#QuickLookDialog QPushButton {
    padding: 3px 12px;
}
#QuickLookDialog QPushButton#pdf_nav_btn {
    background-color: transparent;
    border: 1px solid rgba(140, 140, 140, 0.35);
    border-radius: 3px;
    padding: 0px;
    margin: 0px;
}
#QuickLookDialog QPushButton#pdf_nav_btn:hover {
    background-color: rgba(140, 140, 140, 0.2);
    border-color: rgba(140, 140, 140, 0.6);
}
#QuickLookDialog QPushButton#pdf_nav_btn:pressed {
    background-color: rgba(140, 140, 140, 0.35);
}
#QuickLookDialog QPushButton#pdf_nav_btn:disabled {
    border-color: rgba(140, 140, 140, 0.15);
    opacity: 0.3;
}
QMenu {
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    background-color: #252B35;
    color: #D1D6E0;
    border: 1px solid #3A3E44;
    border-radius: 0;
    padding: 0;
}
QMenu::item {
    background-color: transparent;
    color: #D1D6E0;
    padding: 0 12px 0 16px;
    margin: 0;
    border-radius: 0;
}
QMenu::icon {
    padding-left: 16px;
}
QMenu::item:selected {
    background-color: #2E4066;
    color: #FFFFFF;
}
QMenu::item:disabled {
    color: #5A6372;
    background: transparent;
}
QMenu::separator {
    height: 1px;
    background-color: #3A3E44;
    margin: 0;
    padding: 0;
}
"""

_LIGHT_PREVIEW_QSS = """
#QuickLookDialog {
    background-color: #ffffff;
    color: #1a1a1a;
}
#QuickLookDialog QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f7f9fa;
    color: #1a1a1a;
    gridline-color: #e1e4e8;
    border: none;
    selection-background-color: #cce8ff;
    selection-color: #000000;
}
#QuickLookDialog QTableWidget::item:selected {
    background-color: #cce8ff;
    color: #000000;
}
#QuickLookDialog QHeaderView::section {
    background-color: #f0f2f5;
    color: #333333;
    padding: 4px 8px;
    border: 1px solid #dcdfe4;
    font-weight: 600;
}
#QuickLookDialog QTableCornerButton::section {
    background-color: #f0f2f5;
    border: 1px solid #dcdfe4;
}
#QuickLookDialog QTextEdit {
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 13pt;
    background-color: #ffffff;
    color: #1a1a1a;
    border: none;
    selection-background-color: #cce8ff;
    selection-color: #000000;
}
#QuickLookDialog QListWidget {
    background-color: #ffffff;
    color: #1a1a1a;
    border: none;
    selection-background-color: #cce8ff;
    selection-color: #000000;
}
#QuickLookDialog QListWidget::item:selected {
    background-color: #cce8ff;
    color: #000000;
}
#QuickLookDialog QPushButton {
    padding: 3px 12px;
}
#QuickLookDialog QPushButton#pdf_nav_btn {
    background-color: transparent;
    border: 1px solid rgba(140, 140, 140, 0.35);
    border-radius: 3px;
    padding: 0px;
    margin: 0px;
}
#QuickLookDialog QPushButton#pdf_nav_btn:hover {
    background-color: rgba(140, 140, 140, 0.2);
    border-color: rgba(140, 140, 140, 0.6);
}
#QuickLookDialog QPushButton#pdf_nav_btn:pressed {
    background-color: rgba(140, 140, 140, 0.35);
}
#QuickLookDialog QPushButton#pdf_nav_btn:disabled {
    border-color: rgba(140, 140, 140, 0.15);
    opacity: 0.3;
}
QMenu {
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    background-color: #FAFCFF;
    color: #333333;
    border: 1px solid #B3B3B3;
    border-radius: 0;
    padding: 0;
}
QMenu::item {
    background-color: transparent;
    color: #333333;
    padding: 0 12px 0 16px;
    margin: 0;
    border-radius: 0;
}
QMenu::icon {
    padding-left: 16px;
}
QMenu::item:selected {
    background-color: #E6E6E6;
    color: #000000;
}
QMenu::item:disabled {
    color: #999999;
    background: transparent;
}
QMenu::separator {
    height: 1px;
    background-color: #B3B3B3;
    margin: 0;
    padding: 0;
}
"""


class QuickLookDialog(BaseDialog):
    """macOS-style Quick Look preview dialog for links."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_open_callback=None,
        on_navigate_callback=None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint,
        )
        self.setObjectName("QuickLookDialog")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.installEventFilter(self)
        self.resize(760, 540)
        self.setMinimumSize(740, 480)
        self._normal_size = QSize(760, 540)
        self._normal_geometry: Optional[QRect] = None

        self._on_open_callback = on_open_callback
        self._on_navigate_callback = on_navigate_callback
        self._current_link: Optional[dict[str, Any]] = None
        self._current_orig_image: Optional[QPixmap] = None
        self._image_zoom: float = 1.0
        self._is_prose_mode: bool = True

        self._sc_reveal_en = QShortcut(
            QKeySequence(Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_E), self
        )
        self._sc_reveal_en.setContext(Qt.ShortcutContext.WindowShortcut)
        self._sc_reveal_en.activated.connect(self._handle_reveal_in_explorer)

        self._setup_ui()
        self.retranslateUi()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        # Content Stack
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent; border: none;")
        self._stack.setMinimumHeight(380)
        self._stack.setMinimumWidth(700)
        root_layout.addWidget(self._stack, 1)

        # Page 0: Image Preview
        self._image_page = QWidget()
        img_layout = QVBoxLayout(self._image_page)
        img_layout.setContentsMargins(4, 4, 4, 4)
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
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)

        self._text_edit = QTextEdit()
        self._text_edit.setFont(QFont("Segoe UI", 13))
        self._text_edit.setReadOnly(True)
        self._text_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._text_edit.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self._text_edit.installEventFilter(self)
        self._text_edit.viewport().installEventFilter(self)
        text_layout.addWidget(self._text_edit, 1)
        self._stack.addWidget(self._text_page)

        # Page: PDF Preview
        if _HAS_PDF:
            self._pdf_doc = QPdfDocument(self)
            self._pdf_view = QPdfView(self)
            self._pdf_view.setDocument(self._pdf_doc)
            self._pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
            self._pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
            self._pdf_view.setZoomFactor(1.44)
            self._pdf_view.installEventFilter(self)
            if hasattr(self._pdf_view, "viewport") and self._pdf_view.viewport():
                self._pdf_view.viewport().installEventFilter(self)
            self._pdf_view.pageNavigator().currentPageChanged.connect(self._on_pdf_page_changed)
            self._stack.addWidget(self._pdf_view)
        else:
            self._pdf_doc = None
            self._pdf_view = None

        # Page: Table Preview (.xlsx, .csv)
        self._table_view = QTableWidget()
        self._table_view.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table_view.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._table_view.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self._table_view.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self._table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table_view.customContextMenuRequested.connect(self._show_table_context_menu)
        self._table_view.installEventFilter(self)
        self._table_view.viewport().installEventFilter(self)
        self._table_view.setAlternatingRowColors(True)
        self._table_view.setShowGrid(True)
        self._table_view.horizontalHeader().setStretchLastSection(True)
        self._table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._stack.addWidget(self._table_view)

        # Page 2: Folder Content List
        self._folder_page = QWidget()
        folder_layout = QVBoxLayout(self._folder_page)
        folder_layout.setContentsMargins(4, 4, 4, 4)
        self._folder_list = QListWidget()
        self._folder_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._folder_list.installEventFilter(self)
        self._folder_list.viewport().installEventFilter(self)
        folder_layout.addWidget(self._folder_list, 1)
        self._folder_info_lbl = QLabel()
        self._folder_info_lbl.setStyleSheet("color: gray; font-size: 11px;")
        folder_layout.addWidget(self._folder_info_lbl)
        self._stack.addWidget(self._folder_page)

        # Page 3: Generic / Web / Program Card
        self._card_page = QWidget()
        outer_card_layout = QVBoxLayout(self._card_page)
        outer_card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._card_box = QFrame()
        self._card_box.setStyleSheet(
            "background-color: rgba(128, 128, 128, 0.08);"
            " border: 1px solid rgba(128, 128, 128, 0.2);"
            " border-radius: 0px;"
        )
        self._card_box.setMinimumWidth(380)
        self._card_box.setMaximumWidth(560)
        card_layout = QVBoxLayout(self._card_box)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(14)

        self._card_icon_lbl = QLabel()
        self._card_icon_lbl.setFixedSize(64, 64)
        self._card_icon_lbl.setScaledContents(True)
        self._card_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self._card_icon_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        self._card_desc_lbl = QLabel()
        self._card_desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._card_desc_lbl.setWordWrap(True)
        self._card_desc_lbl.setStyleSheet("font-size: 13px; line-height: 1.5; border: none; background: transparent;")
        card_layout.addWidget(self._card_desc_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        self._reveal_btn = QPushButton(self.tr("Show in Explorer"))
        self._reveal_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._reveal_btn.clicked.connect(self._handle_reveal_in_explorer)
        self._reveal_btn.setToolTip(self.tr("Show in Explorer (Ctrl+E)"))
        card_layout.addWidget(self._reveal_btn, 0, Qt.AlignmentFlag.AlignCenter)

        outer_card_layout.addWidget(self._card_box, 0, Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._card_page)

        # Footer (Actions & Path)
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(8)

        self._footer_icon_lbl = QLabel()
        self._footer_icon_lbl.setFixedSize(16, 16)
        self._footer_icon_lbl.setScaledContents(True)
        footer_layout.addWidget(self._footer_icon_lbl)

        self._path_lbl = QLabel()
        self._path_lbl.setMinimumWidth(0)
        self._path_lbl.setStyleSheet("color: gray; font-size: 11px;")
        self._path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        footer_layout.addWidget(self._path_lbl, 1)

        # PDF Page Navigation controls
        self._pdf_nav_widget = QWidget()
        pdf_nav_layout = QHBoxLayout(self._pdf_nav_widget)
        pdf_nav_layout.setContentsMargins(0, 0, 0, 0)
        pdf_nav_layout.setSpacing(4)
        self._pdf_prev_btn = QPushButton()
        self._pdf_prev_btn.setObjectName("pdf_nav_btn")
        self._pdf_prev_btn.setFixedSize(22, 22)
        self._pdf_prev_btn.setIconSize(QSize(12, 12))
        self._pdf_prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pdf_prev_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pdf_prev_btn.clicked.connect(self._pdf_prev_page)
        self._pdf_prev_btn.setToolTip(self.tr("Previous Page"))
        self._pdf_page_lbl = QLabel("1 / 1")
        self._pdf_page_lbl.setStyleSheet("font-size: 11px; opacity: 0.8;")
        self._pdf_next_btn = QPushButton()
        self._pdf_next_btn.setObjectName("pdf_nav_btn")
        self._pdf_next_btn.setFixedSize(22, 22)
        self._pdf_next_btn.setIconSize(QSize(12, 12))
        self._pdf_next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pdf_next_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pdf_next_btn.clicked.connect(self._pdf_next_page)
        self._pdf_next_btn.setToolTip(self.tr("Next Page"))
        pdf_nav_layout.addWidget(self._pdf_prev_btn)
        pdf_nav_layout.addWidget(self._pdf_page_lbl)
        pdf_nav_layout.addWidget(self._pdf_next_btn)
        self._pdf_nav_widget.setVisible(False)
        footer_layout.addWidget(self._pdf_nav_widget)

        self._text_info_lbl = QLabel()
        self._text_info_lbl.setStyleSheet("color: gray; font-size: 11px;")
        footer_layout.addWidget(self._text_info_lbl)

        self._copy_btn = QPushButton(self.tr("Copy Path"))
        self._copy_btn.setFixedHeight(26)
        self._copy_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._copy_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._copy_btn.clicked.connect(self._handle_copy_path)
        footer_layout.addWidget(self._copy_btn)

        self._reveal_footer_btn = QPushButton(self.tr("Open in Explorer"))
        self._reveal_footer_btn.setFixedHeight(26)
        self._reveal_footer_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._reveal_footer_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._reveal_footer_btn.setToolTip(self.tr("Open in Explorer (Ctrl+E)"))
        self._reveal_footer_btn.clicked.connect(self._handle_reveal_in_explorer)
        footer_layout.addWidget(self._reveal_footer_btn)

        self._open_btn = QPushButton()
        self._open_btn.setFixedHeight(26)
        self._open_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._open_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._open_btn.clicked.connect(self._handle_open)
        footer_layout.addWidget(self._open_btn)

        root_layout.addLayout(footer_layout)

    def _handle_reveal_in_explorer(self) -> None:
        if not self._current_link:
            return
        url_val = self._current_link.get("url") or self._current_link.get("path") or ""
        path_str = str(url_val).strip().strip('"\'')
        if path_str.startswith("file:///"):
            path_str = path_str[8:]
        p = Path(path_str)
        if p.exists():
            import sys
            try:
                if sys.platform == "win32":
                    subprocess.Popen(["explorer.exe", f"/select,{p.resolve()}"])
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", "-R", str(p.resolve())])
                else:
                    target_dir = p if p.is_dir() else p.parent
                    subprocess.Popen(["xdg-open", str(target_dir.resolve())])
            except Exception as e:
                logger.warning("Failed to reveal in explorer: %s", e)

    def _handle_copy_path(self) -> None:
        if self._current_link:
            url = str(self._current_link.get("url") or "").strip()
            if url:
                QApplication.clipboard().setText(url)

    def _toggle_fullscreen(self) -> None:
        if self.isMaximized() or self.isFullScreen():
            self.showNormal()
            if self._normal_geometry:
                self.setGeometry(self._normal_geometry)
            else:
                self.resize(self._normal_size)
        else:
            self._normal_geometry = self.geometry()
            self.showMaximized()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)

    def retranslateUi(self) -> None:
        if not hasattr(self, "_open_btn"):
            return
        self._open_btn.setText(self.tr("Open"))
        if hasattr(self, "_copy_btn"):
            self._copy_btn.setText(self.tr("Copy Path"))
            self._copy_btn.setToolTip(self.tr("Copy Path / URL (Ctrl+C)"))
        if hasattr(self, "_reveal_footer_btn"):
            self._reveal_footer_btn.setText(self.tr("Open in Explorer"))
            self._reveal_footer_btn.setToolTip(self.tr("Open in Explorer (Ctrl+E)"))

    def set_link(self, link: dict[str, Any]) -> None:
        self._apply_preview_theme()
        self._current_link = link
        name = str(link.get("name") or self.tr("Untitled"))
        url = str(link.get("url") or "").strip()
        raw_type = link.get("type") or "web"
        link_type = LinkType.from_value(raw_type)
        icon_name = link.get("icon")

        self.setWindowTitle(name)
        self._path_lbl.setText(url)
        if hasattr(self, "_open_btn"):
            self._open_btn.setEnabled(True)
        if hasattr(self, "_pdf_nav_widget"):
            self._pdf_nav_widget.setVisible(False)
        if hasattr(self, "_reveal_footer_btn"):
            clean_u = url.strip().strip('"\'')
            if clean_u.startswith("file:///"):
                clean_u = clean_u[8:]
            is_local = bool(clean_u and (os.path.exists(clean_u) or link_type in (LinkType.FILE, LinkType.FOLDER, LinkType.PROGRAM)))
            self._reveal_footer_btn.setVisible(is_local)
        self._current_orig_image = None
        self._image_zoom = 1.0

        raw_icon = link.get("icon") or link.get("icon_path") or ""
        qicon = get_icon(raw_icon) if raw_icon else QIcon()
        if not qicon or qicon.isNull():
            resolved = resolve_icon_for_link(link)
            if resolved:
                qicon = get_icon(resolved)
        if (not qicon or qicon.isNull()) and link_type in (LinkType.FILE, LinkType.FOLDER, LinkType.PROGRAM) and url:
            fi = QFileInfo(url)
            if fi.exists():
                qicon = QFileIconProvider().icon(fi)

        if qicon and not qicon.isNull():
            self._footer_icon_lbl.setPixmap(qicon.pixmap(16, 16))
        else:
            self._footer_icon_lbl.clear()

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
            if hasattr(self, "_open_btn"):
                self._open_btn.setEnabled(False)
            not_found = self.tr("File or folder not found on disk")
            hint = self.tr("The file may have been moved, renamed, or deleted.")
            self._render_generic_card(
                qicon,
                f"<div style='font-size: 16px; font-weight: 600; margin-bottom: 12px;'>{html.escape(name)}</div>"
                f"<div style='font-size: 13px; color: #ff6b6b; font-weight: 500; margin-bottom: 8px;'>{not_found}</div>"
                f"<div style='font-size: 12px; opacity: 0.75; margin-bottom: 14px;'>{hint}</div>"
                f"<div style='font-size: 11px; opacity: 0.55; word-break: break-all;'>{html.escape(path_str)}</div>",
                show_reveal=False,
            )
            return

        ext = path.suffix.lower()
        if ext == ".docx":
            try:
                with zipfile.ZipFile(path_str) as z:
                    xml_content = z.read("word/document.xml")
                tree = ET.fromstring(xml_content)
                paragraphs = []
                for node in tree.iter():
                    if node.tag.endswith("}p"):
                        texts = [t.text for t in node.iter() if t.tag.endswith("}t") and t.text]
                        if texts:
                            paragraphs.append("".join(texts))
                doc_text = "\n\n".join(paragraphs)
                if doc_text.strip():
                    self._stack.setCurrentWidget(self._text_page)
                    self._is_prose_mode = True
                    self._set_formatted_text(doc_text, is_code=False)
                    sz_str = _format_file_size(path.stat().st_size)
                    self._text_info_lbl.setText(
                        f"DOCX  •  {len(paragraphs)} {self.tr('paragraphs')}  •  {sz_str}"
                    )
                    return
            except Exception as e:
                logger.debug("Failed to read docx text %s: %s", path_str, e)

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
                    self._current_orig_image = pix
                    self._image_zoom = 1.0
                    self._stack.setCurrentWidget(self._image_page)
                    self._image_lbl.setPixmap(pix)
                    sz_str = _format_file_size(path.stat().st_size)
                    self._image_info_lbl.setText(
                        f"{orig_sz.width()} × {orig_sz.height()} px  •  {sz_str}  •  {ext.upper().lstrip('.')}"
                    )
                    return

        if ext in (".psd", ".psb"):
            if self._render_psd_preview(path_str, ext):
                return

        if ext == ".ai":
            if self._render_ai_preview(path_str, ext):
                return

        if ext == ".eps":
            if self._render_eps_preview(path_str, ext):
                return

        if ext == ".pdf" and _HAS_PDF and self._pdf_doc is not None:
            try:
                self._pdf_doc.load(path_str)
                if self._pdf_doc.status() == QPdfDocument.Status.Ready:
                    self._stack.setCurrentWidget(self._pdf_view)
                    self._pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
                    self._pdf_view.setZoomFactor(1.44)
                    self._update_pdf_info()
                    return
            except Exception as e:
                logger.debug("Failed to load PDF %s: %s", path_str, e)

        if ext == ".csv":
            if self._render_csv_preview(path_str):
                return

        if ext in (".xlsx", ".xlsm"):
            if self._render_xlsx_preview(path_str):
                return

        if ext in (".zip", ".jar", ".whl", ".apk"):
            if self._render_zip_preview(path_str):
                return

        if ext in TEXT_EXTENSIONS:
            if ext == ".md":
                try:
                    with open(path, "rb") as f:
                        chunk = f.read(65536)
                    text = chunk.decode("utf-8", errors="replace")
                    self._stack.setCurrentWidget(self._text_page)
                    self._is_prose_mode = True
                    self._set_markdown_text(text)
                    sz_str = _format_file_size(path.stat().st_size)
                    self._text_info_lbl.setText(f"Markdown  •  {sz_str}")
                    return
                except Exception as e:
                    logger.debug("Failed to read markdown file %s: %s", path_str, e)

            try:
                with open(path, "rb") as f:
                    chunk = f.read(65536)
                text = chunk.decode("utf-8", errors="replace")
                self._stack.setCurrentWidget(self._text_page)
                is_code = ext not in {".txt", ".log"}
                self._is_prose_mode = not is_code
                self._set_formatted_text(text, is_code=is_code)
                sz_str = _format_file_size(path.stat().st_size)
                lines_count = text.count("\n") + 1
                self._text_info_lbl.setText(
                    f"{self.tr('Lines')}: ~{lines_count}  •  {self.tr('Size')}: {sz_str}  •  UTF-8"
                )
                return
            except Exception as e:
                logger.debug("Failed to read text file %s: %s", path_str, e)

        sz_str = _format_file_size(path.stat().st_size)
        try:
            mtime_str = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
        except Exception:
            mtime_str = "—"
        fmt_name = ext.upper().lstrip(".") or self.tr("File")
        info_html = (
            f"<div style='font-size: 16px; font-weight: 600; margin-bottom: 12px;'>{html.escape(name)}</div>"
            f"<table style='font-size: 13px; line-height: 1.8; margin: auto;'>"
            f"<tr><td style='text-align: right; padding-right: 12px; opacity: 0.65;'>{self.tr('Format')}:</td><td style='text-align: left;'><b>{fmt_name}</b></td></tr>"
            f"<tr><td style='text-align: right; padding-right: 12px; opacity: 0.65;'>{self.tr('Size')}:</td><td style='text-align: left;'>{sz_str}</td></tr>"
            f"<tr><td style='text-align: right; padding-right: 12px; opacity: 0.65;'>{self.tr('Modified')}:</td><td style='text-align: left;'>{mtime_str}</td></tr>"
            f"</table>"
        )
        self._render_generic_card(qicon, info_html, show_reveal=True)

    def _render_csv_preview(self, path_str: str) -> bool:
        try:
            with open(path_str, "r", encoding="utf-8", errors="replace") as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample)
                    delimiter = dialect.delimiter
                except Exception:
                    delimiter = ","
                reader = csv.reader(f, delimiter=delimiter)
                rows = []
                for i, row in enumerate(reader):
                    if i >= 100:
                        break
                    rows.append(row)

            if not rows:
                return False

            self._populate_table(rows)
            self._stack.setCurrentWidget(self._table_view)
            sz_str = _format_file_size(os.path.getsize(path_str))
            self._text_info_lbl.setText(
                f"CSV  •  {len(rows)} {self.tr('preview rows')}  •  {sz_str}"
            )
            return True
        except Exception as e:
            logger.debug("Failed to read CSV %s: %s", path_str, e)
            return False

    def _render_psd_preview(self, path_str: str, ext: str) -> bool:
        if _HAS_PIL:
            try:
                with Image.open(path_str) as im:
                    orig_w, orig_h = im.size
                    if orig_w > 0 and orig_h > 0:
                        im_rgba = im.convert("RGBA")
                        data = im_rgba.tobytes("raw", "RGBA")
                        qimg = QImage(data, orig_w, orig_h, orig_w * 4, QImage.Format.Format_RGBA8888)
                        pix = QPixmap.fromImage(qimg.copy())
                        if not pix.isNull():
                            self._current_orig_image = pix
                            self._image_zoom = 1.0
                            self._stack.setCurrentWidget(self._image_page)
                            self._apply_image_zoom()
                            sz_str = _format_file_size(os.path.getsize(path_str))
                            self._image_info_lbl.setText(
                                f"{orig_w} × {orig_h} px  •  {sz_str}  •  {ext.upper().lstrip('.')}"
                            )
                            return True
            except Exception as e:
                logger.debug("Failed to read PSD via Pillow %s: %s", path_str, e)

        thumb_bytes = self._extract_adobe_thumbnail(path_str)
        if thumb_bytes:
            qimg = QImage()
            if qimg.loadFromData(thumb_bytes):
                pix = QPixmap.fromImage(qimg)
                if not pix.isNull():
                    self._current_orig_image = pix
                    self._image_zoom = 1.0
                    self._stack.setCurrentWidget(self._image_page)
                    self._apply_image_zoom()
                    sz_str = _format_file_size(os.path.getsize(path_str))
                    self._image_info_lbl.setText(
                        f"{qimg.width()} × {qimg.height()} px  •  {sz_str}  •  {ext.upper().lstrip('.')}"
                    )
                    return True
        return False

    def _render_ai_preview(self, path_str: str, ext: str) -> bool:
        if _HAS_PDF and self._pdf_doc is not None:
            try:
                self._pdf_doc.load(path_str)
                if self._pdf_doc.status() == QPdfDocument.Status.Ready and self._pdf_doc.pageCount() > 0:
                    self._stack.setCurrentWidget(self._pdf_view)
                    self._pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
                    self._pdf_view.setZoomFactor(1.44)
                    self._update_pdf_info()
                    return True
            except Exception as e:
                logger.debug("Direct PDF load failed for AI %s: %s", path_str, e)

        thumb_bytes = self._extract_adobe_thumbnail(path_str)
        if thumb_bytes:
            qimg = QImage()
            if qimg.loadFromData(thumb_bytes):
                pix = QPixmap.fromImage(qimg)
                if not pix.isNull():
                    self._current_orig_image = pix
                    self._image_zoom = 1.0
                    self._stack.setCurrentWidget(self._image_page)
                    self._apply_image_zoom()
                    sz_str = _format_file_size(os.path.getsize(path_str))
                    self._image_info_lbl.setText(
                        f"{qimg.width()} × {qimg.height()} px  •  {sz_str}  •  {ext.upper().lstrip('.')}"
                    )
                    return True
        return False

    def _render_eps_preview(self, path_str: str, ext: str) -> bool:
        try:
            with open(path_str, "rb") as f:
                header = f.read(30)
                if len(header) >= 30 and header[:4] == b"\xc5\xd0\xd3\xc6":
                    tiff_start = int.from_bytes(header[20:24], "little")
                    tiff_len = int.from_bytes(header[24:28], "little")
                    if tiff_start > 0 and tiff_len > 0:
                        f.seek(tiff_start)
                        tiff_data = f.read(tiff_len)
                        qimg = QImage()
                        if qimg.loadFromData(tiff_data):
                            pix = QPixmap.fromImage(qimg)
                            if not pix.isNull():
                                self._current_orig_image = pix
                                self._image_zoom = 1.0
                                self._stack.setCurrentWidget(self._image_page)
                                self._apply_image_zoom()
                                sz_str = _format_file_size(os.path.getsize(path_str))
                                self._image_info_lbl.setText(
                                    f"{qimg.width()} × {qimg.height()} px  •  {sz_str}  •  EPS"
                                )
                                return True
        except Exception as e:
            logger.debug("Failed to read binary EPS preview %s: %s", path_str, e)

        thumb_bytes = self._extract_adobe_thumbnail(path_str)
        if thumb_bytes:
            qimg = QImage()
            if qimg.loadFromData(thumb_bytes):
                pix = QPixmap.fromImage(qimg)
                if not pix.isNull():
                    self._current_orig_image = pix
                    self._image_zoom = 1.0
                    self._stack.setCurrentWidget(self._image_page)
                    self._apply_image_zoom()
                    sz_str = _format_file_size(os.path.getsize(path_str))
                    self._image_info_lbl.setText(
                        f"{qimg.width()} × {qimg.height()} px  •  {sz_str}  •  EPS"
                    )
                    return True
        return False

    @staticmethod
    def _extract_adobe_thumbnail(path_str: str) -> bytes | None:
        try:
            with open(path_str, "rb") as f:
                chunk = f.read(2 * 1024 * 1024)
            for tag_s, tag_e in (
                (b"<xmpGImg:image>", b"</xmpGImg:image>"),
                (b"<xapGImg:image>", b"</xapGImg:image>"),
            ):
                s_idx = chunk.find(tag_s)
                if s_idx != -1:
                    e_idx = chunk.find(tag_e, s_idx)
                    if e_idx != -1:
                        raw_b64 = (
                            chunk[s_idx + len(tag_s):e_idx]
                            .strip()
                            .replace(b"\n", b"")
                            .replace(b"\r", b"")
                        )
                        return base64.b64decode(raw_b64)
        except Exception as e:
            logger.debug("Failed to extract Adobe thumbnail %s: %s", path_str, e)
        return None

    def _render_xlsx_preview(self, path_str: str) -> bool:
        try:
            with zipfile.ZipFile(path_str) as z:
                shared_strings = []
                if "xl/sharedStrings.xml" in z.namelist():
                    ss_tree = ET.fromstring(z.read("xl/sharedStrings.xml"))
                    for si in ss_tree.iter():
                        if si.tag.endswith("}si"):
                            texts = [t.text for t in si.iter() if t.tag.endswith("}t") and t.text]
                            shared_strings.append("".join(texts))

                sheet_name = "xl/worksheets/sheet1.xml"
                if sheet_name not in z.namelist():
                    sheets = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
                    if not sheets:
                        return False
                    sheet_name = sheets[0]

                sheet_tree = ET.fromstring(z.read(sheet_name))
                rows: list[list[str]] = []
                for row_el in sheet_tree.iter():
                    if row_el.tag.endswith("}row"):
                        row_dict: dict[int, str] = {}
                        for c_el in row_el.iter():
                            if c_el.tag.endswith("}c"):
                                ref = c_el.attrib.get("r", "")
                                col_letters = "".join(filter(str.isalpha, ref)).upper()
                                c_idx = 0
                                for ch in col_letters:
                                    c_idx = c_idx * 26 + (ord(ch) - ord("A") + 1)
                                c_idx = max(0, c_idx - 1) if c_idx > 0 else len(row_dict)

                                cell_type = c_el.attrib.get("t")
                                val = ""
                                if cell_type == "inlineStr":
                                    val = "".join(
                                        t.text for t in c_el.iter() if t.tag.endswith("}t") and t.text
                                    )
                                else:
                                    v_el = next((child for child in c_el if child.tag.endswith("}v")), None)
                                    raw_val = v_el.text if v_el is not None and v_el.text else ""
                                    if cell_type == "s" and raw_val.isdigit():
                                        idx = int(raw_val)
                                        val = shared_strings[idx] if idx < len(shared_strings) else raw_val
                                    elif cell_type == "b":
                                        val = "TRUE" if raw_val == "1" else "FALSE"
                                    else:
                                        val = raw_val
                                row_dict[c_idx] = val
                        if any(row_dict.values()):
                            max_c = max(row_dict.keys())
                            row_vals = [row_dict.get(i, "") for i in range(max_c + 1)]
                            rows.append(row_vals)
                        if len(rows) >= 100:
                            break

            if not rows:
                return False

            self._populate_table(rows)
            self._stack.setCurrentWidget(self._table_view)
            sz_str = _format_file_size(os.path.getsize(path_str))
            self._text_info_lbl.setText(
                f"XLSX  •  {len(rows)} {self.tr('preview rows')}  •  {sz_str}"
            )
            return True
        except Exception as e:
            logger.debug("Failed to read XLSX %s: %s", path_str, e)
            return False

    def _render_zip_preview(self, path_str: str) -> bool:
        try:
            with zipfile.ZipFile(path_str, "r") as z:
                infolist = z.infolist()
                if not infolist:
                    return False

                self._folder_list.clear()
                total_uncompressed = 0
                max_show = 100
                for idx, info in enumerate(infolist):
                    total_uncompressed += info.file_size
                    if idx < max_show:
                        is_dir = info.is_dir() or info.filename.endswith("/")
                        is_encrypted = bool(info.flag_bits & 0x1)
                        if is_dir:
                            prefix = "📁 "
                        elif is_encrypted:
                            prefix = "🔒 "
                        else:
                            prefix = "📄 "
                        size_part = f" ({_format_file_size(info.file_size)})" if not is_dir else ""
                        self._folder_list.addItem(
                            QListWidgetItem(f"{prefix}{info.filename}{size_part}")
                        )

                if len(infolist) > max_show:
                    remaining = len(infolist) - max_show
                    self._folder_list.addItem(QListWidgetItem(f"... (+{remaining})"))

            sz_str = _format_file_size(os.path.getsize(path_str))
            uncompressed_str = _format_file_size(total_uncompressed)
            self._folder_info_lbl.setText(
                f"ZIP  •  {len(infolist)} {self.tr('files and folders')}  •  {sz_str} ({self.tr('uncompressed')}: {uncompressed_str})"
            )
            self._stack.setCurrentWidget(self._folder_page)
            return True
        except Exception as e:
            logger.debug("Failed to read ZIP %s: %s", path_str, e)
            return False

    def _on_pdf_page_changed(self, page_index: int) -> None:
        self._update_pdf_info()

    def _update_pdf_info(self) -> None:
        if not _HAS_PDF or self._pdf_doc is None or self._pdf_view is None:
            return
        page_count = self._pdf_doc.pageCount()
        if page_count <= 0:
            return
        cur_page = self._pdf_view.pageNavigator().currentPage() + 1
        self._pdf_page_lbl.setText(f"{cur_page} / {page_count}")
        self._pdf_nav_widget.setVisible(page_count > 1)
        self._pdf_prev_btn.setEnabled(cur_page > 1)
        self._pdf_next_btn.setEnabled(cur_page < page_count)
        zoom_pct = int(self._pdf_view.zoomFactor() * 100)
        path_str = (
            str(self._current_link.get("url") or self._current_link.get("path") or "")
            if self._current_link
            else ""
        )
        sz_str = (
            _format_file_size(os.path.getsize(path_str))
            if path_str and os.path.exists(path_str)
            else ""
        )
        fmt_label = Path(path_str).suffix.upper().lstrip(".") or "PDF"
        self._text_info_lbl.setText(
            f"{fmt_label}  •  {self.tr('Page')} {cur_page} / {page_count}  •  {zoom_pct}%  •  {sz_str}"
        )

    def _pdf_prev_page(self) -> None:
        if _HAS_PDF and self._pdf_view:
            nav = self._pdf_view.pageNavigator()
            nav.jump(max(0, nav.currentPage() - 1), QPointF())

    def _pdf_next_page(self) -> None:
        if _HAS_PDF and self._pdf_view and self._pdf_doc:
            nav = self._pdf_view.pageNavigator()
            nav.jump(min(self._pdf_doc.pageCount() - 1, nav.currentPage() + 1), QPointF())

    def _pdf_first_page(self) -> None:
        if _HAS_PDF and self._pdf_view:
            self._pdf_view.pageNavigator().jump(0, QPointF())

    def _pdf_last_page(self) -> None:
        if _HAS_PDF and self._pdf_view and self._pdf_doc:
            self._pdf_view.pageNavigator().jump(max(0, self._pdf_doc.pageCount() - 1), QPointF())

    def _zoom_in(self) -> None:
        cur_w = self._stack.currentWidget()
        if _HAS_PDF and cur_w == self._pdf_view and self._pdf_view:
            cur_factor = self._pdf_view.zoomFactor()
            self._pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
            self._pdf_view.setZoomFactor(min(5.0, cur_factor * 1.2))
            self._update_pdf_info()
        elif cur_w == self._image_page and self._current_orig_image:
            self._image_zoom = min(5.0, self._image_zoom * 1.2)
            self._apply_image_zoom()
        else:
            self._text_edit.zoomIn(1)

    def _zoom_out(self) -> None:
        cur_w = self._stack.currentWidget()
        if _HAS_PDF and cur_w == self._pdf_view and self._pdf_view:
            cur_factor = self._pdf_view.zoomFactor()
            self._pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
            self._pdf_view.setZoomFactor(max(0.1, cur_factor / 1.2))
            self._update_pdf_info()
        elif cur_w == self._image_page and self._current_orig_image:
            self._image_zoom = max(0.1, self._image_zoom / 1.2)
            self._apply_image_zoom()
        else:
            self._text_edit.zoomOut(1)

    def _zoom_reset(self) -> None:
        cur_w = self._stack.currentWidget()
        if _HAS_PDF and cur_w == self._pdf_view and self._pdf_view:
            self._pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
            self._pdf_view.setZoomFactor(1.44)
            self._update_pdf_info()
        elif cur_w == self._image_page and self._current_orig_image:
            self._image_zoom = 1.0
            self._apply_image_zoom()
        else:
            default_sz = 13 if getattr(self, "_is_prose_mode", True) else 11
            self._text_edit.setFont(QFont("Segoe UI", default_sz))

    def _apply_image_zoom(self) -> None:
        if not self._current_orig_image or self._current_orig_image.isNull():
            return
        target_w = max(10, int(self._current_orig_image.width() * self._image_zoom))
        target_h = max(10, int(self._current_orig_image.height() * self._image_zoom))
        scaled = self._current_orig_image.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_lbl.setPixmap(scaled)
        orig_w = self._current_orig_image.width()
        orig_h = self._current_orig_image.height()
        path_str = (
            str(self._current_link.get("url") or self._current_link.get("path") or "")
            if self._current_link
            else ""
        )
        sz_str = (
            _format_file_size(os.path.getsize(path_str))
            if path_str and os.path.exists(path_str)
            else ""
        )
        self._image_info_lbl.setText(
            f"{orig_w} × {orig_h} px  •  {int(self._image_zoom * 100)}%  •  {sz_str}"
        )

    def _populate_table(self, rows: list[list[str]]) -> None:
        self._table_view.clear()
        if not rows:
            self._table_view.setRowCount(0)
            self._table_view.setColumnCount(0)
            return

        def _col_name(idx: int) -> str:
            name = ""
            idx += 1
            while idx > 0:
                idx, rem = divmod(idx - 1, 26)
                name = chr(65 + rem) + name
            return name

        max_cols = max(len(r) for r in rows)
        first_row = rows[0]
        has_header = any(any(ch.isalpha() for ch in str(v)) for v in first_row)

        if has_header and len(rows) > 1:
            col_headers = [
                str(first_row[c]).strip() or _col_name(c) if c < len(first_row) else _col_name(c)
                for c in range(max_cols)
            ]
            data_rows = rows[1:]
            start_row_num = 2
        else:
            col_headers = [_col_name(c) for c in range(max_cols)]
            data_rows = rows
            start_row_num = 1

        self._table_view.setRowCount(len(data_rows))
        self._table_view.setColumnCount(max_cols)
        self._table_view.setHorizontalHeaderLabels(col_headers)
        self._table_view.setVerticalHeaderLabels([str(start_row_num + i) for i in range(len(data_rows))])

        for r_idx, row in enumerate(data_rows):
            for c_idx in range(max_cols):
                val = row[c_idx] if c_idx < len(row) else ""
                self._table_view.setItem(r_idx, c_idx, QTableWidgetItem(str(val)))

        self._table_view.resizeColumnsToContents()
        for col in range(max_cols):
            w = self._table_view.columnWidth(col)
            self._table_view.setColumnWidth(col, min(max(w + 16, 70), 320))

    def _copy_table_selection(self) -> bool:
        selected_indexes = self._table_view.selectedIndexes()
        if not selected_indexes:
            return False

        rows_dict: dict[int, dict[int, str]] = {}
        for idx in selected_indexes:
            r = idx.row()
            c = idx.column()
            item = self._table_view.item(r, c)
            text = item.text() if item is not None else ""
            if r not in rows_dict:
                rows_dict[r] = {}
            rows_dict[r][c] = text

        if not rows_dict:
            return False

        if len(rows_dict) == 1 and len(next(iter(rows_dict.values()))) == 1:
            val = next(iter(next(iter(rows_dict.values())).values()))
            QApplication.clipboard().setText(val)
            return True

        sorted_rows = sorted(rows_dict.keys())
        all_cols = sorted({c for row in rows_dict.values() for c in row})
        lines = ["\t".join(rows_dict[r].get(c, "") for c in all_cols) for r in sorted_rows]
        QApplication.clipboard().setText("\n".join(lines))
        return True

    def _show_table_context_menu(self, pos: QPoint) -> None:
        try:
            idx = self._table_view.indexAt(pos)
            if idx.isValid() and idx not in self._table_view.selectedIndexes():
                self._table_view.setCurrentIndex(idx)

            theme_name = get_current_theme()
            menu = QMenu(self._table_view)
            menu.setStyleSheet(self._get_menu_style())
            self._context_menus.append(menu)

            has_selection = bool(self._table_view.selectedIndexes())

            copy_act = menu.addAction(
                get_menu_icon("copy", theme_name),
                QCoreApplication.translate("MenuActions", "Copy"),
            )
            copy_act.setShortcut(HotkeyManager.get_sequence("edit.copy"))
            copy_act.setEnabled(has_selection)
            copy_act.triggered.connect(self._copy_table_selection)

            menu.addSeparator()

            select_all_act = menu.addAction(
                get_menu_icon("select_all", theme_name),
                QCoreApplication.translate("MenuActions", "Select all"),
            )
            select_all_act.setShortcut(HotkeyManager.get_sequence("edit.select_all"))
            select_all_act.triggered.connect(self._table_view.selectAll)

            menu.exec(self._table_view.viewport().mapToGlobal(pos))
        except Exception as e:
            logger.warning("Failed to show table context menu: %s", e)

    def _show_context_menu(self, widget, pos) -> None:
        """Show context menu for read-only preview text with tracking for cleanup."""
        try:
            theme_name = get_current_theme()
            menu = QMenu(widget)
            menu.setStyleSheet(self._get_menu_style())
            self._context_menus.append(menu)

            has_selection = (
                widget.textCursor().hasSelection()
                if isinstance(widget, QTextEdit)
                else False
            )

            copy_act = menu.addAction(
                get_menu_icon("copy", theme_name),
                QCoreApplication.translate("MenuActions", "Copy"),
            )
            copy_act.setShortcut(HotkeyManager.get_sequence("edit.copy"))
            copy_act.setEnabled(has_selection)
            copy_act.triggered.connect(widget.copy)

            menu.addSeparator()

            select_all_act = menu.addAction(
                get_menu_icon("select_all", theme_name),
                QCoreApplication.translate("MenuActions", "Select all"),
            )
            select_all_act.setShortcut(HotkeyManager.get_sequence("edit.select_all"))
            select_all_act.triggered.connect(widget.selectAll)

            global_pos = (
                widget.viewport().mapToGlobal(pos)
                if hasattr(widget, "viewport")
                else widget.mapToGlobal(pos)
            )
            menu.popup(global_pos)
        except Exception as e:
            logger.warning("Failed to show preview text context menu: %s", e)

    def _get_menu_style(self) -> str:
        if self._is_dark_theme():
            return (
                "QMenu {"
                ' font-family: "Segoe UI", system-ui, -apple-system, sans-serif;'
                " background-color: #252B35;"
                " color: #D1D6E0;"
                " border: 1px solid #3A3E44;"
                " border-radius: 0;"
                " padding: 0;"
                "}"
                "QMenu::item {"
                " background-color: transparent;"
                " color: #D1D6E0;"
                " padding: 0 12px 0 16px;"
                " margin: 0;"
                " border-radius: 0;"
                "}"
                "QMenu::icon { padding-left: 16px; }"
                "QMenu::item:selected { background-color: #2E4066; color: #FFFFFF; }"
                "QMenu::item:disabled { color: #5A6372; background: transparent; }"
                "QMenu::separator { height: 1px; background-color: #3A3E44; margin: 0; padding: 0; }"
            )
        return (
            "QMenu {"
            ' font-family: "Segoe UI", system-ui, -apple-system, sans-serif;'
            " background-color: #FAFCFF;"
            " color: #333333;"
            " border: 1px solid #B3B3B3;"
            " border-radius: 0;"
            " padding: 0;"
            "}"
            "QMenu::item {"
            " background-color: transparent;"
            " color: #333333;"
            " padding: 0 12px 0 16px;"
            " margin: 0;"
            " border-radius: 0;"
            "}"
            "QMenu::icon { padding-left: 16px; }"
            "QMenu::item:selected { background-color: #E6E6E6; color: #000000; }"
            "QMenu::item:disabled { color: #999999; background: transparent; }"
            "QMenu::separator { height: 1px; background-color: #B3B3B3; margin: 0; padding: 0; }"
        )

    def _is_dark_theme(self) -> bool:
        try:
            from app.services.theme_registry import ThemeRegistry
            from app.utils.ui.icon.path_service import get_current_theme
            cur_theme = get_current_theme()
            theme_meta = ThemeRegistry().get_theme(cur_theme)
            if theme_meta is not None:
                return bool(theme_meta.is_dark)
        except Exception:
            pass
        bg = self.palette().color(QPalette.ColorRole.Window)
        return (bg.red() * 0.299 + bg.green() * 0.587 + bg.blue() * 0.114) < 128

    def _apply_preview_theme(self) -> None:
        self.setStyleSheet(_DARK_PREVIEW_QSS if self._is_dark_theme() else _LIGHT_PREVIEW_QSS)
        cur_t = get_current_theme()
        if hasattr(self, "_pdf_prev_btn") and hasattr(self, "_pdf_next_btn"):
            self._pdf_prev_btn.setIcon(icon_cache.get_icon("left", cur_t))
            self._pdf_next_btn.setIcon(icon_cache.get_icon("right", cur_t))

    def _set_formatted_text(self, text: str, is_code: bool = False) -> None:
        doc = self._text_edit.document()
        doc.clear()

        font_name = "Consolas" if is_code else "Segoe UI"
        font_size = 11 if is_code else 13

        char_fmt = QTextCharFormat()
        char_fmt.setFont(QFont(font_name, font_size))

        block_fmt = QTextBlockFormat()
        block_fmt.setLineHeight(
            120 if is_code else 140,
            QTextBlockFormat.LineHeightTypes.ProportionalHeight.value,
        )
        block_fmt.setBottomMargin(0 if is_code else 10)

        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        paragraphs = text.split("\n") if is_code else [p.strip() for p in text.split("\n\n") if p.strip()]
        for i, para in enumerate(paragraphs):
            if i > 0:
                cursor.insertBlock(block_fmt, char_fmt)
            else:
                cursor.setBlockFormat(block_fmt)
                cursor.setBlockCharFormat(char_fmt)
            cursor.insertText(para)
        cursor.endEditBlock()
        self._update_text_margins()
        self._text_edit.moveCursor(QTextCursor.MoveOperation.Start)

    def _set_markdown_text(self, text: str) -> None:
        font = QFont("Segoe UI", 13)
        self._text_edit.setFont(font)
        doc = self._text_edit.document()
        doc.clear()
        doc.setDefaultFont(font)
        doc.setDocumentMargin(0)
        doc.setMarkdown(text)

        b = doc.firstBlock()
        while b.isValid():
            bfmt = b.blockFormat()
            bfmt.setLineHeight(140, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            bfmt.setBottomMargin(8)
            cursor = QTextCursor(b)
            cursor.setBlockFormat(bfmt)
            b = b.next()

        self._update_text_margins()
        self._text_edit.moveCursor(QTextCursor.MoveOperation.Start)

    def _update_text_margins(self) -> None:
        w = self._text_edit.width() or self.width()
        margin = max(32, (w - 768) // 2)
        if getattr(self, "_is_prose_mode", True):
            self._text_edit.setViewportMargins(margin, 24, margin, 24)
        else:
            self._text_edit.setViewportMargins(margin, 16, margin, 16)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_text_margins()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_preview_theme()
        self._update_text_margins()

    def _render_folder_preview(self, path_str: str, name: str) -> None:
        path = Path(path_str)
        if not path.exists() or not path.is_dir():
            if hasattr(self, "_open_btn"):
                self._open_btn.setEnabled(False)
            not_found = self.tr("File or folder not found on disk")
            hint = self.tr("The file may have been moved, renamed, or deleted.")
            self._render_generic_card(
                QIcon(),
                f"<div style='font-size: 16px; font-weight: 600; margin-bottom: 12px;'>{html.escape(name)}</div>"
                f"<div style='font-size: 13px; color: #ff6b6b; font-weight: 500; margin-bottom: 8px;'>{not_found}</div>"
                f"<div style='font-size: 12px; opacity: 0.75; margin-bottom: 14px;'>{hint}</div>"
                f"<div style='font-size: 11px; opacity: 0.55; word-break: break-all;'>{html.escape(path_str)}</div>",
                show_reveal=False,
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
            self._folder_list.addItem(QListWidgetItem(f"{self.tr('Access error')}: {e}"))

        self._folder_info_lbl.setText(f"{self.tr('Total items in root')}: {items_count}")
        self._stack.setCurrentWidget(self._folder_page)

    def _render_script_preview(self, path_str: str, link: dict[str, Any]) -> None:
        path = Path(path_str)
        cmd_args = link.get("cmd_args") or ""
        work_dir = link.get("work_dir") or ""

        if not path.exists():
            if hasattr(self, "_open_btn"):
                self._open_btn.setEnabled(False)
            not_found = self.tr("File or folder not found on disk")
            hint = self.tr("The file may have been moved, renamed, or deleted.")
            self._render_generic_card(
                QIcon(),
                f"<div style='font-size: 16px; font-weight: 600; margin-bottom: 12px;'>{html.escape(str(link.get('name') or path.name))}</div>"
                f"<div style='font-size: 13px; color: #ff6b6b; font-weight: 500; margin-bottom: 8px;'>{not_found}</div>"
                f"<div style='font-size: 12px; opacity: 0.75; margin-bottom: 14px;'>{hint}</div>"
                f"<div style='font-size: 11px; opacity: 0.55; word-break: break-all;'>{html.escape(path_str)}</div>",
                show_reveal=False,
            )
            return

        if path.exists() and path.is_file():
            try:
                with open(path, "rb") as f:
                    chunk = f.read(65536)
                code = chunk.decode("utf-8", errors="replace")
                self._stack.setCurrentWidget(self._text_page)
                self._set_formatted_text(code, is_code=True)
                self._text_info_lbl.setText(
                    f"{self.tr('Script')}: {path.name}  •  {self.tr('Arguments')}: {cmd_args or self.tr('None')}"
                )
                return
            except Exception:
                pass

        info_html = (
            f"<b>{html.escape(str(link.get('name')))}</b><br><br>"
            f"{self.tr('Script')}: {html.escape(path_str)}<br>"
            f"{self.tr('Arguments')}: {html.escape(str(cmd_args)) or '—'}<br>"
            f"{self.tr('Working Directory')}: {html.escape(str(work_dir)) or '—'}"
        )
        self._render_generic_card(QIcon(), info_html)

    def _render_program_preview(
        self, path_str: str, link: dict[str, Any], qicon: QIcon
    ) -> None:
        cmd_args = link.get("cmd_args") or ""
        work_dir = link.get("work_dir") or ""
        is_uwp = path_str.lower().startswith("shell:appsfolder\\") or (
            "!" in path_str and "." in path_str and "\\" not in path_str
        )
        if not is_uwp and not Path(path_str).exists():
            if hasattr(self, "_open_btn"):
                self._open_btn.setEnabled(False)
            not_found = self.tr("File or folder not found on disk")
            hint = self.tr("The file may have been moved, renamed, or deleted.")
            self._render_generic_card(
                qicon,
                f"<div style='font-size: 16px; font-weight: 600; margin-bottom: 12px;'>{html.escape(str(link.get('name')))}</div>"
                f"<div style='font-size: 13px; color: #ff6b6b; font-weight: 500; margin-bottom: 8px;'>{not_found}</div>"
                f"<div style='font-size: 12px; opacity: 0.75; margin-bottom: 14px;'>{hint}</div>"
                f"<div style='font-size: 11px; opacity: 0.55; word-break: break-all;'>{html.escape(path_str)}</div>",
                show_reveal=False,
            )
            return

        info_html = (
            f"<b>{html.escape(str(link.get('name')))}</b><br><br>"
            f"{self.tr('Program')}: {html.escape(path_str)}<br>"
            f"{self.tr('Arguments')}: {html.escape(str(cmd_args)) or '—'}<br>"
            f"{self.tr('Working Directory')}: {html.escape(str(work_dir)) or '—'}"
        )
        self._render_generic_card(qicon, info_html)

    def _render_web_preview(self, url: str, link: dict[str, Any], qicon: QIcon) -> None:
        profile = link.get("browser_profile") or ""
        notes = link.get("notes") or ""
        info_html = (
            f"<div style='font-size: 15px; font-weight: 600; margin-bottom: 10px;'>{html.escape(str(link.get('name')))}</div>"
            f"URL: <span style='color: palette(highlight);'>{html.escape(url)}</span><br>"
            f"{self.tr('Profile')}: {html.escape(str(profile)) or self.tr('Default')}"
        )
        if notes:
            info_html += f"<br><br>{self.tr('Notes')}: <i>{html.escape(str(notes))}</i>"
        self._render_generic_card(qicon, info_html)

    def _render_generic_card(self, qicon: QIcon, text_html: str, show_reveal: bool = False) -> None:
        if qicon and not qicon.isNull():
            self._card_icon_lbl.setPixmap(qicon.pixmap(64, 64))
            self._card_icon_lbl.setVisible(True)
        else:
            self._card_icon_lbl.setVisible(False)
        self._card_desc_lbl.setText(text_html)
        if hasattr(self, "_reveal_btn"):
            self._reveal_btn.setVisible(show_reveal)
        self._stack.setCurrentWidget(self._card_page)

    def _handle_open(self) -> None:
        if hasattr(self, "_open_btn") and not self._open_btn.isEnabled():
            return
        if self._on_open_callback and self._current_link:
            self._on_open_callback(self._current_link)
        self.close()

    def eventFilter(self, obj, event) -> bool:
        if event.type() == event.Type.Wheel:
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta > 0:
                    self._zoom_in()
                elif delta < 0:
                    self._zoom_out()
                return True
        elif event.type() == event.Type.KeyPress:
            key = event.key()
            modifiers = event.modifiers()
            if key in (Qt.Key.Key_Space, Qt.Key.Key_Escape):
                self.close()
                return True
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._handle_open()
                return True
            elif key in (Qt.Key.Key_F, Qt.Key.Key_F11) or getattr(event, "nativeVirtualKey", lambda: 0)() == 0x46:
                self._toggle_fullscreen()
                return True
            elif modifiers == Qt.KeyboardModifier.ControlModifier and (
                key == Qt.Key.Key_C or getattr(event, "nativeVirtualKey", lambda: 0)() == 0x43
            ):
                if self._stack.currentWidget() == self._table_view and self._copy_table_selection():
                    return True
                if self._stack.currentWidget() == self._text_page and self._text_edit.textCursor().hasSelection():
                    self._text_edit.copy()
                    return True
                self._handle_copy_path()
                return True
            elif modifiers == Qt.KeyboardModifier.ControlModifier and (
                key == Qt.Key.Key_A or getattr(event, "nativeVirtualKey", lambda: 0)() == 0x41
            ):
                if self._stack.currentWidget() == self._table_view:
                    self._table_view.selectAll()
                    return True
                if self._stack.currentWidget() == self._text_page:
                    self._text_edit.selectAll()
                    return True
            elif modifiers == Qt.KeyboardModifier.ControlModifier and (
                key == Qt.Key.Key_E
                or getattr(event, "nativeVirtualKey", lambda: 0)() == 0x45
            ):
                self._handle_reveal_in_explorer()
                return True
            elif modifiers == Qt.KeyboardModifier.ControlModifier and key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self._zoom_in()
                return True
            elif modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_Minus:
                self._zoom_out()
                return True
            elif modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_0:
                self._zoom_reset()
                return True
            elif key == Qt.Key.Key_PageUp:
                if _HAS_PDF and self._stack.currentWidget() == self._pdf_view:
                    self._pdf_prev_page()
                    return True
            elif key == Qt.Key.Key_PageDown:
                if _HAS_PDF and self._stack.currentWidget() == self._pdf_view:
                    self._pdf_next_page()
                    return True
            elif key == Qt.Key.Key_Home:
                if _HAS_PDF and self._stack.currentWidget() == self._pdf_view:
                    self._pdf_first_page()
                    return True
            elif key == Qt.Key.Key_End:
                if _HAS_PDF and self._stack.currentWidget() == self._pdf_view:
                    self._pdf_last_page()
                    return True
            elif key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                if self._on_navigate_callback:
                    self._on_navigate_callback(1 if key == Qt.Key.Key_Down else -1)
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        modifiers = event.modifiers()
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Escape):
            self.close()
            event.accept()
            return
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._handle_open()
            event.accept()
            return
        elif key in (Qt.Key.Key_F, Qt.Key.Key_F11) or getattr(event, "nativeVirtualKey", lambda: 0)() == 0x46:
            self._toggle_fullscreen()
            event.accept()
            return
        elif modifiers == Qt.KeyboardModifier.ControlModifier and (
            key == Qt.Key.Key_C or getattr(event, "nativeVirtualKey", lambda: 0)() == 0x43
        ):
            if self._stack.currentWidget() == self._table_view and self._copy_table_selection():
                event.accept()
                return
            if self._stack.currentWidget() == self._text_page and self._text_edit.textCursor().hasSelection():
                self._text_edit.copy()
                event.accept()
                return
            self._handle_copy_path()
            event.accept()
            return
        elif modifiers == Qt.KeyboardModifier.ControlModifier and (
            key == Qt.Key.Key_A or getattr(event, "nativeVirtualKey", lambda: 0)() == 0x41
        ):
            if self._stack.currentWidget() == self._table_view:
                self._table_view.selectAll()
                event.accept()
                return
            if self._stack.currentWidget() == self._text_page:
                self._text_edit.selectAll()
                event.accept()
                return
        elif modifiers == Qt.KeyboardModifier.ControlModifier and (
            key == Qt.Key.Key_E
            or getattr(event, "nativeVirtualKey", lambda: 0)() == 0x45
        ):
            self._handle_reveal_in_explorer()
            event.accept()
            return
        elif modifiers == Qt.KeyboardModifier.ControlModifier and key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._zoom_in()
            event.accept()
            return
        elif modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_Minus:
            self._zoom_out()
            event.accept()
            return
        elif modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_0:
            self._zoom_reset()
            event.accept()
            return
        elif key == Qt.Key.Key_PageUp:
            if _HAS_PDF and self._stack.currentWidget() == self._pdf_view:
                self._pdf_prev_page()
                event.accept()
                return
        elif key == Qt.Key.Key_PageDown:
            if _HAS_PDF and self._stack.currentWidget() == self._pdf_view:
                self._pdf_next_page()
                event.accept()
                return
        elif key == Qt.Key.Key_Home:
            if _HAS_PDF and self._stack.currentWidget() == self._pdf_view:
                self._pdf_first_page()
                event.accept()
                return
        elif key == Qt.Key.Key_End:
            if _HAS_PDF and self._stack.currentWidget() == self._pdf_view:
                self._pdf_last_page()
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

    def wheelEvent(self, event) -> None:
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self._zoom_in()
            elif delta < 0:
                self._zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        if self.parent() and hasattr(self.parent(), "table"):
            table = self.parent().table
            if table:
                table.setFocus()

