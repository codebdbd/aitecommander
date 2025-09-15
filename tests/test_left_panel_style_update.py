import contextlib

import pytest

from app.views.main_window import MainWindow


class _StyleStub:
    def __init__(self):
        self.polish_calls = 0
        self.unpolish_calls = 0

    def polish(self, widget):
        self.polish_calls += 1

    def unpolish(self, widget):
        self.unpolish_calls += 1


class _LeftPanelStub:
    def __init__(self):
        self._props = {}
        self._style = _StyleStub()
        self.updated = 0

    def property(self, name: str):
        return self._props.get(name)

    def setProperty(self, name: str, value):
        self._props[name] = value

    def style(self):
        return self._style

    def update(self):
        self.updated += 1


class _SettingsStub: ...
class _ThemeStub: ...


@contextlib.contextmanager
def _no_suspend(_):
    # no-op context manager to bypass UI dependency
    yield


@pytest.mark.usefixtures("qapp")
class TestLeftPanelStyleUpdate:
    def test_updates_style_without_unpolish_and_triggers_update(self, monkeypatch):
        # Arrange
        mw = MainWindow(settings=_SettingsStub(), theme_ctrl=_ThemeStub())
        lp = _LeftPanelStub()
        lp.setProperty("sphere", "1")
        mw.left_panel = lp

        # Suspend updates is used in method; replace by no-op
        monkeypatch.setattr("app.views.main_window.suspend_updates", _no_suspend, raising=True)

        # Act
        mw._update_left_panel_style(2)

        # Assert
        assert lp.property("sphere") == "2"
        assert lp.style().polish_calls == 1
        # Ensure unpolish was NOT called
        assert lp.style().unpolish_calls == 0
        # Ensure update() was called to repaint
        assert lp.updated == 1

    def test_no_op_when_sphere_not_changed(self, monkeypatch):
        # Arrange
        mw = MainWindow(settings=_SettingsStub(), theme_ctrl=_ThemeStub())
        lp = _LeftPanelStub()
        lp.setProperty("sphere", "5")
        mw.left_panel = lp

        monkeypatch.setattr("app.views.main_window.suspend_updates", _no_suspend, raising=True)

        # Act
        mw._update_left_panel_style(5)

        # Assert: no changes
        assert lp.property("sphere") == "5"
        assert lp.style().polish_calls == 0
        assert lp.style().unpolish_calls == 0
        assert lp.updated == 0
