import importlib

import pytest
from PyQt6.QtCore import QPoint


def reload_tiles():
    from app.views import tiles as ct

    importlib.reload(ct)
    return ct


@pytest.mark.qt_no_exception_capture
def test_init_logs_on_config_errors(monkeypatch, caplog, qtbot):
    ct = reload_tiles()

    # Force config accessors to fail
    ui = ct.app_config.ui
    monkeypatch.setattr(ui, "get_tile_size", lambda: (_ for _ in ()).throw(ValueError("bad tile size")))
    monkeypatch.setattr(ui, "get_tile_icon_size", lambda: (_ for _ in ()).throw(AttributeError("no icon size")))
    monkeypatch.setattr(ui, "get_tile_spacing", lambda: (_ for _ in ()).throw(TypeError("bad spacing")))
    monkeypatch.setattr(ui, "get_tile_padding", lambda: (_ for _ in ()).throw(TypeError("bad padding")))

    caplog.set_level("WARNING")
    w = ct.CategoryTiles()
    qtbot.addWidget(w)

    msgs = "\n".join(rec.message for rec in caplog.records)
    assert "Tile size config read failed" in msgs
    assert "Icon size config read failed" in msgs
    assert "Tile spacing config read failed" in msgs
    assert "Tile padding config read failed" in msgs


@pytest.mark.qt_no_exception_capture
def test_update_font_size_logs_on_invalid_and_repaint_error(monkeypatch, caplog, qtbot):
    ct = reload_tiles()
    w = ct.CategoryTiles()
    qtbot.addWidget(w)

    # Make repaint/reset fail
    monkeypatch.setattr(w.view, "reset", lambda: (_ for _ in ()).throw(RuntimeError("fail")))

    caplog.set_level("WARNING")
    w.update_font_size("bad")  # invalid

    msgs = "\n".join(rec.message for rec in caplog.records)
    assert "update_font_size: invalid fs=" in msgs
    assert "update_font_size: repaint/reset failed" in msgs


@pytest.mark.qt_no_exception_capture
def test_context_menu_fallback_logs_debug_on_cursor_mapping_failure(monkeypatch, caplog, qtbot):
    ct = reload_tiles()

    w = ct.CategoryTiles()
    qtbot.addWidget(w)

    # Empty model to force invalid index at first
    w.set_categories([])

    # Force viewport mapFromGlobal to raise to hit debug branch
    vp = w.view.viewport()
    monkeypatch.setattr(vp, "mapFromGlobal", lambda *_: (_ for _ in ()).throw(RuntimeError("map fail")), raising=False)

    caplog.set_level("DEBUG")
    # Trigger context menu
    w._show_context_menu(QPoint(0, 0))

    assert any(
        "Context menu fallback mapping from cursor failed" in rec.message for rec in caplog.records
    )
