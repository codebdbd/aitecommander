import importlib

import pytest
from PyQt6.QtWidgets import QApplication, QLineEdit, QComboBox


def reload_module():
    from app.views.dialogs import base_dialog as bd

    importlib.reload(bd)
    return bd


@pytest.mark.qt_no_exception_capture
def test_context_menu_clipboard_error_logged(monkeypatch, caplog, qtbot):
    bd = reload_module()

    # Ensure theme resolution is deterministic
    monkeypatch.setattr(bd, "get_current_theme", lambda: "light")

    # Patch clipboard mimeData on the real QApplication instance to raise
    app = QApplication.instance()
    assert app is not None
    clip = app.clipboard()
    # Keep original and replace method
    original_mimeData = clip.mimeData

    def boom_mimeData():  # noqa: D401
        raise RuntimeError("clipboard error")

    monkeypatch.setattr(clip, "mimeData", boom_mimeData, raising=False)

    w = QLineEdit()
    qtbot.addWidget(w)

    caplog.set_level("ERROR")
    menu = bd.create_russian_context_menu(w)
    assert menu is not None

    assert any(
        "Failed to evaluate clipboard state for context menu" in rec.message
        for rec in caplog.records
    )


@pytest.mark.qt_no_exception_capture
def test_apply_combo_popup_styles_logs_on_dpi_error(monkeypatch, caplog, qtbot):
    bd = reload_module()

    class Dlg(bd.BaseDialog):
        def __init__(self):
            super().__init__()

    d = Dlg()
    qtbot.addWidget(d)
    # Ensure at least one combo exists to enter processing branch
    combo = QComboBox(d)
    qtbot.addWidget(combo)

    # Make dialog return a windowHandle that raises when screen() accessed
    class WH:
        def screen(self):
            raise AttributeError("no screen")

    monkeypatch.setattr(Dlg, "windowHandle", lambda self: WH())

    caplog.set_level("ERROR")
    d._apply_combo_popup_styles()

    assert any(
        "Failed to determine DPI scale for combo boxes" in rec.message
        for rec in caplog.records
    )


@pytest.mark.qt_no_exception_capture
def test_message_boxes_log_on_exec_error(monkeypatch, caplog, qtbot):
    bd = reload_module()

    class Dlg(bd.BaseDialog):
        pass

    d = Dlg()
    qtbot.addWidget(d)

    # Patch QMessageBox.exec to raise
    def boom(self):  # noqa: ANN001
        raise RuntimeError("boom")

    monkeypatch.setattr(bd.QMessageBox, "exec", boom, raising=False)

    caplog.set_level("ERROR")

    bd.BaseDialog.show_info(d, "text", silent=False)
    bd.BaseDialog.show_warning(d, "text", silent=False)
    bd.BaseDialog.show_error(d, "text", silent=False)

    assert any("Failed to show info message box" in rec.message for rec in caplog.records)
    assert any("Failed to show warning message box" in rec.message for rec in caplog.records)
    assert any("Failed to show error message box" in rec.message for rec in caplog.records)
