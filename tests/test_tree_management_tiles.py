import logging
from types import SimpleNamespace

import pytest

from app.controllers.ui.structure.tree_management import TreeManagement


class DummyTilesController:
    def __init__(self):
        self.calls = []
        self.raise_exc = None

    def refresh(self, section_id: int):
        self.calls.append(section_id)
        if self.raise_exc is not None:
            raise self.raise_exc


class _MinimalModel:
    def insert_sections(self, *_):
        pass
    def insert_categories(self, *_):
        pass
    def update_item(self, *_):
        pass

class _TreeWithModel:
    def model(self):
        return _MinimalModel()

@pytest.fixture
def controller_stub():
    # Минимальный контроллер с деревом, у которого есть валидная модель
    return SimpleNamespace(tree=_TreeWithModel(), icon_handler=None)


def test_refresh_section_tiles_calls_controller(controller_stub):
    tiles = DummyTilesController()
    tm = TreeManagement(controller_stub, tiles)

    tm.refresh_section_tiles("5")  # строка должна быть приведена к int

    assert tiles.calls == [5]


def test_refresh_section_tiles_expected_errors_are_logged_and_swallowed(controller_stub, caplog):
    tiles = DummyTilesController()
    tiles.raise_exc = ValueError("bad section id")
    tm = TreeManagement(controller_stub, tiles)

    with caplog.at_level(logging.ERROR):
        tm.refresh_section_tiles(10)

    # Ошибка не должна пробрасываться, но должна логироваться
    assert any(
        "controller refresh failed (expected)" in rec.getMessage()
        for rec in caplog.records
    )


def test_refresh_section_tiles_unexpected_errors_bubble_up(controller_stub):
    tiles = DummyTilesController()
    tiles.raise_exc = KeyError("boom")  # не входит в список ожидаемых
    tm = TreeManagement(controller_stub, tiles)

    with pytest.raises(KeyError):
        tm.refresh_section_tiles(1)
