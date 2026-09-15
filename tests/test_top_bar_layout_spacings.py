from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QToolBar,
    QToolButton,
    QWidget,
)

from app.views.main_components.ui.topbar.toolbar_adapters import ToolbarActionAdapter
from app.views.main_components.ui.window_ui_setup import WindowUISetup

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_normalize_top_bar_stretches_keeps_spacers_fixed(qapp: QApplication) -> None:
    window = QMainWindow()
    layout = QHBoxLayout()

    toolbar = QToolBar()
    vsep1 = QWidget()
    search = QLineEdit()
    search.setObjectName("mainSearch")
    vsep2 = QWidget()
    theme = QWidget()

    layout.addWidget(toolbar)
    layout.addSpacing(4)
    layout.addWidget(vsep1)
    layout.addSpacing(4)
    layout.addWidget(search)
    layout.addSpacing(4)
    layout.addWidget(vsep2)
    layout.addSpacing(4)
    layout.addWidget(theme)

    window.search = search

    initializer = MagicMock()
    initializer.window = window
    ui_setup = WindowUISetup(initializer)

    ui_setup._normalize_top_bar_stretches(layout)

    # Search widget must have stretch = 1
    assert layout.stretch(layout.indexOf(search)) == 1

    # Toolbar and theme must have stretch = 0
    assert layout.stretch(layout.indexOf(toolbar)) == 0
    assert layout.stretch(layout.indexOf(vsep1)) == 0
    assert layout.stretch(layout.indexOf(vsep2)) == 0
    assert layout.stretch(layout.indexOf(theme)) == 0

    # All spacers must have stretch = 0 (not stretch = 1)
    for i in range(layout.count()):
        it = layout.itemAt(i)
        if it.spacerItem() is not None:
            assert layout.stretch(i) == 0, f"Spacer at index {i} must have stretch 0, got {layout.stretch(i)}"


def test_toolbar_adapter_set_button_last_unpolish_polish(qapp: QApplication) -> None:
    toolbar = QToolBar()
    adapter = ToolbarActionAdapter(
        toolbar,
        insert_before=None,
        button_object_name="testButton",
        button_size=toolbar.iconSize(),
        icon_size=toolbar.iconSize(),
    )

    btn = QToolButton(toolbar)
    btn.setProperty("toolbar_btn", True)

    adapter._set_button_last(btn, True)
    assert btn.property("toolbar_last") is True

    adapter._set_button_last(btn, False)
    assert btn.property("toolbar_last") is False
