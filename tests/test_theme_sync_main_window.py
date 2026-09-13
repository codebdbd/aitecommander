from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication, QWidget

from app.views.widgets.theme_selector import ThemeSelector
from app.views.windows.dialogs.entity_dialogs import SettingsDialog
from app.views.windows.main_window import MainWindow
from app.core.settings_manager import SettingsManager

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _MockSettings:
    def __init__(self, theme: str = "light") -> None:
        self._theme = theme

    def get_theme(self) -> str:
        return self._theme

    def set_theme(self, theme: str) -> None:
        self._theme = theme

    def get_font_size(self) -> int:
        return 12

    def get_max_backups(self) -> int:
        return 10


class _MockThemeController:
    def __init__(self, settings: _MockSettings, main_window=None) -> None:
        self.settings = settings
        self.main_window = main_window
        self.themes = [
            ("light", "Light"),
            ("dark", "Dark"),
            ("matrix", "Matrix"),
        ]

    def available(self) -> list[tuple[str, str]]:
        return list(self.themes)

    def refresh_themes(self) -> None:
        if self.main_window and hasattr(self.main_window, "theme_selector"):
            theme_sel = getattr(self.main_window, "theme_selector", None)
            if theme_sel and hasattr(theme_sel, "refresh_themes"):
                theme_sel.refresh_themes()

    def clear_cache(self) -> None:
        pass

    def set_main_window(self, main_window) -> None:
        self.main_window = main_window

    def apply(self, theme_id: str) -> bool:
        self.settings.set_theme(theme_id)
        SettingsManager.set("theme.name", theme_id)
        if self.main_window and hasattr(self.main_window, "update_theme"):
            self.main_window.update_theme()
        return True


class TestThemeSyncMainWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_theme_selector_update_theme_selection(self) -> None:
        settings = _MockSettings("light")
        theme_ctrl = _MockThemeController(settings)
        parent = QWidget()
        selector = ThemeSelector(theme_ctrl, parent=parent)

        try:
            self.assertEqual("light", selector.currentData())

            # update_theme_selection changes data without firing apply
            theme_ctrl.apply = MagicMock()
            selector.update_theme_selection("dark")
            self.assertEqual("dark", selector.currentData())
            theme_ctrl.apply.assert_not_called()

            # update_theme_selection using settings
            settings.set_theme("matrix")
            selector.update_theme_selection()
            self.assertEqual("matrix", selector.currentData())
            theme_ctrl.apply.assert_not_called()
        finally:
            selector.close()
            parent.close()

    def test_settings_dialog_accept_updates_main_window_theme_selector(self) -> None:
        """When changing theme in SettingsDialog and saving, MainWindow.theme_selector is updated."""
        settings = _MockSettings("light")
        theme_ctrl = _MockThemeController(settings)
        mw = MainWindow(settings, theme_ctrl)

        selector = ThemeSelector(theme_ctrl, parent=mw)
        mw.theme_selector = selector

        try:
            self.assertEqual("light", mw.theme_selector.currentData())

            # Open SettingsDialog
            with patch.object(
                SettingsDialog,
                "_get_available_themes",
                return_value=[("light", "Light"), ("dark", "Dark"), ("matrix", "Matrix")],
            ):
                dialog = SettingsDialog(settings, theme_ctrl, parent=mw)

            self.assertEqual("light", dialog.theme_combo.currentData())

            # Select 'dark' in SettingsDialog
            dark_idx = dialog.theme_combo.findData("dark")
            dialog.theme_combo.setCurrentIndex(dark_idx)

            # Accept settings
            dialog._on_accept()

            # MainWindow theme_selector must now reflect 'dark'
            self.assertEqual("dark", mw.theme_selector.currentData())
            self.assertEqual("dark", settings.get_theme())
        finally:
            selector.close()
            mw.close()

    def test_bidirectional_theme_sync(self) -> None:
        """Changing theme in ThemeSelector updates SettingsDialog, and vice versa."""
        settings = _MockSettings("light")
        theme_ctrl = _MockThemeController(settings)
        mw = MainWindow(settings, theme_ctrl)

        selector = ThemeSelector(theme_ctrl, parent=mw)
        mw.theme_selector = selector

        with patch.object(
            SettingsDialog,
            "_get_available_themes",
            return_value=[("light", "Light"), ("dark", "Dark"), ("matrix", "Matrix")],
        ):
            dialog = SettingsDialog(settings, theme_ctrl, parent=mw)

        # Mock system_dialogs on MainWindow
        system_dialogs = MagicMock()
        system_dialogs._settings_dialog = dialog
        mw.system_dialogs = system_dialogs

        try:
            self.assertEqual("light", mw.theme_selector.currentData())
            self.assertEqual("light", dialog.theme_combo.currentData())

            # 1. Change from MainWindow.theme_selector to 'dark'
            selector.setCurrentIndex(selector.findData("dark"))
            self.assertEqual("dark", mw.theme_selector.currentData())
            self.assertEqual("dark", dialog.theme_combo.currentData())
            self.assertEqual("dark", settings.get_theme())

            # 2. Change from SettingsDialog to 'matrix' and accept
            dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("matrix"))
            dialog._on_accept()
            self.assertEqual("matrix", mw.theme_selector.currentData())
            self.assertEqual("matrix", dialog.theme_combo.currentData())
            self.assertEqual("matrix", settings.get_theme())
        finally:
            dialog.close()
            selector.close()
            mw.close()


if __name__ == "__main__":
    unittest.main()
