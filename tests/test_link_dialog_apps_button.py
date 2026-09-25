from unittest.mock import MagicMock, patch

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


def test_link_dialog_edit_mode_shows_only_current_link_type(qapp):
    init_data = {"category_hierarchy": {}, "spheres": []}
    dialog = LinkDialog(
        initialization_data=init_data,
        dialog_controller=MagicMock(),
        link={"type": "program"},
    )

    group = dialog._get_type_group()
    assert group is None or len(group.buttons()) == 0
    assert dialog.link_type == "program"

    dialog.close()


def test_link_dialog_new_link_hides_note_type(qapp):
    init_data = {"category_hierarchy": {}, "spheres": []}
    dialog = LinkDialog(
        initialization_data=init_data,
        dialog_controller=MagicMock(),
    )

    type_codes = [
        button.property("link_type") for button in dialog._get_type_group().buttons()
    ]

    assert "note" not in type_codes
    assert set(type_codes) == {"web", "file", "folder", "program", "script"}
    dialog.close()


def test_link_dialog_edit_mode_normalizes_legacy_note_type(qapp):
    init_data = {"category_hierarchy": {}, "spheres": []}
    dialog = LinkDialog(
        initialization_data=init_data,
        dialog_controller=MagicMock(),
        link={"type": "note"},
    )

    group = dialog._get_type_group()
    assert group is None or len(group.buttons()) == 0
    assert dialog.link_type == "web"
    dialog.close()


def test_link_dialog_fixed_type_shows_only_quick_add_type(qapp):
    init_data = {"category_hierarchy": {}, "spheres": []}
    dialog = LinkDialog(
        initialization_data=init_data,
        dialog_controller=MagicMock(),
        link=None,
        fixed_link_type="web",
    )

    group = dialog._get_type_group()
    assert group is None or len(group.buttons()) == 0
    assert dialog.link_type == "web"

    dialog.close()


def test_link_dialog_type_section_has_no_label_and_compact_height(qapp):
    init_data = {"category_hierarchy": {}, "spheres": []}
    dialog = LinkDialog(
        initialization_data=init_data,
        dialog_controller=MagicMock(),
        link={"type": "web"},
    )

    assert not hasattr(dialog.ui, "lbl_link_type")
    assert dialog.width() == 600
    assert dialog.height() > 0

    dialog.close()


def test_link_dialog_programmatic_type_change_collects_string_code(qapp):
    init_data = {"category_hierarchy": {}, "spheres": []}
    dialog = LinkDialog(
        initialization_data=init_data,
        dialog_controller=MagicMock(),
        link=None,
        fixed_link_type="web",
    )

    dialog.set_link_type(LinkType.WEB)
    form_data = dialog.handlers._collect_form_data()

    assert form_data["link_type"] == "web"

    dialog.close()


def test_link_dialog_defers_sphere_icon_loading_until_after_show(qapp):
    init_data = {
        "category_hierarchy": {},
        "spheres": [
            {"id": 1, "name": "Work", "icon_path": "work.png"},
            {"id": 2, "name": "Home", "icon_path": "home.png"},
        ],
    }

    with patch(
        "app.views.windows.dialogs.link_dialog.link_dialog.get_cached_icon_with_fallback"
    ) as icon_loader:
        icon_loader.return_value = None
        dialog = LinkDialog(
            initialization_data=init_data,
            dialog_controller=MagicMock(),
            link={"type": "web"},
        )

        assert dialog._get_sphere_cb().count() == 2
        icon_loader.assert_not_called()

        dialog._apply_sphere_icons()

        assert icon_loader.call_count == 2
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
    profile_btn = dialog._get_profile_select_btn()
    assert profile_btn.width() >= 115

    # Select 12 profiles
    dialog.profile_mode = "batch"
    dialog.selected_profiles = [{"directory": f"Profile {i}", "name": f"User {i}"} for i in range(12)]
    dialog.handlers._update_profile_ui_state()
    assert "12" in dialog._get_profile_le().text()
    assert profile_btn.width() >= 115

    dialog.close()
