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


def test_resolve_search_min_width_guarantees_minimum() -> None:
    min_w = WindowUISetup._resolve_search_min_width()
    assert min_w >= 160


def test_normalize_top_bar_stretches_with_placeholder(qapp: QApplication) -> None:
    window = QMainWindow()
    layout = QHBoxLayout()

    toolbar = QToolBar()
    toolbar.setObjectName("topBarToolbar")
    placeholder = QWidget()
    placeholder.setObjectName("mainSearchPlaceholder")
    theme = QWidget()
    theme.setObjectName("themeSelector")

    layout.addWidget(toolbar)
    layout.addWidget(placeholder)
    layout.addWidget(theme)

    initializer = MagicMock()
    initializer.window = window
    ui_setup = WindowUISetup(initializer)

    ui_setup._normalize_top_bar_stretches(layout)

    assert layout.stretch(layout.indexOf(placeholder)) == 1
    assert layout.stretch(layout.indexOf(toolbar)) == 0
    assert layout.stretch(layout.indexOf(theme)) == 0


def test_common_qss_contains_toolbar_button_styles() -> None:
    from app.core.paths.path_manager import PathManager
    common_path = PathManager.qss_dir() / "common.qss"
    assert common_path.exists()
    content = common_path.read_text(encoding="utf-8")
    assert 'QToolBar#topBarToolbar QToolButton[toolbar_btn="true"]' in content


def test_theme_stylesheet_service_generates_toolbar_overrides() -> None:
    from app.config_data.runtime_config import runtime_app_config
    from app.services.theme_stylesheet_service import ThemeStylesheetService
    service = ThemeStylesheetService(runtime_app_config)
    overrides = service._build_config_overrides_qss()
    assert 'QToolBar#topBarToolbar QToolButton[toolbar_btn="true"]' in overrides


def test_topbar_toolbar_ext_button_alignment(qapp: QApplication) -> None:
    from app.views.main_components.ui.topbar.top_bar_setup import TopBarToolBar
    toolbar = TopBarToolBar(button_height=32)
    toolbar.resize(200, 40)
    ext_btn = toolbar.findChild(QToolButton, "qt_toolbar_ext_button")
    assert ext_btn is not None
    ext_btn.setGeometry(170, 0, 20, 40)
    ext_btn.setVisible(True)

    toolbar._centre_ext_button()
    assert ext_btn.geometry().y() == (40 - 32) // 2
    assert ext_btn.geometry().height() == 32


def test_icon_from_path_fallback_by_link_type(qapp: QApplication) -> None:
    from pathlib import Path
    from app.views.main_components.ui.topbar.toolbar_adapters import _icon_from_path

    # Non-existent path with link_type="folder" should not return empty icon if resolver finds something
    icon = _icon_from_path(Path("non_existent_icon_12345.png"), link_type="folder")
    assert icon is not None


def test_links_toolbar_adapter_rich_tooltip_and_visibility(qapp: QApplication) -> None:
    from app.views.main_components.ui.topbar.toolbar_adapters import LinksToolbarAdapter

    toolbar = QToolBar()
    adapter = LinksToolbarAdapter(
        toolbar,
        insert_before=None,
        button_object_name="favButton",
        group_name="fav",
    )

    data = [
        {
            "name": "Project Docs",
            "path": "/path/to/docs",
            "category_name": "Work",
            "last_opened_at": "2026-09-16 10:00",
            "type": "folder",
        }
    ]
    adapter.set_data(data)

    actions = adapter.actions
    assert len(actions) == 1
    action = actions[0]

    tooltip = action.toolTip()
    assert "<b>Project Docs</b>" in tooltip
    assert "📍 /path/to/docs" in tooltip
    assert "📁 Work" in tooltip
    assert "🕐 2026-09-16 10:00" in tooltip

    # Test set_actions_visible and backward-compatibility alias setVisible
    assert action.isVisible() is True
    adapter.set_actions_visible(False)
    assert action.isVisible() is False
    adapter.setVisible(True)
    assert action.isVisible() is True


def test_auto_hide_tree_filter_threshold_and_screen_scale(qapp: QApplication) -> None:
    from unittest.mock import patch
    from PyQt6.QtWidgets import QSplitter, QStackedWidget
    from app.views.main_components.ui.window_ui_setup import _AutoHideTreeFilter

    window = QMainWindow()
    splitter = QSplitter(window)
    splitter.resize(1000, 600)
    left_panel = QWidget()
    right_panel = QWidget()
    splitter.addWidget(left_panel)
    splitter.addWidget(right_panel)
    splitter.setCollapsible(0, False)
    splitter.setSizes([250, 750])

    stack = QStackedWidget(window)
    table = QWidget()
    stack.addWidget(table)

    window.splitter = splitter
    window.stack = stack
    window.table = table
    window.left_panel = left_panel

    filter_obj = _AutoHideTreeFilter(window, threshold_width=320, default_sizes=[250, 750])

    # Test scale threshold property
    assert filter_obj.base_threshold == 320
    # On 1.0 DPR
    with patch.object(filter_obj, "_get_screen_scale", return_value=1.0):
        assert filter_obj.threshold == 320

    # On 1.25 DPR (125% scale)
    with patch.object(filter_obj, "_get_screen_scale", return_value=1.25):
        assert filter_obj.threshold == 400

    # On 1.5 DPR (150% scale)
    with patch.object(filter_obj, "_get_screen_scale", return_value=1.5):
        assert filter_obj.threshold == 480

    # Test collapse and restore logic:
    # 1. Initially manual collapsing is disabled
    assert splitter.isCollapsible(0) is False

    # 2. Collapse
    filter_obj._handle_narrow_window(splitter, stack, table, 300)
    assert filter_obj._is_collapsed is True
    assert splitter.sizes()[0] == 0

    # 3. Restore
    filter_obj._handle_wide_window(splitter, stack)
    assert filter_obj._is_collapsed is False
    assert abs(splitter.sizes()[0] - 250) <= 2
    # Manual collapsing is re-disabled
    assert splitter.isCollapsible(0) is False


