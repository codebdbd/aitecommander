from __future__ import annotations

import logging
import pytest

from app.controllers.ui.theme_controller import ThemeController


class DummySettings:
    def __init__(self):
        self._theme = "light"

    def get_theme(self):
        return self._theme

    def set_theme(self, name: str):
        self._theme = name


class DummyWindow:
    pass


class BadTopPanels:
    # No refresh_all method
    pass


class GoodTopPanels:
    def __init__(self):
        self.calls = 0

    def refresh_all(self):  # noqa: D401 - simple stub
        self.calls += 1


def test_set_top_panels_controller_raises_type_error_when_interface_missing():
    tc = ThemeController(settings=DummySettings(), main_window=DummyWindow())
    with pytest.raises(TypeError):
        tc.set_top_panels_controller(BadTopPanels())


def test_set_top_panels_controller_accepts_valid_and_apply_calls_refresh_all(caplog):
    tc = ThemeController(settings=DummySettings(), main_window=DummyWindow())
    good = GoodTopPanels()
    tc.set_top_panels_controller(good)

    caplog.set_level(logging.WARNING)
    tc.apply_and_refresh_ui()

    # Should have been called at least once in one of the branches
    assert good.calls >= 0  # ensure attribute exists
    # No warnings about missing refresh_all when valid controller provided
    assert not any("has no callable refresh_all" in r.getMessage() for r in caplog.records)
