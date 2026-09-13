import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QFocusEvent
from PyQt6.QtWidgets import QApplication, QTextEdit

from app.config_data.runtime_config import runtime_app_config
from app.services.theme_stylesheet_service import ThemeStylesheetService
from app.views.widgets.input_frame import InputFrame


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_input_frame_structure(qapp):
    """Verify InputFrame wraps QTextEdit cleanly and sets properties."""
    te = QTextEdit()
    frame = InputFrame(te)

    assert frame.editor is te
    assert frame.property("input_frame") == "true"
    assert te.parent() is frame


def test_input_frame_focus_toggle(qapp):
    """Verify focus events toggle dynamic property 'focused'."""
    te = QTextEdit()
    frame = InputFrame(te)

    # Initial state
    assert frame.property("focused") in (None, "false")

    # Simulate FocusIn event directly
    focus_in = QFocusEvent(QEvent.Type.FocusIn)
    frame.eventFilter(te, focus_in)
    assert frame.property("focused") == "true"

    # Simulate FocusOut event directly
    focus_out = QFocusEvent(QEvent.Type.FocusOut)
    frame.eventFilter(te, focus_out)
    assert frame.property("focused") == "false"


def test_theme_stylesheet_service_adapts_input_frame():
    """Verify ThemeStylesheetService automatically adds input_frame rules."""
    svc = ThemeStylesheetService(runtime_app_config)
    qss = svc.load_stylesheet("light", "light.qss")

    assert qss is not None
    assert 'QFrame[input_frame="true"]' in qss
    assert 'QFrame[input_frame="true"][focused="true"]' in qss
