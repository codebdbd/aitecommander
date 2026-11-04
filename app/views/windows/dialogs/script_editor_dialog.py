"""Dialog for creating or editing a script directly inside Aite Commander."""

from __future__ import annotations

import logging
import re
from typing import Optional

from PyQt6.QtCore import QCoreApplication, QEvent, QSize, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QKeyEvent,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialogButtonBox,
    QFileDialog,
    QFileIconProvider,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.controllers.ui.theme_controller import theme_registry
from app.services.dialog_path_service import DialogPathService
from app.services.script_storage_service import ScriptStorageService
from app.utils.i18n.common import tr as tr_common
from app.utils.ui.icon.path_service import get_current_theme
from app.utils.ui.qt.combo_helpers import PopupComboBox
from app.views.windows.dialogs.base_dialog import BaseDialog
from app.views.windows.dialogs.installed_apps_dialog import IconTextPushButton

logger = logging.getLogger(__name__)

def tr_script_ui(context: str, source: str) -> str:
    """Translate string via Qt translator."""
    return QCoreApplication.translate(context, source)

# lupdate hints for ScriptEditorDialog
if False:  # pragma: no cover
    QCoreApplication.translate("ScriptEditorDialog", "Script Editor")
    QCoreApplication.translate("ScriptEditorDialog", "Type:")
    QCoreApplication.translate("ScriptEditorDialog", "Paste from clipboard")
    QCoreApplication.translate("ScriptEditorDialog", "Clear")
    QCoreApplication.translate(
        "ScriptEditorDialog",
        "Paste ready script code from AI chat here (Ctrl+V)...",
    )
    QCoreApplication.translate("ScriptEditorDialog", "Keep console open")
    QCoreApplication.translate("ScriptEditorDialog", "Find on computer")
    QCoreApplication.translate("ScriptEditorDialog", "Select Script")
    QCoreApplication.translate(
        "ScriptEditorDialog",
        "Scripts (*.ps1 *.bat *.cmd *.py *.pyw *.vbs *.js);;All files (*.*)",
    )


