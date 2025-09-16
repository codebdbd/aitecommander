import pytest

from PyQt6.QtWidgets import QApplication, QLineEdit
from PyQt6.QtGui import QAction

from app.views.main_components.topbar_layout.topbar_narrow_mode import (
    _save_search_state,
    restore_search_state,
)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_restore_search_state_recovers_clear_button_and_actions(qt_app):
    search = QLineEdit()

    # Prepare actions with different initial visibility
    act_left = QAction("left", search)
    act_right = QAction("right", search)
    search.addAction(act_left)
    search.addAction(act_right)

    act_left.setVisible(True)
    act_right.setVisible(False)

    # Some environments may not support clear button; guard accordingly
    had_clear_attr = hasattr(search, "setClearButtonEnabled") and hasattr(search, "isClearButtonEnabled")
    if had_clear_attr:
        search.setClearButtonEnabled(True)
        assert search.isClearButtonEnabled() is True

    # Save current state and then simulate narrow mode disabling
    _save_search_state(search)

    # Simulate narrow mode effects
    if had_clear_attr:
        search.setClearButtonEnabled(False)
    for act in search.actions():
        act.setVisible(False)

    # Restore
    restore_search_state(search)

    # Verify restored state
    if had_clear_attr:
        assert search.isClearButtonEnabled() is True
    # Actions visibility must be restored to their original states
    # Original: left=True, right=False
    actions = search.actions()
    assert actions[0].isVisible() is True
    assert actions[1].isVisible() is False
