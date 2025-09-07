import sys

import pytest
from PyQt6.QtWidgets import QApplication

from app.views.dialogs.link_dialog.link_dialog import LinkDialog


class StubDialogController:
    def __init__(self, sections_by_sphere, cats_by_section):
        self._sections_by_sphere = sections_by_sphere
        self._cats_by_section = cats_by_section

    # Протоколы требуют эти методы
    def get_sections_for_sphere(self, sphere_id: int):
        return self._sections_by_sphere.get(sphere_id, [])

    def get_categories_for_section(self, section_id: int):
        return self._cats_by_section.get(section_id, [])

    # Для LinkDataControllerProtocol (делаем no-op в этих smoke тестах)
    def validate_and_save(self, form_data):
        return {"is_valid": True}


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_dialog(init_data):
    controller = StubDialogController(
        sections_by_sphere={
            1: [{"id": 10, "name": "A", "icon_path": ""}],
        },
        cats_by_section={
            10: [{"id": 100, "name": "CA", "icon_path": ""}],
        },
    )
    return LinkDialog(
        initialization_data=init_data,
        dialog_controller=controller,
        link=None,
        category_id=None,
        parent=None,
        link_controller=controller,  # удовлетворяем протокол валидации
    )


@pytest.mark.parametrize(
    "target, expect_profile, expect_browse, expect_args",
    [
        ("web", True, False, True),
        ("file", False, True, False),
        ("program", False, True, True),
    ],
)
def test_set_link_type_smoke_updates_visibility_and_clears_fields(qapp, target, expect_profile, expect_browse, expect_args):
    init_data = {
        "spheres": [
            {"id": 1, "name": "S1"},
        ],
        # category_hierarchy не важна для этих тестов
    }
    dlg = _make_dialog(init_data)

    # Заполним поля не пустыми значениями
    dlg.ui.set_widget_value("url_le", "something")
    dlg.ui.set_widget_value("name_le", "some name")
    dlg.ui.set_widget_value("args_le", "--flag")

    # Действие: смена типа программно
    dlg.set_link_type(target)

    # Поля должны быть очищены согласно TypeChangeMixin.on_type_changed
    assert dlg.ui.get_widget("url_le").text() == ""
    assert dlg.ui.get_widget("name_le").text() == ""
    assert dlg.ui.get_widget("args_le").text() == ""

    # Видимость контролов согласно _update_ui_state (используем isHidden для независимости от показа окна)
    assert dlg.ui.get_widget("profile_btn").isHidden() is (not expect_profile)
    assert dlg.ui.get_widget("browse_btn").isHidden() is (not expect_browse)
    assert dlg.ui.get_widget("args_le").isHidden() is (not expect_args)
    assert dlg.ui.get_widget("args_label").isHidden() is (not expect_args)
