"""Tests for the Global Command Palette (Alt + ~ / Alt + `)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QDialog, QMainWindow

from app.controllers.ui.command_palette_controller import CommandPaletteController
from app.services.command_palette_service import (
    CommandPaletteService,
    parse_palette_query,
)
from app.services.global_hotkey_service import (
    MOD_ALT,
    MOD_NOREPEAT,
    MOD_SHIFT,
    MOD_WIN,
    VK_OEM_3,
    GlobalHotkeyService,
    parse_win32_hotkey,
)
from app.services.theme_registry import theme_registry
from app.services.theme_stylesheet_service import ThemeStylesheetService
from app.views.windows.dialogs.command_palette_dialog import CommandPaletteDialog


def test_parse_win32_hotkey_tilde_and_combinations() -> None:
    assert parse_win32_hotkey("Alt+`") == (MOD_ALT | MOD_NOREPEAT, VK_OEM_3)
    assert parse_win32_hotkey("Alt+~") == (MOD_ALT | MOD_NOREPEAT, VK_OEM_3)
    assert parse_win32_hotkey("Alt+Ё") == (MOD_ALT | MOD_NOREPEAT, VK_OEM_3)
    assert parse_win32_hotkey("Win+Shift+A") == (
        MOD_WIN | MOD_SHIFT | MOD_NOREPEAT,
        ord("A"),
    )
    assert parse_win32_hotkey("") is None
    assert parse_win32_hotkey("Alt+") is None
    assert parse_win32_hotkey("`") is None


def test_global_hotkey_service_register_and_cleanup(monkeypatch) -> None:
    fake_user32 = MagicMock()
    fake_user32.RegisterHotKey.return_value = 1
    fake_user32.UnregisterHotKey.return_value = 1

    svc = GlobalHotkeyService()
    monkeypatch.setattr(svc, "_get_user32", lambda: fake_user32)

    assert svc.register_hotkey("Alt+`", force_native=True) is True
    assert svc.is_registered is True
    fake_user32.RegisterHotKey.assert_called_once_with(
        None,
        svc.HOTKEY_ID,
        MOD_ALT | MOD_NOREPEAT,
        VK_OEM_3,
    )

    svc.cleanup()
    assert svc.is_registered is False
    fake_user32.UnregisterHotKey.assert_called_once_with(None, svc.HOTKEY_ID)


def test_parse_palette_query_prefixes() -> None:
    q1 = parse_palette_query("> deploy prod")
    assert q1.type_filter == frozenset({"script"})
    assert q1.sphere_filter == ""
    assert q1.text == "deploy prod"

    q2 = parse_palette_query("/ hosts")
    assert q2.type_filter == frozenset({"file", "folder", "program"})
    assert q2.text == "hosts"

    q3 = parse_palette_query("@Личное > бэкап")
    assert q3.sphere_filter == "личное"
    assert q3.type_filter == frozenset({"script"})
    assert q3.text == "бэкап"


def test_command_palette_service_cyrillic_fuzzy_and_ranking() -> None:
    sample_items: list[dict[str, Any]] = [
        {
            "id": 1,
            "name": "Яндекс Музыка",
            "url": "https://music.yandex.ru",
            "type": "web",
            "category_id": 10,
            "category_name": "Медиа",
            "section_id": 5,
            "section_name": "Развлечения",
            "sphere_id": 2,
            "sphere_name": "Личное",
            "is_favorite": 1,
            "last_used": "2026-11-06T12:00:00",
            "position": 0,
        },
        {
            "id": 2,
            "name": "Deploy Production Script",
            "url": "C:/scripts/deploy_prod.ps1",
            "type": "script",
            "category_id": 11,
            "category_name": "DevOps",
            "section_id": 6,
            "section_name": "Инфраструктура",
            "sphere_id": 1,
            "sphere_name": "Work",
            "is_favorite": 0,
            "last_used": "2026-11-07T09:00:00",
            "position": 1,
        },
        {
            "id": 3,
            "name": "Hosts File",
            "url": "C:/Windows/System32/drivers/etc/hosts",
            "type": "file",
            "category_id": 11,
            "category_name": "DevOps",
            "section_id": 6,
            "section_name": "Инфраструктура",
            "sphere_id": 1,
            "sphere_name": "Work",
            "is_favorite": 0,
            "last_used": None,
            "position": 2,
        },
    ]

    svc = CommandPaletteService()
    svc.set_snapshot_for_testing(sample_items)

    # Empty query: most recently used comes first
    initial = svc.search("", limit=10)
    assert [item["id"] for item in initial] == [2, 1, 3]

    # Case-insensitive Cyrillic search (lowercase query matches uppercase Cyrillic)
    cyr = svc.search("яндекс", limit=10)
    assert len(cyr) == 1
    assert cyr[0]["id"] == 1

    # Sphere filter in Cyrillic + query
    sphere_res = svc.search("@личное муз", limit=10)
    assert len(sphere_res) == 1
    assert sphere_res[0]["id"] == 1

    # Script prefix '>'
    scripts = svc.search("> dpl", limit=10)
    assert len(scripts) == 1
    assert scripts[0]["id"] == 2

    # Local file prefix '/'
    files = svc.search("/ hosts", limit=10)
    assert len(files) == 1
    assert files[0]["id"] == 3


def test_command_palette_theme_tokens_and_dialog_interaction(qapp: QApplication) -> None:
    mw = QMainWindow()
    mw.links_actions = MagicMock()
    mw.structure = MagicMock()
    mw.structure_business = MagicMock()
    mw.structure_business.current_sphere_id = 1
    mw.ui_state = MagicMock()

    ctrl = CommandPaletteController(mw, db=None, register_native_hotkey=False)
    ctrl._service.set_snapshot_for_testing(
        [
            {
                "id": 101,
                "name": "GitHub Repo",
                "url": "https://github.com/example/repo",
                "type": "web",
                "category_id": 20,
                "category_name": "Repos",
                "section_id": 10,
                "section_name": "Code",
                "sphere_id": 1,
                "sphere_name": "Work",
                "is_favorite": 1,
                "last_used": "2026-11-07T08:00:00",
                "position": 0,
            },
            {
                "id": 102,
                "name": "Clean Temp Folder",
                "url": "C:/scripts/clean_temp.ps1",
                "type": "script",
                "category_id": 30,
                "category_name": "Maintenance",
                "section_id": 12,
                "section_name": "Scripts",
                "sphere_id": 2,
                "sphere_name": "Personal",
                "is_favorite": 0,
                "last_used": "2026-11-06T08:00:00",
                "position": 1,
            },
        ]
    )
    # Prevent refresh_snapshot from wiping in-memory test data when db is None
    ctrl._service.refresh_snapshot = lambda: len(ctrl._service._snapshot)  # type: ignore[method-assign]

    opened = ctrl.show_palette()
    assert opened is True
    dlg = ctrl._dialog
    assert isinstance(dlg, CommandPaletteDialog)
    assert dlg.testAttribute(Qt.WidgetAttribute.WA_QuitOnClose) is False
    assert dlg.model.rowCount() == 2

    # Navigate Down to second item and press Enter to launch
    down_event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(dlg.search_input, down_event)
    assert dlg.list_view.currentIndex().row() == 1

    enter_event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(dlg.search_input, enter_event)
    mw.links_actions.open_link.assert_called_once()
    assert mw.links_actions.open_link.call_args[0][0]["id"] == 102
    assert not dlg.isVisible()

    # Re-open and press Ctrl+Enter on item in sphere 2 -> switches sphere & schedules restore
    ctrl.show_palette()
    QApplication.sendEvent(dlg.search_input, down_event)
    ctrl_enter = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_Return,
        Qt.KeyboardModifier.ControlModifier,
    )
    QApplication.sendEvent(dlg.search_input, ctrl_enter)
    mw.structure.switch_sphere.assert_called_once_with(2, item_to_select=("category", 30))
    mw.ui_state.load_category.assert_called_with(30, source="CommandPalette")
    mw.links_actions.schedule_restore_selection.assert_called_once_with(102)

    # Verify theme QSS generation includes Command Palette selectors across themes
    qss_svc = ThemeStylesheetService({"settings": {}})
    for theme_id in ("dark", "light", "cyberpunk_neon", "sakura_anime"):
        tokens = theme_registry.get_theme_tokens(theme_id)
        qss_block = qss_svc._build_tokens_qss(tokens)
        assert "QDialog#CommandPaletteDialog" in qss_block
        assert "QFrame#commandPaletteContainer" in qss_block
        assert "QLineEdit#commandPaletteInput" in qss_block
        assert "QListView#commandPaletteResults" in qss_block

    ctrl.refresh_theme()
    ctrl.cleanup()
    mw.close()


def test_command_palette_blocked_when_modal_dialog_active(
    qapp: QApplication, monkeypatch
) -> None:
    mw = QMainWindow()
    ctrl = CommandPaletteController(mw, db=None, register_native_hotkey=False)

    modal_dlg = QDialog(mw)
    modal_dlg.setModal(True)
    monkeypatch.setattr(QApplication, "activeModalWidget", staticmethod(lambda: modal_dlg))

    assert ctrl.show_palette() is False
    assert ctrl._dialog is None

    ctrl.cleanup()
    modal_dlg.close()
    mw.close()
