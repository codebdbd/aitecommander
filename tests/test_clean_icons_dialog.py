from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QMainWindow

from app.services.icon_reference_service import IconReferenceService
from app.utils.ui.menu_builders.main_menu_builder import MainMenuBuilder
from app.utils.ui.menu_builders.menu_actions import MenuTexts
from app.views.windows.dialogs.clean_icons_dialog import CleanIconsDialog


def _init_test_database(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE sphere (id INTEGER PRIMARY KEY, name TEXT NOT NULL, icon_path TEXT);
        CREATE TABLE section (id INTEGER PRIMARY KEY, sphere_id INTEGER, name TEXT NOT NULL, icon_path TEXT);
        CREATE TABLE category (id INTEGER PRIMARY KEY, section_id INTEGER, name TEXT NOT NULL, icon_path TEXT);
        CREATE TABLE link (id INTEGER PRIMARY KEY, category_id INTEGER, name TEXT NOT NULL, icon_path TEXT);
        """
    )
    conn.commit()


def test_clean_icons_dialog_no_orphans(qapp, tmp_path: Path) -> None:
    icons_dir = tmp_path / "icons"
    icons_dir.mkdir()

    conn = sqlite3.connect(":memory:")
    _init_test_database(conn)
    db_mock = MagicMock()
    db_mock.connection = conn

    service = IconReferenceService(db_mock)
    service._get_user_icons_dir = MagicMock(return_value=icons_dir)

    dialog = CleanIconsDialog(service)
    assert dialog.clean_button is not None
    assert dialog.clean_button.isHidden() or not dialog.clean_button.isVisible()
    assert dialog.close_button is not None
    assert "Close" in dialog.close_button.text() or "Закрыть" in dialog.close_button.text()
    dialog.close()


def test_clean_icons_dialog_with_orphans_and_cleanup(qapp, tmp_path: Path) -> None:
    icons_dir = tmp_path / "icons"
    icons_dir.mkdir()
    orphan_file = icons_dir / "orphan.png"
    orphan_file.write_bytes(b"data")

    conn = sqlite3.connect(":memory:")
    _init_test_database(conn)
    db_mock = MagicMock()
    db_mock.connection = conn

    service = IconReferenceService(db_mock)
    service._get_user_icons_dir = MagicMock(return_value=icons_dir)

    dialog = CleanIconsDialog(service)
    assert dialog.clean_button is not None
    assert not dialog.clean_button.isHidden()

    # Trigger clean
    dialog._on_clean_clicked()

    assert not orphan_file.exists()
    assert dialog.clean_button.isHidden()
    assert dialog._is_cleaned is True
    dialog.close()


def test_clean_icons_menu_action_present(qapp) -> None:
    window = QMainWindow()
    window.settings = MagicMock()
    window.settings.get_theme.return_value = "dark"
    window.create_undo_redo_actions = MagicMock(return_value=(None, None))
    window.show_file_search_dialog = MagicMock()
    window.show_settings_dialog = MagicMock()
    window.show_about_dialog = MagicMock()
    window.handle_import_browser_bookmarks = MagicMock()
    window.handle_import_text_links = MagicMock()
    system_dialogs_mock = MagicMock()
    window.system_dialogs = system_dialogs_mock

    builder = MainMenuBuilder(window)
    menubar = builder.build()

    # Find Data menu
    data_menu = None
    for action in menubar.actions():
        menu = action.menu()
        if menu and ("Data" in action.text() or "Данные" in action.text()):
            data_menu = menu
            break

    assert data_menu is not None

    clean_action = None
    for action in data_menu.actions():
        if action.text() == MenuTexts.CLEAN_ICONS or "Clean Icons" in action.text() or "Очистить иконки" in action.text():
            clean_action = action
            break

    assert clean_action is not None
    assert "..." not in clean_action.text()
    assert "…" not in clean_action.text()

    # Trigger action
    clean_action.trigger()
    system_dialogs_mock.handle_clean_icons.assert_called_once()

    window.close()
