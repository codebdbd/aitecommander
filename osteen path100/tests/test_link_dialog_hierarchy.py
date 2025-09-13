import sys

import pytest
from PyQt6.QtWidgets import QApplication

from app.views.dialogs.link_dialog.link_dialog import LinkDialog


class StubDialogController:
    def __init__(self, sections_by_sphere, cats_by_section):
        self._sections_by_sphere = sections_by_sphere
        self._cats_by_section = cats_by_section

    def get_sections_for_sphere(self, sphere_id: int):
        return self._sections_by_sphere.get(sphere_id, [])

    def get_categories_for_section(self, section_id: int):
        return self._cats_by_section.get(section_id, [])


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _make_dialog(init_data, controller, category_id=None):
    # link_controller аргумент опционален и не требуется для этих тестов
    return LinkDialog(
        initialization_data=init_data,
        dialog_controller=controller,
        link=None,
        category_id=category_id,
        parent=None,
        link_controller=None,
    )


def test_populate_hierarchy_with_category_hierarchy_applies_selection(qapp):
    spheres = [
        {"id": 1, "name": "Work"},
        {"id": 2, "name": "Home"},
    ]
    sections_by_sphere = {
        2: [
            {"id": 10, "name": "Apps", "icon_path": ""},
            {"id": 11, "name": "Docs", "icon_path": ""},
        ]
    }
    cats_by_section = {
        11: [
            {"id": 101, "name": "Guides", "icon_path": ""},
            {"id": 102, "name": "Specs", "icon_path": ""},
        ]
    }

    init_data = {
        "spheres": spheres,
        "category_hierarchy": {"sphere_id": 2, "section_id": 11, "category_id": 102},
    }

    controller = StubDialogController(sections_by_sphere, cats_by_section)
    dlg = _make_dialog(init_data, controller, category_id=999)

    sphere_cb = dlg.ui.get_widget("sphere_cb")
    section_cb = dlg.ui.get_widget("section_cb")
    category_cb = dlg.ui.get_widget("category_cb")

    # Проверка, что текущие значения совпадают с иерархией
    assert sphere_cb.currentData() == 2
    assert section_cb.currentData() == 11
    assert category_cb.currentData() == 102


def test_populate_hierarchy_default_selects_first(qapp):
    spheres = [
        {"id": 5, "name": "Alpha"},
        {"id": 6, "name": "Beta"},
    ]
    sections_by_sphere = {
        5: [
            {"id": 50, "name": "SecA", "icon_path": ""},
        ]
    }
    cats_by_section = {
        50: [
            {"id": 500, "name": "CatA", "icon_path": ""},
        ]
    }

    init_data = {
        "spheres": spheres,
        # Иерархия не задана, категория тоже
    }

    controller = StubDialogController(sections_by_sphere, cats_by_section)
    dlg = _make_dialog(init_data, controller, category_id=None)

    sphere_cb = dlg.ui.get_widget("sphere_cb")
    section_cb = dlg.ui.get_widget("section_cb")
    category_cb = dlg.ui.get_widget("category_cb")

    # По умолчанию выбрана первая сфера (id=5) и соответствующие первый раздел/категория
    assert sphere_cb.currentData() == 5
    assert section_cb.currentData() == 50
    assert category_cb.currentData() == 500


def test_populate_hierarchy_partial_hierarchy_fallbacks(qapp):
    spheres = [
        {"id": 1, "name": "S1"},
        {"id": 2, "name": "S2"},
    ]
    sections_by_sphere = {
        1: [
            {"id": 10, "name": "A", "icon_path": ""},
            {"id": 11, "name": "B", "icon_path": ""},
        ]
    }
    cats_by_section = {
        10: [
            {"id": 100, "name": "CA", "icon_path": ""},
            {"id": 101, "name": "CB", "icon_path": ""},
        ],
        11: [
            {"id": 110, "name": "CC", "icon_path": ""},
        ],
    }

    init_data = {
        "spheres": spheres,
        # Задана только сфера; section/category отсутствуют
        "category_hierarchy": {"sphere_id": 1},
    }

    controller = StubDialogController(sections_by_sphere, cats_by_section)
    # Чтобы задействовалась ветка применения иерархии, передаём любой category_id
    dlg = _make_dialog(init_data, controller, category_id=999)

    sphere_cb = dlg.ui.get_widget("sphere_cb")
    section_cb = dlg.ui.get_widget("section_cb")
    category_cb = dlg.ui.get_widget("category_cb")

    # Сфера должна быть 1 (из иерархии)
    assert sphere_cb.currentData() == 1
    # Раздел/категория — первые для выбранной сферы/раздела (фолбэк)
    assert section_cb.currentData() == 10
    assert category_cb.currentData() == 100


def test_populate_hierarchy_empty_spheres_safe(qapp):
    init_data = {
        "spheres": [],
    }
    controller = StubDialogController({}, {})
    dlg = _make_dialog(init_data, controller, category_id=None)

    sphere_cb = dlg.ui.get_widget("sphere_cb")
    section_cb = dlg.ui.get_widget("section_cb")
    category_cb = dlg.ui.get_widget("category_cb")

    # Комбобоксы пустые, инициализация не падает
    assert sphere_cb.count() == 0
    assert section_cb.count() == 0
    assert category_cb.count() == 0
