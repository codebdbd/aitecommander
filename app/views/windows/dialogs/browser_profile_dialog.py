import logging
import re
from typing import Any, Optional

from PyQt6.QtCore import QCoreApplication, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStyle,
    QStyleOptionButton,
    QVBoxLayout,
    QWidget,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.core.paths.path_manager import PathManager
from app.utils.browser.browser_profiles import async_profile_manager as _apm
from app.utils.browser.browser_profiles import get_profile_manager
from app.utils.browser.browser_profiles import persistent_cache as _pc
from app.utils.browser.browser_profiles import profile_manager as _pm
from app.utils.browser.browser_profiles.utils import get_browser_display_name
from app.utils.browser.profile_selection_state import profile_selection_key
from app.utils.i18n.common import tr as tr_common
from app.utils.ui.icon.path_service import get_current_theme
from app.utils.ui.menu_builders.base import get_menu_icon
from app.utils.ui.qt.combo_helpers import PopupComboBox, select_first_combo_item

from .base_dialog import BaseDialog

logger = logging.getLogger(__name__)


class ProfileRadioButton(QRadioButton):
    double_clicked = pyqtSignal()

    def __init__(
        self,
        email: str,
        profile_name: str,
        fallback_text: str = "",
        accent_color: str = "#0194F0",
        is_dark: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.email = email
        self.profile_name = profile_name
        self.fallback_text = fallback_text
        self.accent_color = QColor(accent_color)
        self.is_dark = is_dark

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()

    def paintEvent(self, event):
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        opt.text = ""
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, p, self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        ind_rect = self.style().subElementRect(QStyle.SubElement.SE_RadioButtonIndicator, opt, self)
        cx = ind_rect.center().x()
        cy = ind_rect.center().y()
        radius = 7.0

        if self.isChecked():
            p.setPen(QPen(self.accent_color, 1.8))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), radius, radius)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self.accent_color))
            p.drawEllipse(QPointF(cx, cy), 3.8, 3.8)
        else:
            unsel_color = (
                self.accent_color
                if self.underMouse()
                else (QColor("#8B949E") if self.is_dark else QColor("#6E7781"))
            )
            p.setPen(QPen(unsel_color, 1.8))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), radius, radius)

        rect = self.style().subElementRect(QStyle.SubElement.SE_RadioButtonContents, opt, self)
        p.setClipRect(rect)
        fm = self.fontMetrics()
        x = rect.left() + 4
        y = rect.center().y() + fm.ascent() // 2 - 1
        text_color = self.palette().text().color() if self.isEnabled() else self.palette().placeholderText().color()
        muted_color = self.palette().placeholderText().color()
        email_login = self.email.split("@")[0].lower() if "@" in self.email else self.email.lower()
        if self.email and self.profile_name and self.profile_name.lower() not in (self.email.lower(), email_login):
            p.setPen(text_color)
            p.drawText(x, y, self.email)
            x += fm.horizontalAdvance(self.email)
            p.setPen(muted_color)
            sep = " | "
            p.drawText(x, y, sep)
            x += fm.horizontalAdvance(sep)
            italic_font = QFont(self.font())
            italic_font.setItalic(True)
            p.setFont(italic_font)
            p.setPen(text_color)
            p.drawText(x, y, self.profile_name)
        else:
            main_text = self.email or self.profile_name or self.fallback_text
            p.setPen(text_color)
            p.drawText(x, y, main_text)
        p.end()


