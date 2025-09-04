import pytest
from types import SimpleNamespace

from app.controllers.system.window_controllers_setup import setup_controllers, SetupError
from app.controllers.ui.category_tiles_controller import CategoryTilesController


class DummyDB:
    pass


def test_setup_raises_on_incompatible_tiles_widget(monkeypatch):
    # Подменяем attach_tiles_widget, чтобы она проверяла совместимость и бросала TypeError
    def fake_attach(self, tiles_widget):  # noqa: ARG001
        raise TypeError("tiles widget is incompatible")

    monkeypatch.setattr(CategoryTilesController, "attach_tiles_widget", fake_attach, raising=True)

    window = SimpleNamespace(tiles=object())

    with pytest.raises(SetupError):
        setup_controllers(window, {}, DummyDB())


def test_setup_raises_when_tiles_widget_missing_or_falsy():
    # Окно без tiles должно приводить к SetupError на этапе setup_controllers
    window_no_attr = SimpleNamespace()
    with pytest.raises(SetupError):
        setup_controllers(window_no_attr, {}, DummyDB())

    # Окно с tiles=None также должно падать
    window_falsy = SimpleNamespace(tiles=None)
    with pytest.raises(SetupError):
        setup_controllers(window_falsy, {}, DummyDB())


def test_setup_raises_on_unexpected_error_during_tiles_attachment(monkeypatch):
    # Подменяем attach_tiles_widget, чтобы она бросала неожиданную ошибку
    def fake_attach(self, tiles_widget):  # noqa: ARG001
        raise RuntimeError("boom")

    monkeypatch.setattr(CategoryTilesController, "attach_tiles_widget", fake_attach, raising=True)

    window = SimpleNamespace(tiles=object())

    with pytest.raises(SetupError):
        setup_controllers(window, {}, DummyDB())
