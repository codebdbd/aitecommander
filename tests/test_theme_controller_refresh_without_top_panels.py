from __future__ import annotations

import logging
import types

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
    """Minimal main window stub; may have no menu_controller/structure."""
    pass


def test_apply_and_refresh_ui_does_not_warn_without_top_panels_controller(caplog):
    # No top_panels_controller injected
    tc = ThemeController(settings=DummySettings(), main_window=DummyWindow())

    # Capture warnings
    with caplog.at_level(logging.WARNING):
        tc.apply_and_refresh_ui()

    # Ensure there is no warning about top panels refresh when controller is missing
    msgs = [r.getMessage() for r in caplog.records]
    assert not any("верхних панелей" in m for m in msgs), msgs

    # Now inject a controller that raises to ensure real errors are still logged
    class BadTopPanels:
        def refresh_all(self):
            raise RuntimeError("boom")

    tc.set_top_panels_controller(BadTopPanels())

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        tc.apply_and_refresh_ui()

    assert any("верхних панелей" in r.getMessage() for r in caplog.records)
