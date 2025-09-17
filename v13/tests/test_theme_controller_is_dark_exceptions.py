from __future__ import annotations

import pytest

from app.controllers.ui.theme_controller import ThemeController


class DummySettingsNoGet:
    pass


class DummySettingsRaise:
    def get_theme(self):
        raise RuntimeError("boom")


class DummySettingsValue:
    def __init__(self, value):
        self._value = value

    def get_theme(self):
        return self._value


def test_is_dark_handles_missing_get_theme_returns_false():
    ctrl = ThemeController(settings=DummySettingsNoGet())
    assert ctrl.is_dark() is False


essential_themes = [("light", False), ("dark", True), (None, False), ("", False)]


@pytest.mark.parametrize("value,expected", essential_themes)
def test_is_dark_basic_values(value, expected):
    ctrl = ThemeController(settings=DummySettingsValue(value))
    assert ctrl.is_dark() is expected


def test_is_dark_unexpected_exception_is_propagated():
    ctrl = ThemeController(settings=DummySettingsRaise())
    with pytest.raises(RuntimeError):
        ctrl.is_dark()
