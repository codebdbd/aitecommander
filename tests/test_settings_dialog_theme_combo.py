from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QWidget

from app.views.windows.dialogs.entity_dialogs import SettingsDialog


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _DummySettings:
    def __init__(self, theme: str) -> None:
        self._theme = theme

    def get_theme(self) -> str:
        return self._theme

    def set_theme(self, theme: str) -> None:
        self._theme = theme

    def get_font_size(self) -> int:
        return 12

    def get_max_backups(self) -> int:
        return 10


class _DummyThemeController:
    def refresh_themes(self) -> None:
        return

    def clear_cache(self) -> None:
        return

    def apply(self, _theme_id: str) -> bool:
        return True


class TestSettingsDialogThemeCombo(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_initial_selection_uses_saved_theme_not_first_item(self) -> None:
        settings = _DummySettings("light")
        theme_ctrl = _DummyThemeController()
        parent = QWidget()

        with patch.object(
            SettingsDialog,
            "_get_available_themes",
            return_value=[
                ("dark", "Dark theme"),
                ("light", "Light theme"),
                ("dreamy_room", "Dreamy room"),
            ],
        ):
            dialog = SettingsDialog(settings, theme_ctrl, parent=parent)

        try:
            self.assertEqual("light", dialog.theme_combo.currentData())
            self.assertEqual("Light theme", dialog.theme_combo.currentText())
        finally:
            dialog.close()
            parent.close()

    def test_refresh_preserves_current_selection(self) -> None:
        settings = _DummySettings("light")
        theme_ctrl = _DummyThemeController()
        parent = QWidget()

        with patch.object(
            SettingsDialog,
            "_get_available_themes",
            return_value=[
                ("dark", "Dark theme"),
                ("light", "Light theme"),
                ("dreamy_room", "Dreamy room"),
            ],
        ):
            dialog = SettingsDialog(settings, theme_ctrl, parent=parent)

        try:
            dreamy_index = dialog.theme_combo.findData("dreamy_room")
            dialog.theme_combo.setCurrentIndex(dreamy_index)

            with patch.object(
                SettingsDialog,
                "_get_available_themes",
                return_value=[
                    ("dark", "Темная тема"),
                    ("light", "Светлая тема"),
                    ("dreamy_room", "Комната мечты"),
                ],
            ):
                dialog._refresh_theme_list(keep_selection=True)

            self.assertEqual("dreamy_room", dialog.theme_combo.currentData())
            self.assertEqual("Комната мечты", dialog.theme_combo.currentText())
        finally:
            dialog.close()
            parent.close()


if __name__ == "__main__":
    unittest.main()