class _ScriptSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for PowerShell, Batch, Python, and VBScript."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rules: list[tuple[re.Pattern, QTextCharFormat]] = []

    def configure(self, ext: str, is_dark: bool) -> None:
        self._rules.clear()
        ext = (ext or ".ps1").lower()

        kw_color = QColor("#569CD6") if is_dark else QColor("#0000FF")
        str_color = QColor("#CE9178") if is_dark else QColor("#A31515")
        comm_color = QColor("#6A9955") if is_dark else QColor("#008000")
        num_color = QColor("#B5CEA8") if is_dark else QColor("#098658")
        var_color = QColor("#9CDCFE") if is_dark else QColor("#001080")

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(kw_color)
        kw_fmt.setFontWeight(QFont.Weight.Bold)

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(str_color)

        comm_fmt = QTextCharFormat()
        comm_fmt.setForeground(comm_color)
        comm_fmt.setFontItalic(True)

        num_fmt = QTextCharFormat()
        num_fmt.setForeground(num_color)

        var_fmt = QTextCharFormat()
        var_fmt.setForeground(var_color)

        self._rules.append((re.compile(r"\b\d+(\.\d+)?\b"), num_fmt))
        self._rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), str_fmt))
        self._rules.append((re.compile(r"'[^'\\]*(\\.[^'\\]*)*'"), str_fmt))

        if ext == ".ps1":
            keywords = [
                "if", "else", "elseif", "switch", "foreach", "for", "while", "do",
                "until", "function", "filter", "param", "begin", "process", "end",
                "try", "catch", "finally", "throw", "return", "break", "continue",
                "exit", "in",
            ]
            self._rules.append(
                (re.compile(r"\b(" + "|".join(keywords) + r")\b", re.IGNORECASE), kw_fmt)
            )
            self._rules.append((re.compile(r"\b[A-Za-z]+-[A-Za-z0-9]+\b"), kw_fmt))
            self._rules.append((re.compile(r"\$[A-Za-z0-9_:]+"), var_fmt))
            self._rules.append((re.compile(r"#.*$"), comm_fmt))
        elif ext in (".bat", ".cmd"):
            keywords = [
                "echo", "off", "on", "set", "setlocal", "endlocal", "if", "else",
                "not", "exist", "defined", "errorlevel", "for", "in", "do", "call",
                "goto", "exit", "pause", "start", "chcp", "cd", "pushd", "popd",
            ]
            self._rules.append(
                (re.compile(r"(?:@|\b)(" + "|".join(keywords) + r")\b", re.IGNORECASE), kw_fmt)
            )
            self._rules.append((re.compile(r"%[A-Za-z0-9_~:*]+%?"), var_fmt))
            self._rules.append((re.compile(r"(?i)^\s*(?:rem\b|::).*$"), comm_fmt))
        elif ext in (".py", ".pyw"):
            keywords = [
                "and", "as", "assert", "async", "await", "break", "class", "continue",
                "def", "del", "elif", "else", "except", "finally", "for", "from",
                "global", "if", "import", "in", "is", "lambda", "nonlocal", "not",
                "or", "pass", "raise", "return", "try", "while", "with", "yield",
                "None", "True", "False", "self",
            ]
            self._rules.append((re.compile(r"\b(" + "|".join(keywords) + r")\b"), kw_fmt))
            self._rules.append((re.compile(r"#.*$"), comm_fmt))
        elif ext == ".vbs":
            keywords = [
                "Dim", "Set", "If", "Then", "Else", "ElseIf", "End", "For", "Each",
                "In", "Next", "While", "Wend", "Do", "Loop", "Until", "Sub", "Function",
                "Exit", "Option", "Explicit", "On", "Error", "Resume", "Nothing",
                "True", "False", "Call", "CreateObject", "MsgBox",
            ]
            self._rules.append(
                (re.compile(r"\b(" + "|".join(keywords) + r")\b", re.IGNORECASE), kw_fmt)
            )
            self._rules.append((re.compile(r"'.*$"), comm_fmt))
        else:
            self._rules.append((re.compile(r"#.*$"), comm_fmt))

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class ScriptEditorDialog(BaseDialog):
    """Modal editor to paste/write a script or fall back to picking a file on disk."""

    _SCRIPT_TYPES: tuple[tuple[str, str], ...] = (
        ("PowerShell (.ps1)", ".ps1"),
        ("Batch (.bat)", ".bat"),
        ("Command Script (.cmd)", ".cmd"),
        ("Python (.py)", ".py"),
        ("Python GUI (.pyw)", ".pyw"),
        ("VBScript (.vbs)", ".vbs"),
    )

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        initial_code: str = "",
        initial_ext: str = ".ps1",
        initial_keep_open: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ScriptEditorDialog")
        self.setMinimumSize(660, 480)
        self.resize(700, 540)

        self._selected_disk_path: Optional[str] = None
        self._user_manually_changed_ext = False
        self._icon_provider = QFileIconProvider()

        self._setup_ui(
            initial_code=initial_code,
            initial_ext=initial_ext,
            initial_keep_open=initial_keep_open,
        )
        self.retranslateUi()
        self._update_save_state()

    def tr(
        self,
        sourceText: str | None,
        disambiguation: str | None = None,
        n: int = -1,
    ) -> str:
        if not sourceText:
            return ""
        return tr_script_ui("ScriptEditorDialog", sourceText)

    def _get_browse_disk_icon(self) -> QIcon:
        icon_path = app_config.paths.get_ui_icons_dir() / "folder_icon.png"
        if icon_path.exists():
            return QIcon(str(icon_path))
        return self._icon_provider.icon(QFileIconProvider.IconType.Folder)

    def _is_dark_theme(self) -> bool:
        try:
            current_theme_id = get_current_theme()
            theme = theme_registry.get_theme(current_theme_id)
            return bool(theme and theme.is_dark)
        except Exception:
            return False

    def _setup_ui(
        self,
        *,
        initial_code: str,
        initial_ext: str,
        initial_keep_open: bool,
    ) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 1. Top bar: script type combo + Paste / Clear buttons
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        self.type_label = QLabel(self.tr("Type:"))
        top_row.addWidget(self.type_label)

        self.type_cb = PopupComboBox()
        self.type_cb.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        for label, ext_val in self._SCRIPT_TYPES:
            self.type_cb.addItem(label, userData=ext_val)

        # Select initial extension
        norm_ext = (initial_ext or ".ps1").lower()
        found_idx = -1
        for i in range(self.type_cb.count()):
            if self.type_cb.itemData(i) == norm_ext:
                found_idx = i
                break
        if found_idx >= 0:
            self.type_cb.setCurrentIndex(found_idx)
        elif norm_ext:
            custom_label = f"Script ({norm_ext})"
            self.type_cb.addItem(custom_label, userData=norm_ext)
            self.type_cb.setCurrentIndex(self.type_cb.count() - 1)

        self.type_cb.currentIndexChanged.connect(self._on_type_combo_changed)
        top_row.addWidget(self.type_cb)

        top_row.addStretch(1)

        self.paste_btn = QPushButton(self.tr("Paste from clipboard"))
        self.paste_btn.clicked.connect(self._on_paste_from_clipboard)
        top_row.addWidget(self.paste_btn)

        self.clear_btn = QPushButton(self.tr("Clear"))
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        top_row.addWidget(self.clear_btn)

        layout.addLayout(top_row)

        # 2. Code editor
        self.code_edit = QPlainTextEdit()
        self.code_edit.setObjectName("scriptCodePlainTextEdit")
        mono_font = QFont("Cascadia Code", 10)
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        if not mono_font.exactMatch():
            mono_font = QFont("Consolas", 10)
            mono_font.setStyleHint(QFont.StyleHint.Monospace)
        self.code_edit.setFont(mono_font)
        self.code_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.highlighter = _ScriptSyntaxHighlighter(self.code_edit.document())
        self.highlighter.configure(self.get_selected_extension(), self._is_dark_theme())

        if initial_code:
            self.code_edit.setPlainText(initial_code)
            self._user_manually_changed_ext = True

        self.code_edit.textChanged.connect(self._update_save_state)
        self.code_edit.installEventFilter(self)
        layout.addWidget(self.code_edit, 1)

        # 3. Bottom row: Find on computer (left), Keep console open, Save/Cancel (right)
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(12)

        self.browse_disk_btn = IconTextPushButton(self.tr("Find on computer"))
        self.browse_disk_btn.setIcon(self._get_browse_disk_icon())
        self.browse_disk_btn.setIconSize(QSize(16, 16))
        self.browse_disk_btn.setMinimumHeight(32)
        self.browse_disk_btn.clicked.connect(self._on_browse_disk)
        bottom_layout.addWidget(self.browse_disk_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self.keep_open_chk = QCheckBox(self.tr("Keep console open"))
        self.keep_open_chk.setChecked(bool(initial_keep_open))
        bottom_layout.addWidget(self.keep_open_chk, 0, Qt.AlignmentFlag.AlignVCenter)

        bottom_layout.addStretch(1)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        if self.button_box.layout() is not None:
            self.button_box.layout().setSpacing(8)
        self.ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.cancel_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        if self.ok_button:
            self.ok_button.setText(tr_common("Save"))
        if self.cancel_button:
            self.cancel_button.setText(tr_common("Cancel"))

        self.button_box.accepted.connect(self._on_accepted)
        self.button_box.rejected.connect(self.reject)
        bottom_layout.addWidget(self.button_box, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(bottom_layout)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.code_edit is not None:
            self.code_edit.setFocus()

    def _on_type_combo_changed(self, _index: int) -> None:
        self._user_manually_changed_ext = True
        ext = self.get_selected_extension()
        if hasattr(self, "highlighter") and self.highlighter is not None:
            self.highlighter.configure(ext, self._is_dark_theme())
            self.highlighter.rehighlight()

    def _set_extension_programmatically(self, ext: str) -> None:
        norm_ext = (ext or ".ps1").lower()
        found_idx = -1
        for i in range(self.type_cb.count()):
            if self.type_cb.itemData(i) == norm_ext:
                found_idx = i
                break
        if found_idx == -1 and norm_ext:
            custom_label = f"Script ({norm_ext})"
            self.type_cb.addItem(custom_label, userData=norm_ext)
            found_idx = self.type_cb.count() - 1

        if found_idx >= 0:
            self.type_cb.blockSignals(True)
            try:
                self.type_cb.setCurrentIndex(found_idx)
            finally:
                self.type_cb.blockSignals(False)
            if hasattr(self, "highlighter") and self.highlighter is not None:
                self.highlighter.configure(norm_ext, self._is_dark_theme())
                self.highlighter.rehighlight()

    def _apply_pasted_text(self, raw_text: str, replace_all: bool = False) -> None:
        if not raw_text:
            return
        cleaned, detected_ext = ScriptStorageService.clean_and_detect_script(raw_text)
        was_empty = not self.code_edit.toPlainText().strip()

        if replace_all or was_empty:
            self.code_edit.setPlainText(cleaned)
        else:
            self.code_edit.insertPlainText(cleaned)

        if detected_ext and (was_empty or replace_all or not self._user_manually_changed_ext):
            self._set_extension_programmatically(detected_ext)

    def _on_paste_from_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        text = clipboard.text()
        if text:
            self._apply_pasted_text(text, replace_all=not self.code_edit.toPlainText().strip())
            self.code_edit.setFocus()

    def _on_clear_clicked(self) -> None:
        self.code_edit.clear()
        self._user_manually_changed_ext = False
        self.code_edit.setFocus()

    def _update_save_state(self) -> None:
        has_code = bool(self.code_edit.toPlainText().strip())
        if self.ok_button is not None:
            self.ok_button.setEnabled(has_code)

    def _on_accepted(self) -> None:
        if self.code_edit.toPlainText().strip():
            self._selected_disk_path = None
            self.accept()

    def _on_browse_disk(self) -> None:
        filters = self.tr(
            "Scripts (*.ps1 *.bat *.cmd *.py *.pyw *.vbs *.js);;All files (*.*)"
        )
        start_dir = DialogPathService.get_downloads_dir("Scripts")
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Select Script"),
            start_dir,
            filters,
        )
        if path:
            DialogPathService.remember_dir("Scripts", path)
            self._selected_disk_path = path
            self.accept()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.code_edit and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            mods = event.modifiers()

            if key == Qt.Key.Key_Tab and mods == Qt.KeyboardModifier.NoModifier:
                self.code_edit.insertPlainText("    ")
                return True

            if mods == Qt.KeyboardModifier.ControlModifier:
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_S):
                    if self.code_edit.toPlainText().strip():
                        self._on_accepted()
                    return True
                if key == Qt.Key.Key_V:
                    # If editor is empty or all text is selected, clean markdown fences on paste
                    cursor = self.code_edit.textCursor()
                    full_len = len(self.code_edit.toPlainText())
                    is_empty_or_all = (full_len == 0) or (
                        cursor.hasSelection() and len(cursor.selectedText()) == full_len
                    )
                    if is_empty_or_all:
                        clipboard = QApplication.clipboard()
                        raw = clipboard.text() if clipboard else ""
                        if raw:
                            self._apply_pasted_text(raw, replace_all=True)
                            return True
                if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                    self.code_edit.zoomIn(1)
                    return True
                if key == Qt.Key.Key_Minus:
                    self.code_edit.zoomOut(1)
                    return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            event.modifiers() == Qt.KeyboardModifier.ControlModifier
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_S)
        ):
            if self.code_edit.toPlainText().strip():
                self._on_accepted()
                return
        super().keyPressEvent(event)

    def get_script_code(self) -> str:
        """Return script code text."""
        return self.code_edit.toPlainText()

    def get_selected_extension(self) -> str:
        """Return currently selected file extension (e.g., '.ps1')."""
        data = self.type_cb.currentData()
        return str(data) if data else ".ps1"

    def get_keep_console_open(self) -> bool:
        """Return True if 'Keep console open' checkbox is checked."""
        return bool(self.keep_open_chk.isChecked())

    def get_selected_disk_path(self) -> Optional[str]:
        """Return path if user chose an existing file on disk via 'Find on computer'."""
        return self._selected_disk_path

    def retranslateUi(self) -> None:
        """Update UI strings when language changes."""
        self.setWindowTitle(self.tr("Script Editor"))
        if hasattr(self, "type_label") and self.type_label is not None:
            self.type_label.setText(self.tr("Type:"))
        if hasattr(self, "paste_btn") and self.paste_btn is not None:
            self.paste_btn.setText(self.tr("Paste from clipboard"))
            self.adjust_button_width(self.paste_btn, min_width=110)
        if hasattr(self, "clear_btn") and self.clear_btn is not None:
            self.clear_btn.setText(self.tr("Clear"))
            self.adjust_button_width(self.clear_btn, min_width=85)
        if hasattr(self, "code_edit") and self.code_edit is not None:
            self.code_edit.setPlaceholderText(
                self.tr("Paste ready script code from AI chat here (Ctrl+V)...")
            )
        if hasattr(self, "keep_open_chk") and self.keep_open_chk is not None:
            self.keep_open_chk.setText(self.tr("Keep console open"))
        if hasattr(self, "ok_button") and self.ok_button is not None:
            self.ok_button.setText(tr_common("Save"))
        if hasattr(self, "cancel_button") and self.cancel_button is not None:
            self.cancel_button.setText(tr_common("Cancel"))
        if hasattr(self, "button_box") and self.button_box is not None:
            self.equalize_button_box(
                self.button_box, min_width=app_config.ui.get_fixed_button_width()
            )
        if hasattr(self, "browse_disk_btn") and self.browse_disk_btn is not None:
            self.browse_disk_btn.setText(self.tr("Find on computer"))
            self.browse_disk_btn.setIcon(self._get_browse_disk_icon())
            self.browse_disk_btn.setIconSize(QSize(16, 16))
            self.adjust_button_width(
                self.browse_disk_btn, min_width=app_config.ui.get_fixed_button_width()
            )
