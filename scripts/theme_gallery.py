"""Developer tool: component gallery for visual inspection of all themes.

Run: python scripts/theme_gallery.py
Switching a theme here only restyles the gallery process; settings are not saved.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config_data.runtime_config import runtime_app_config as app_config  # noqa: E402
from app.core.style_manager import StyleManager  # noqa: E402
from app.services.theme_registry import theme_registry  # noqa: E402
from app.services.theme_stylesheet_service import ThemeStylesheetService  # noqa: E402
from app.utils.theme_checker import validate_theme_contrast  # noqa: E402
from app.utils.ui.qt.combo_helpers import identify_combo_popup_view  # noqa: E402

TOKEN_KEYS = [
    "bg_canvas",
    "bg_surface",
    "text_primary",
    "text_secondary",
    "text_accent",
    "text_on_accent",
    "selection_bg",
    "selection_fg",
    "hover_bg",
    "status_error",
    "status_warning",
    "status_success",
    "status_info",
]


class ThemeGallery(QDialog):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Theme Component Gallery")
        self.resize(900, 700)
        self._service = ThemeStylesheetService(app_config)
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Theme:"))
        self._combo = QComboBox()
        identify_combo_popup_view(self._combo)
        for t in theme_registry.list_themes():
            self._combo.addItem(f"{t.name} ({t.theme_id})", t.theme_id)
        self._combo.currentIndexChanged.connect(self._on_changed)
        top.addWidget(self._combo)
        self._badge = QLabel()
        top.addWidget(self._badge)
        top.addStretch()
        root.addLayout(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        grid = QGridLayout(body)

        g = QGroupBox("Buttons")
        v = QVBoxLayout(g)
        v.addWidget(QPushButton("Standard"))
        dis = QPushButton("Disabled")
        dis.setEnabled(False)
        v.addWidget(dis)
        grid.addWidget(g, 0, 0)

        g = QGroupBox("Inputs")
        v = QVBoxLayout(g)
        le = QLineEdit()
        le.setPlaceholderText("Placeholder")
        v.addWidget(le)
        v.addWidget(QLineEdit("Editable text"))
        led = QLineEdit("Disabled")
        led.setEnabled(False)
        v.addWidget(led)
        sp = QSpinBox()
        sp.setValue(42)
        v.addWidget(sp)
        te = QTextEdit()
        te.setPlainText("Multi-line editor")
        te.setMaximumHeight(70)
        v.addWidget(te)
        grid.addWidget(g, 0, 1)

        g = QGroupBox("Choices")
        v = QVBoxLayout(g)
        cb = QComboBox()
        identify_combo_popup_view(cb)
        cb.addItems(["Option A", "Option B", "Option C"])
        v.addWidget(cb)
        c1 = QCheckBox("Unchecked")
        c2 = QCheckBox("Checked")
        c2.setChecked(True)
        c3 = QCheckBox("Disabled checked")
        c3.setChecked(True)
        c3.setEnabled(False)
        r1 = QRadioButton("Radio 1")
        r1.setChecked(True)
        r2 = QRadioButton("Radio 2")
        for w in (c1, c2, c3, r1, r2):
            v.addWidget(w)
        grid.addWidget(g, 1, 0)

        g = QGroupBox("Lists & Tables")
        v = QVBoxLayout(g)
        lw = QListWidget()
        lw.addItems(["Item 1", "Item 2 (selected)", "Item 3"])
        lw.setCurrentRow(1)
        lw.setMaximumHeight(90)
        v.addWidget(lw)
        tw = QTableWidget(2, 2)
        tw.setHorizontalHeaderLabels(["Property", "Value"])
        tw.setItem(0, 0, QTableWidgetItem("Row"))
        tw.setItem(0, 1, QTableWidgetItem("Normal"))
        tw.setItem(1, 0, QTableWidgetItem("Row"))
        tw.setItem(1, 1, QTableWidgetItem("Selected"))
        tw.selectRow(1)
        tw.setMaximumHeight(100)
        v.addWidget(tw)
        grid.addWidget(g, 1, 1)

        self._tokens = QGroupBox("Tokens")
        self._tokens_grid = QGridLayout(self._tokens)
        grid.addWidget(self._tokens, 2, 0, 1, 2)

        scroll.setWidget(body)
        root.addWidget(scroll)
        self._on_changed(self._combo.currentIndex())

    def _on_changed(self, index: int) -> None:
        theme_id = self._combo.itemData(index)
        theme = theme_registry.get_theme(theme_id) if theme_id else None
        if theme is None:
            return
        qss = self._service.load_stylesheet_from_path(theme.theme_id, theme.qss_path)
        if qss:
            StyleManager.apply_qss_string(qss)
        passed, cr, msg = validate_theme_contrast(
            theme.qss_path.read_text(encoding="utf-8"), theme.is_dark, theme.tokens
        )
        self._badge.setText(
            f"{'dark' if theme.is_dark else 'light'} | {cr:.2f}:1 | "
            f"{'PASS' if passed else 'FAIL: ' + msg}"
        )
        while self._tokens_grid.count():
            item = self._tokens_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        tokens = theme_registry.get_theme_tokens(theme.theme_id)
        for i, key in enumerate(TOKEN_KEYS):
            val = tokens.get(key, "#888888")
            lbl = QLabel(f"{key}\n{val}")
            lbl.setFrameShape(QFrame.Shape.StyledPanel)
            lbl.setStyleSheet(
                f"background-color: {val}; color: {'#000' if self._is_light(val) else '#FFF'};"
                " padding: 4px; border: 1px solid #555;"
            )
            self._tokens_grid.addWidget(lbl, i // 5, i % 5)

    @staticmethod
    def _is_light(hex_color: str) -> bool:
        h = hex_color.lstrip("#")
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        try:
            r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return False
        return (0.299 * r + 0.587 * g + 0.114 * b) > 140


def main() -> int:
    app = QApplication(sys.argv)
    dlg = ThemeGallery()
    dlg.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
