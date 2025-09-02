import logging
import pytest
from types import SimpleNamespace

from app.controllers.ui.structure.tree_management import TreeManagement


class TilesControllerMock:
    def __init__(self, err: Exception):
        self._err = err
        self.calls = []

    def refresh(self, section_id: int):
        self.calls.append(("refresh", int(section_id)))
        raise self._err


class ModelMock:
    def rowCount(self, *_):
        return 0

    # методы, требуемые TreeManagement при инициализации
    def insert_sections(self, *_):
        pass

    def insert_categories(self, *_):
        pass

    def update_item(self, *_):
        pass


class TreeMock:
    def __init__(self):
        self._model = ModelMock()

    def model(self):
        return self._model

    def currentIndex(self):
        return None


class ControllerMock:
    def __init__(self):
        self.tree = TreeMock()
        self.icon_handler = SimpleNamespace(reload_icons=lambda: None)
        self.selection_handler = SimpleNamespace(
            _restore_selection_after_load=lambda *_: None,
            _set_focus_on_new_item_by_id=lambda *_: None,
        )
        self.main = SimpleNamespace(_first_structure_load=False)


def test_refresh_section_tiles_expected_error_logged_and_swallowed(caplog):
    caplog.set_level(logging.ERROR)
    ctrl = ControllerMock()
    # Ожидаемые ошибки (ValueError/RuntimeError) должны логироваться и НЕ выбрасываться
    tiles_ctrl = TilesControllerMock(ValueError("boom tiles"))

    tm = TreeManagement(controller=ctrl, category_tiles_controller=tiles_ctrl)

    tm.refresh_section_tiles(123)  # не должно выбросить

    # Убедимся, что был вызов refresh
    assert tiles_ctrl.calls == [("refresh", 123)]
    assert any("controller refresh failed (expected)" in rec.getMessage() for rec in caplog.records)
