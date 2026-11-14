from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMainWindow, QMenu

from app.controllers.system.keyboard_manager import KeyboardManager
from app.core.hotkey_manager import HotkeyManager
from app.utils.ui.menu_builders.menu_actions import ActionBuilder


def test_data_menu_shortcut_works_while_menu_is_open(qapp, monkeypatch) -> None:
    monkeypatch.setattr(
        HotkeyManager,
        "_registry",
        {"global.import_browser": "Ctrl+Alt+C"},
    )
    window = QMainWindow()
    calls: list[str] = []
    window.handle_import_browser_bookmarks = lambda: calls.append("import")
    KeyboardManager(window)

    menu = QMenu(window)
    action = ActionBuilder(window).create(
        "Import Bookmarks",
        lambda: None,
        "global.import_browser",
    )
    menu.addAction(action)
    window.menuBar().addMenu(menu)

    window.show()
    menu.popup(window.mapToGlobal(window.rect().center()))
    qapp.processEvents()
    qapp.setActiveWindow(window)
    QTest.keyClick(
        menu,
        Qt.Key.Key_C,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )
    qapp.processEvents()

    assert calls == ["import"]

    menu.close()
    window.close()