class ProfileCheckBox(QCheckBox):
    def __init__(
        self,
        email: str,
        profile_name: str,
        fallback_text: str = "",
        accent_color: str = "#0194F0",
        is_dark: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.email = email
        self.profile_name = profile_name
        self.fallback_text = fallback_text
        self.accent_color = QColor(accent_color)
        self.is_dark = is_dark

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, event):
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        opt.text = ""
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, p, self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        ind_rect = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, opt, self)
        cx = ind_rect.center().x()
        cy = ind_rect.center().y()
        box_rect = QRectF(cx - 7, cy - 7, 14, 14)

        if self.isChecked():
            p.setPen(QPen(self.accent_color, 1.0))
            p.setBrush(QBrush(self.accent_color))
            p.drawRoundedRect(box_rect, 2.5, 2.5)
            lum = 0.299 * self.accent_color.red() + 0.587 * self.accent_color.green() + 0.114 * self.accent_color.blue()
            check_color = QColor("#121212") if lum > 130 else QColor("#FFFFFF")
            if getattr(self, "order_number", None):
                p.setPen(check_color)
                font = QFont(self.font())
                font.setPixelSize(10)
                font.setBold(True)
                p.setFont(font)
                p.drawText(box_rect, Qt.AlignmentFlag.AlignCenter, str(self.order_number))
            else:
                p.setPen(QPen(check_color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.setBrush(Qt.BrushStyle.NoBrush)
                path = QPainterPath()
                path.moveTo(cx - 4.0, cy + 0.0)
                path.lineTo(cx - 1.2, cy + 3.2)
                path.lineTo(cx + 4.2, cy - 2.8)
                p.drawPath(path)
        else:
            unsel_color = (
                self.accent_color
                if self.underMouse()
                else (QColor("#8B949E") if self.is_dark else QColor("#6E7781"))
            )
            p.setPen(QPen(unsel_color, 1.6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(box_rect, 2.5, 2.5)

        rect = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxContents, opt, self)
        p.setClipRect(rect)
        fm = self.fontMetrics()
        x = rect.left() + 4
        y = rect.center().y() + fm.ascent() // 2 - 1
        text_color = self.palette().text().color() if self.isEnabled() else self.palette().placeholderText().color()
        muted_color = self.palette().placeholderText().color()
        email_login = self.email.split("@")[0].lower() if "@" in self.email else self.email.lower()
        if self.email and self.profile_name and self.profile_name.lower() not in (self.email.lower(), email_login):
            p.setPen(text_color)
            p.drawText(x, y, self.email)
            x += fm.horizontalAdvance(self.email)
            p.setPen(muted_color)
            sep = " | "
            p.drawText(x, y, sep)
            x += fm.horizontalAdvance(sep)
            italic_font = QFont(self.font())
            italic_font.setItalic(True)
            p.setFont(italic_font)
            p.setPen(text_color)
            p.drawText(x, y, self.profile_name)
        else:
            main_text = self.email or self.profile_name or self.fallback_text
            p.setPen(text_color)
            p.drawText(x, y, main_text)
        p.end()


class BrowserProfileDialog(BaseDialog):
    def __init__(
        self,
        parent=None,
        initial_selected_profile_keys: set[str] | None = None,
        mode: str = "multi",
        allow_mode_change: bool = False,
        profile_mode: str = "single",
        allow_batch: bool = True,
    ):
        super().__init__(parent)
        self.setObjectName("BrowserProfileDialog")
        self.setWindowTitle(tr_common("Select browser profile"))
        width, height = app_config.ui.get_browser_profile_dialog_min_size()
        min_w = max(width, 620)
        self.setMinimumSize(min_w, 450)
        self.resize(max(min_w, 640), 500)
        self.manager = get_profile_manager()
        self.allow_mode_change = allow_mode_change
        self.profile_mode = profile_mode
        self.allow_batch = allow_batch
        self.mode = "single" if profile_mode == "single" else mode
        self._selected_profiles_map: dict[str, dict] = {}
        self.selected_profiles = []
        self.profile_checkboxes = []
        self.initial_selected_profile_keys = {
            str(key).strip().lower()
            for key in (initial_selected_profile_keys or set())
            if str(key).strip()
        }
        self.async_manager = _apm.get_async_profile_manager()
        self.async_manager.browser_profiles_ready.connect(self._on_async_profiles_ready)
        self.async_manager.loading_error.connect(self._on_async_profiles_error)
        self._pending_browser_key: Optional[str] = None
        self._setup_ui()
        self._populate_browsers()
        # Do not load every profile immediately; populate on demand for the chosen browser.
        # self._populate_profiles()
        # Initial translation pass
        self.retranslateUi()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        top_grid = QGridLayout()
        top_grid.setContentsMargins(0, 0, 0, 0)
        top_grid.setSpacing(8)
        top_grid.setColumnStretch(0, 0)
        top_grid.setColumnStretch(1, 1)
        top_grid.setColumnStretch(2, 0)
        row = 0
        if self.allow_mode_change:
            self.lbl_mode = QLabel(self.tr("Mode:"))
            top_grid.addWidget(
                self.lbl_mode,
                row,
                0,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            )
            self.mode_combo = PopupComboBox()
            self.mode_combo.addItem(self.tr("Single profile"), userData="single")
            self.mode_combo.addItem(self.tr("Rotation"), userData="rotation")
            if self.allow_batch:
                self.mode_combo.addItem(
                    self.tr("Create for each profile"), userData="batch"
                )
            for idx in range(self.mode_combo.count()):
                if self.mode_combo.itemData(idx) == self.profile_mode:
                    self.mode_combo.setCurrentIndex(idx)
                    break
            self.mode_combo.currentIndexChanged.connect(self._on_mode_combo_changed)
            top_grid.addWidget(self.mode_combo, row, 1, 1, 2)
            row += 1

        self.lbl_browsers = QLabel(self.tr("Browsers:"))
        top_grid.addWidget(
            self.lbl_browsers,
            row,
            0,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        )
        self.browser_combo = PopupComboBox()
        self.browser_combo.currentIndexChanged.connect(self._populate_profiles)
        top_grid.addWidget(self.browser_combo, row, 1)

        self.refresh_btn = QPushButton(self.tr("Refresh"))
        theme = get_current_theme()
        refresh_icon = get_menu_icon("refresh", theme)
        if refresh_icon and not refresh_icon.isNull():
            self.refresh_btn.setIcon(refresh_icon)
        self.refresh_btn.clicked.connect(self.refresh_profiles)
        top_grid.addWidget(self.refresh_btn, row, 2)

        layout.addLayout(top_grid)

        # 2. Row: search input
        search_layout = QHBoxLayout()
        self.search_line = QLineEdit()
        self.search_line.setClearButtonEnabled(True)
        self.search_line.setPlaceholderText(self.tr("Search by name/email"))
        self.search_line.textChanged.connect(self._populate_profiles)
        search_layout.addWidget(self.search_line, 1)
        layout.addLayout(search_layout)

        # Profiles list
        self.scroll_frame = QFrame()
        self.scroll_frame.setObjectName("profilesFrame")
        self.scroll_frame.setProperty("input_frame", "true")
        scroll_frame_layout = QVBoxLayout(self.scroll_frame)
        scroll_frame_layout.setContentsMargins(0, 0, 0, 0)
        scroll_frame_layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("profilesScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._apply_scroll_theme()
        try:
            for bar in (self.scroll.verticalScrollBar(), self.scroll.horizontalScrollBar()):
                if bar is None:
                    continue
        except Exception:
            logger.debug("BrowserProfileDialog: failed to normalize scrollbars", exc_info=True)
        try:
            self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        except Exception:
            logger.debug(
                "BrowserProfileDialog: failed to set scrollbar policies", exc_info=True
            )
        # Match background via QSS by targeting viewport
        self.scroll.viewport().setObjectName("profilesScrollViewport")
        self.profile_widget = QWidget()
        self.profile_widget.setObjectName("profilesContent")
        self.profile_layout = QVBoxLayout(self.profile_widget)
        self.profile_layout.setContentsMargins(0, 0, 0, 0)
        self.profile_layout.setSpacing(0)
        self.scroll.setWidget(self.profile_widget)
        scroll_frame_layout.addWidget(self.scroll)
        layout.addWidget(self.scroll_frame)

        # Buttons
        # 4. Bottom row: selection buttons and status on the left, Save/Cancel on the right
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 6, 0, 0)
        left_bottom = QHBoxLayout()
        # Selection helper buttons on the left
        self.select_all_btn = QPushButton(self.tr("Add all"))
        self.select_all_btn.clicked.connect(self._select_all_profiles)
        self.select_all_btn.setVisible(self.mode != "single")
        left_bottom.addWidget(self.select_all_btn)
        self.deselect_all_btn = QPushButton(self.tr("Clear selection"))
        self.deselect_all_btn.clicked.connect(self._deselect_all_profiles)
        self.deselect_all_btn.setVisible(self.mode != "single")
        left_bottom.addWidget(self.deselect_all_btn)
        # Status/progress indicator
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; margin-left: 8px;")
        left_bottom.addWidget(self.status_label, 0)
        bottom_layout.addLayout(left_bottom, 1)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        # Localize button labels
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_btn is not None:
            ok_btn.setText(tr_common("Save"))
            ok_btn.setEnabled(False)  # disabled until a profile is selected
            ok_btn.setDefault(True)
            self._ok_button = ok_btn
        if cancel_btn is not None:
            cancel_btn.setText(tr_common("Cancel"))
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        bottom_layout.addWidget(self.button_box, 0)
        layout.addLayout(bottom_layout)

    def _on_mode_combo_changed(self, index: int) -> None:
        new_mode = self.mode_combo.currentData() or "single"
        if new_mode == self.profile_mode:
            return
        self.profile_mode = new_mode
        self.mode = "single" if new_mode == "single" else "multi"
        self.select_all_btn.setVisible(self.mode != "single")
        self.deselect_all_btn.setVisible(self.mode != "single")
        if self.mode == "single" and len(self._selected_profiles_map) > 1:
            first_key = next(iter(self._selected_profiles_map))
            self._selected_profiles_map = {first_key: self._selected_profiles_map[first_key]}
        self._populate_profiles()

    def get_profile_mode(self) -> str:
        """Return the active profile mode ('single', 'rotation', or 'batch')."""
        return getattr(self, "profile_mode", "single" if self.mode == "single" else "rotation")

    def retranslateUi(self) -> None:  # type: ignore[override]
        """Update UI texts on language change."""
        self.setWindowTitle(tr_common("Select browser profile"))
        if hasattr(self, "lbl_mode") and self.lbl_mode is not None:
            self.lbl_mode.setText(self.tr("Mode:"))
        if hasattr(self, "mode_combo") and self.mode_combo is not None:
            mode_labels = {
                "single": self.tr("Single profile"),
                "rotation": self.tr("Rotation"),
                "batch": self.tr("Create for each profile"),
            }
            for idx in range(self.mode_combo.count()):
                key = self.mode_combo.itemData(idx)
                if key in mode_labels:
                    self.mode_combo.setItemText(idx, mode_labels[key])
        if hasattr(self, "lbl_browsers") and self.lbl_browsers is not None:
            self.lbl_browsers.setText(self.tr("Browsers:"))
        if hasattr(self, "refresh_btn") and self.refresh_btn is not None:
            self.refresh_btn.setText(self.tr("Refresh"))
        if hasattr(self, "search_line") and self.search_line is not None:
            self.search_line.setPlaceholderText(self.tr("Search by name/email"))
        if hasattr(self, "select_all_btn") and self.select_all_btn is not None:
            self.select_all_btn.setText(self.tr("Add all"))
        if hasattr(self, "deselect_all_btn") and self.deselect_all_btn is not None:
            self.deselect_all_btn.setText(self.tr("Clear selection"))
        if hasattr(self, "button_box") and self.button_box is not None:
            ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
            cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if ok_btn is not None:
                ok_btn.setText(tr_common("Save"))
            if cancel_btn is not None:
                cancel_btn.setText(tr_common("Cancel"))

    def _set_controls_enabled(self, enabled: bool):
        self.browser_combo.setEnabled(enabled)
        self.search_line.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
        self.select_all_btn.setEnabled(enabled)
        self.deselect_all_btn.setEnabled(enabled)
        # The save button depends on selection, but also disables when the dialog is locked
        if hasattr(self, "_ok_button") and self._ok_button is not None:
            if not enabled:
                self._ok_button.setEnabled(False)
            else:
                self._update_save_enabled()

    def _populate_browsers(self):
        self.browser_combo.clear()
        browsers = self.manager.get_supported_browsers()
        for b in browsers:
            self.browser_combo.addItem(b["name"], b["key"])
        select_first_combo_item(self.browser_combo)

    def _clear_profiles_layout(self) -> None:
        for cb in self.profile_checkboxes:
            cb.deleteLater()
        self.profile_checkboxes.clear()

        while self.profile_layout.count():
            child = self.profile_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _populate_profiles(self):
        self._clear_profiles_layout()

        browser_key = self.browser_combo.currentData()
        if not isinstance(browser_key, str):
            lbl = QLabel(self.tr("No profiles found"))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #8A94A6; font-size: 13px;")
            self.profile_layout.addStretch()
            self.profile_layout.addWidget(lbl)
            self.profile_layout.addStretch()
            return

        cached_profiles = self.async_manager.get_cached_profiles(browser_key)
        if cached_profiles is None:
            self._pending_browser_key = browser_key
            self._set_controls_enabled(False)
            self.status_label.setText(self.tr("Loading profiles…"))
            if not self.async_manager.load_browser_profiles_async(
                browser_key, use_cache=True
            ):
                self._pending_browser_key = None
                self._set_controls_enabled(True)
                self.status_label.setText(self.tr("Failed to start loading"))
            return

        self._pending_browser_key = None
        self._set_controls_enabled(True)
        self.status_label.setText("")
        self._render_profiles(browser_key, cached_profiles)

    @staticmethod
    def _get_theme_table_colors(theme_name: str) -> tuple[str, str]:
        """Extract table background-color and alternate-background-color for theme."""
        qss_file = PathManager.qss_dir() / f"{theme_name}.qss"
        if qss_file.exists():
            try:
                content = qss_file.read_text(encoding="utf-8")
                m = re.search(r"QTableView,\s*QTableWidget\s*\{([^}]+)\}", content, re.DOTALL)
                if m:
                    block = m.group(1)
                    bg_m = re.search(r"background-color:\s*([^;]+);", block)
                    alt_m = re.search(r"alternate-background-color:\s*([^;]+);", block)
                    if bg_m and alt_m:
                        return bg_m.group(1).strip(), alt_m.group(1).strip()
            except Exception:
                pass
        return "#14181D", "#1A1F26"

    def _apply_scroll_theme(self) -> None:
        theme = get_current_theme()
        base_bg, _ = self._get_theme_table_colors(theme)
        self.scroll.setStyleSheet(
            f"QScrollArea#profilesScroll {{"
            f"    border: none;"
            f"    border-radius: 0px;"
            f"    background-color: {base_bg};"
            f"}}"
            f"QWidget#profilesScrollViewport, QWidget#profilesContent {{"
            f"    background-color: {base_bg};"
            f"    border-radius: 0px;"
            f"}}"
        )

    def _render_profiles(self, browser_key: str, profiles: list[dict]) -> None:
        self._clear_profiles_layout()

        working_profiles = [dict(profile) for profile in profiles or []]
        query = (self.search_line.text() or "").strip().lower()
        if query:

            def _match(p: dict) -> bool:
                name = str(p.get("email") or p.get("name") or "").lower()
                path = str(p.get("path") or "").lower()
                return query in name or query in path

            working_profiles = [p for p in working_profiles if _match(p)]

        finder = self.manager.finders.get(browser_key)
        if finder:
            for profile in working_profiles:
                profile["browser_key"] = browser_key
                profile["browser_name"] = get_browser_display_name(finder, browser_key)

        logger.debug("_render_profiles: browser_key=%s", browser_key)

        if not working_profiles:
            lbl = QLabel(self.tr("No profiles found"))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #8A94A6; font-size: 13px;")
            self.profile_layout.addStretch()
            self.profile_layout.addWidget(lbl)
            self.profile_layout.addStretch()
            self._update_save_enabled()
            return

        working_profiles.sort(
            key=lambda p: str(p.get("email") or p.get("name") or "").lower()
        )

        theme = get_current_theme()
        base_bg, alt_bg = self._get_theme_table_colors(theme)
        from app.services.theme_registry import theme_registry
        theme_def = theme_registry.get_theme(theme)
        is_dark = theme_def.is_dark if theme_def else True
        accent_color = theme_registry.get_theme_icon_color(theme)
        text_color = "#E0E0E0" if is_dark else "#202020"
        hover_bg = "rgba(255, 255, 255, 0.07)" if is_dark else "rgba(0, 0, 0, 0.04)"

        for idx, profile in enumerate(working_profiles):
            email, p_name = self._parse_profile_parts(profile)
            fallback = self.tr("Unnamed")
            if self.mode == "single":
                cb = ProfileRadioButton(email, p_name, fallback, accent_color, is_dark)
                cb.double_clicked.connect(self._on_profile_double_clicked)
            else:
                cb = ProfileCheckBox(email, p_name, fallback, accent_color, is_dark)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setFixedHeight(32)
            bg_color = base_bg if idx % 2 == 0 else alt_bg
            cb.setStyleSheet(
                f"QRadioButton, QCheckBox {{"
                f"    min-height: 32px;"
                f"    max-height: 32px;"
                f"    padding: 0px 8px 0px 0px;"
                f"    spacing: 10px;"
                f"    border: none;"
                f"    border-radius: 0px;"
                f"    background-color: {bg_color};"
                f"    color: {text_color};"
                f"}}"
                f"QRadioButton::indicator, QCheckBox::indicator {{"
                f"    width: 14px;"
                f"    height: 14px;"
                f"    margin-left: 14px;"
                f"    background: transparent;"
                f"    border: none;"
                f"}}"
                f"QRadioButton:hover, QCheckBox:hover {{"
                f"    background-color: {hover_bg};"
                f"}}"
            )
            cb.profile_data = profile
            key = profile_selection_key(profile)
            cb.profile_key = key
            if self.profile_mode == "rotation" and key in self._selected_profiles_map:
                keys_order = list(self._selected_profiles_map.keys())
                cb.order_number = keys_order.index(key) + 1
            if key in self._selected_profiles_map or key in self.initial_selected_profile_keys:
                cb.setChecked(True)
                self._selected_profiles_map[key] = profile
                if self.mode == "single":
                    self.status_label.setText(self._format_profile_display_name(profile))
            try:
                cb.toggled.connect(
                    lambda checked, p=profile, c=cb: self._on_profile_toggled(p, c, checked)
                )
            except Exception:
                logger.debug(
                    "BrowserProfileDialog: failed to connect toggled for checkbox",
                    exc_info=True,
                )
            self.profile_layout.addWidget(cb)
            self.profile_checkboxes.append(cb)

        self.profile_layout.addStretch()
        self._update_save_enabled()

    def _on_profile_toggled(self, profile: dict, cb: Any, checked: bool) -> None:
        key = profile_selection_key(profile)
        if self.mode == "single":
            if checked:
                self._selected_profiles_map = {key: profile}
                for other_cb in self.profile_checkboxes:
                    if other_cb is not cb and other_cb.isChecked():
                        other_cb.blockSignals(True)
                        other_cb.setChecked(False)
                        other_cb.blockSignals(False)
                p_name = self._format_profile_display_name(profile)
                self.status_label.setText(p_name)
            else:
                self._selected_profiles_map.pop(key, None)
                self.status_label.setText("")
        else:
            if checked:
                self._selected_profiles_map[key] = profile
            else:
                self._selected_profiles_map.pop(key, None)
                self.initial_selected_profile_keys.discard(key)
        if self.profile_mode == "rotation":
            keys_order = list(self._selected_profiles_map.keys())
            for other_cb in self.profile_checkboxes:
                k = getattr(other_cb, "profile_key", None)
                if k in keys_order:
                    other_cb.order_number = keys_order.index(k) + 1
                else:
                    other_cb.order_number = None
                other_cb.update()
        self._update_save_enabled()

    def _on_profile_double_clicked(self) -> None:
        """Accept dialog immediately on double-clicking a profile in single mode."""
        if self._selected_profiles_map:
            self.accept()

    @staticmethod
    def _parse_profile_parts(profile: dict) -> tuple[str, str]:
        email = str(profile.get("email") or "").strip()
        raw_name = str(profile.get("name") or "").strip()
        profile_name = re.sub(
            r"^(?:Profile|Профиль|Профіль)\s+",
            "",
            raw_name,
            flags=re.IGNORECASE,
        ).strip()
        return email, profile_name

    @classmethod
    def _format_profile_display_name(cls, profile: dict) -> str:
        """Return display name in format 'email | name' or fallback to available info."""
        email, profile_name = cls._parse_profile_parts(profile)
        email_login = email.split("@")[0].lower() if "@" in email else email.lower()
        if email and profile_name and profile_name.lower() not in (email.lower(), email_login):
            return f"{email} | {profile_name}"
        if email:
            return email
        return profile_name or QCoreApplication.translate("BrowserProfileDialog", "Unnamed")

    def _on_async_profiles_ready(self, browser_key: str, profiles: list[dict]) -> None:
        current_key = self.browser_combo.currentData()
        if current_key != browser_key:
            return
        self._pending_browser_key = None
        self._set_controls_enabled(True)
        self.status_label.setText("")
        self._render_profiles(browser_key, profiles)

    def _on_async_profiles_error(self, operation: str, message: str) -> None:
        if not isinstance(operation, str) or not operation.startswith("browser_"):
            return
        browser_key = operation.removeprefix("browser_")
        current_key = self.browser_combo.currentData()
        if current_key != browser_key:
            return
        self._pending_browser_key = None
        self._set_controls_enabled(True)
        self.status_label.setText(self.tr("Failed to load profiles"))
        logger.warning(
            "BrowserProfileDialog: async load error for %s: %s",
            browser_key,
            message,
        )

    def closeEvent(self, event):
        try:
            self.async_manager.browser_profiles_ready.disconnect(
                self._on_async_profiles_ready
            )
            self.async_manager.loading_error.disconnect(self._on_async_profiles_error)
        except (TypeError, RuntimeError):
            pass
        super().closeEvent(event)

    def refresh_profiles(self):
        """Manually refresh profiles asynchronously while updating caches and UI."""
        self._set_controls_enabled(False)
        self.status_label.setText(self.tr("Loading profiles…"))
        try:
            async_mgr = _apm.get_async_profile_manager()

            def _on_ready(all_profiles: dict[str, list[dict]]):
                try:
                    # Persist profiles in cache
                    cache = _pc.PersistentProfileCache(default_ttl=None)
                    for key, profiles in (all_profiles or {}).items():
                        try:
                            cache.set(key, profiles)
                        except Exception:
                            logger.debug(
                                "BrowserProfileDialog: persistent cache set failed for %s",
                                key,
                                exc_info=True,
                            )
                    # Update synchronous manager cache (shared cache)
                    mgr = _pm.get_profile_manager()
                    for key, profiles in (all_profiles or {}).items():
                        try:
                            mgr.cache.set(key, profiles)
                        except Exception:
                            logger.debug(
                                "BrowserProfileDialog: runtime cache set failed for %s",
                                key,
                                exc_info=True,
                            )
                    # Rebuild dialog lists
                    self._populate_browsers()
                    self._populate_profiles()
                finally:
                    # Disconnect signals and restore controls
                    try:
                        async_mgr.all_profiles_ready.disconnect(_on_ready)
                        async_mgr.loading_progress.disconnect(_on_progress)
                        async_mgr.loading_error.disconnect(_on_error)
                    except Exception:
                        logger.debug(
                            "BrowserProfileDialog: failed to disconnect async signals",
                            exc_info=True,
                        )
                    self._set_controls_enabled(True)
                    self.status_label.setText("")

            # Subscribe and start loading without using worker RAM cache
            async_mgr.all_profiles_ready.connect(_on_ready)

            def _on_progress(operation: str, current: int, total: int):
                # `operation` is a string like "Loading chrome" from the manager
                try:
                    self.status_label.setText(
                        self.tr("{operation} ({current}/{total})…").format(
                            operation=operation, current=current, total=total
                        )
                    )
                except Exception:
                    logger.debug(
                        "BrowserProfileDialog: failed to update status label on progress",
                        exc_info=True,
                    )

            def _on_error(operation: str, message: str):
                logger.warning("Error during %s: %s", operation, message)
                self.status_label.setText(self.tr("Failed to load profiles"))

            async_mgr.loading_progress.connect(_on_progress)
            async_mgr.loading_error.connect(_on_error)
            async_mgr.load_all_profiles_async(use_cache=False)
        except Exception as e:
            logger.warning("Failed to start profiles refresh: %s", e)
            self._set_controls_enabled(True)
            self.status_label.setText(self.tr("Failed to start loading"))

    def accept(self):
        """Override ``accept`` to persist the selected profiles."""
        self.selected_profiles = list(self._selected_profiles_map.values())
        super().accept()

    def get_selected_profiles(self) -> list[dict]:
        """Return the list of chosen profiles."""
        selected = self.selected_profiles

        logger.debug("get_selected_profiles: returning %s profiles", len(selected))
        for i, profile in enumerate(selected):
            logger.debug(
                "get_selected_profiles: profile %s: name=%s, browser_key=%s",
                i,
                profile.get("name"),
                profile.get("browser_key"),
            )

        return selected

    def _select_all_profiles(self):
        """Select every profile in the list."""
        for cb in self.profile_checkboxes:
            if not cb.isChecked():
                cb.setChecked(True)
        self._update_save_enabled()

    def _deselect_all_profiles(self):
        """Clear selection on every profile."""
        self._selected_profiles_map.clear()
        self.initial_selected_profile_keys.clear()
        for cb in self.profile_checkboxes:
            cb.setChecked(False)
        self._update_save_enabled()

    def _update_save_enabled(self):
        """Enable the Save button when at least one profile is selected."""
        try:
            has_selection = bool(self._selected_profiles_map)
            if hasattr(self, "_ok_button") and self._ok_button is not None:
                self._ok_button.setEnabled(has_selection)
            if hasattr(self, "status_label") and self.status_label is not None and self.mode != "single":
                count = len(self._selected_profiles_map)
                total = len(self.profile_checkboxes)
                if count > 0:
                    self.status_label.setText(
                        self.tr("Selected: {0} of {1}").format(count, total)
                    )
                else:
                    self.status_label.setText("")
        except Exception:
            logger.debug(
                "BrowserProfileDialog: failed to update save enabled state",
                exc_info=True,
            )
