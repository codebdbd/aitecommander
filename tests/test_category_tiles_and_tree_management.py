import logging
import types

import pytest

from app.controllers.ui.category_tiles_controller import CategoryTilesController
from app.controllers.ui.structure.tree_management import TreeManagement


class UIStateMock:
    def __init__(self):
        self.last_categories = None
        self.calls = 0

    def switch_to_category_tiles(self, categories):
        self.last_categories = categories
        self.calls += 1


class StructureBusinessMock:
    def __init__(self, by_section):
        self.by_section = by_section
        self.queries = []

    def get_categories(self, section_id: int):
        self.queries.append(section_id)
        return self.by_section.get(section_id, [])


class ControllerStub:
    def __init__(self):
        # TreeManagement ожидает tree и icon_handler, но в тестах они не используются нашими вызовами
        self.tree = types.SimpleNamespace()
        self.icon_handler = object()


def test_category_tiles_controller_refresh_valid_section(monkeypatch):
    ui = UIStateMock()
    business = StructureBusinessMock({5: [{"id": 1}, {"id": 2}]})
    ctrl = CategoryTilesController(ui_state=ui, structure_business=business)

    ctrl.refresh(5)

    assert business.queries == [5]
    assert ui.calls == 1
    assert ui.last_categories == [{"id": 1}, {"id": 2}]


def test_category_tiles_controller_refresh_invalid_section_logs(caplog):
    ui = UIStateMock()
    business = StructureBusinessMock({})
    ctrl = CategoryTilesController(ui_state=ui, structure_business=business)
    caplog.set_level(logging.WARNING)

    ctrl.refresh(0)

    # никаких вызовов UI/BL
    assert business.queries == []
    assert ui.calls == 0


def test_tree_management_calls_tiles_controller_refresh(monkeypatch):
    # Проверяем интеграцию: TreeManagement.refresh_section_tiles -> CategoryTilesController.refresh
    class TilesSpy:
        def __init__(self):
            self.calls = []

        def refresh(self, section_id: int):
            self.calls.append(section_id)

    main_ctrl = type("Main", (), {})()
    main_ctrl.tree = object()
    main_ctrl.icon_handler = object()

    tiles_spy = TilesSpy()
    tm = TreeManagement(main_ctrl, category_tiles_controller=tiles_spy)

    tm.refresh_section_tiles(42)

    assert tiles_spy.calls == [42]
