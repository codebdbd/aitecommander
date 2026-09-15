from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

from app.models.types.link_type import LinkType
from app.views.windows.dialogs.link_dialog.link_dialog import LinkDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_link_dialog_apps_btn_toggle(qapp):
    init_data = {"category_hierarchy": {}, "spheres": []}
    mock_controller = MagicMock()
    dialog = LinkDialog(
        initialization_data=init_data,
        dialog_controller=mock_controller,
        link={"type": "web"},
    )
    apps_btn = dialog._get_apps_btn()
    assert apps_btn is not None
    # For web link, apps_btn should be hidden
    assert apps_btn.isHidden()

    # Switch to program
    dialog.handlers.on_type_changed(LinkType.PROGRAM)
    assert not apps_btn.isHidden()

    # Switch to file
    dialog.handlers.on_type_changed(LinkType.FILE)
    assert apps_btn.isHidden()

    dialog.close()


def test_installed_apps_dialog_bottom_layout(qapp):
    from PyQt6.QtWidgets import QHBoxLayout

    from app.views.windows.dialogs.installed_apps_dialog import InstalledAppsDialog

    dlg = InstalledAppsDialog()
    assert dlg.count_label is not None
    assert dlg.button_box is not None

    found = False
    for i in range(dlg.layout().count()):
        item = dlg.layout().itemAt(i)
        lay = item.layout()
        if isinstance(lay, QHBoxLayout):
            widgets = [lay.itemAt(j).widget() for j in range(lay.count()) if lay.itemAt(j).widget() is not None]
            if dlg.count_label in widgets and dlg.button_box in widgets:
                assert widgets.index(dlg.count_label) < widgets.index(dlg.button_box)
                found = True
                break

    assert found, "count_label and button_box should be in the same bottom row"
    assert getattr(dlg.apps_list.itemDelegate(), "_target_height", None) == 42
    if hasattr(dlg, "loader_thread"):
        dlg.loader_thread.cancel()
        dlg.loader_thread.quit()
        dlg.loader_thread.wait(1000)
    dlg.close()


def test_link_dialog_button_widths_adjust(qapp):
    from PyQt6.QtWidgets import QPushButton

    from app.views.windows.dialogs.link_dialog.link_dialog_ui import LinkDialogUI

    btn = QPushButton("Test")
    LinkDialogUI.adjust_button_width(btn, min_width=115, padding=28)
    assert btn.width() >= 115

    # Long text expands width
    long_btn = QPushButton("Профили (120)")
    LinkDialogUI.adjust_button_width(long_btn, min_width=115, padding=28)
    assert long_btn.width() >= 115
    assert long_btn.width() >= long_btn.fontMetrics().horizontalAdvance("Профили (120)") + 28

    # Dialog dynamic profile button adjustment
    init_data = {"category_hierarchy": {}, "spheres": []}
    mock_controller = MagicMock()
    dialog = LinkDialog(
        initialization_data=init_data,
        dialog_controller=mock_controller,
        link={"type": "web"},
    )
    profile_btn = dialog._get_profile_btn()
    assert profile_btn.width() >= 115

    # Select 12 profiles
    dialog.selected_profiles = [{"directory": f"Profile {i}", "name": f"User {i}"} for i in range(12)]
    dialog._update_profile_button_state()
    assert "12" in profile_btn.text()
    assert profile_btn.width() >= 115
    assert profile_btn.width() >= profile_btn.fontMetrics().horizontalAdvance(profile_btn.text()) + 20

    dialog.close()


