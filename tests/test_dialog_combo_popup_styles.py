from __future__ import annotations

import unittest

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QListView, QWidget

from app.views.windows.dialogs.entity_dialogs import SettingsDialog
from app.views.windows.dialogs.base_dialog import ComboRowHeightDelegate


class _DummySettings:
    def get_theme(self) -> str:
        return "dark"

    def set_theme(self, _theme: str) -> None:
        return

    def get_font_size(self) -> int:
        return 12

    def set_font_size(self, _size: int) -> None:
        return

    def get_max_backups(self) -> int:
        return 10

    def set_max_backups(self, _count: int) -> None:
        return


class _DummyThemeController:
    def refresh_themes(self) -> None:
        return

    def clear_cache(self) -> None:
        return

    def apply(self, _theme_id: str) -> bool:
        return True


class TestDialogComboPopupStyles(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_settings_dialog_combos_use_uniform_qt_popup_view(self) -> None:
        parent = QWidget()
        dialog = SettingsDialog(_DummySettings(), _DummyThemeController(), parent=parent)

        try:
            dialog.show()
            self._app.processEvents()

            combos = [
                dialog.theme_combo,
                dialog.font_size_combo,
                dialog.max_backups_combo,
            ]
            for combo in combos:
                self.assertIsInstance(combo.view(), QListView)
                self.assertTrue(combo.view().hasMouseTracking())
                self.assertTrue(combo.view().viewport().hasMouseTracking())
                self.assertTrue(
                    combo.view().viewport().testAttribute(Qt.WidgetAttribute.WA_Hover)
                )
                self.assertIsInstance(combo.itemDelegate(), ComboRowHeightDelegate)
        finally:
            dialog.close()
            parent.close()


if __name__ == "__main__":
    unittest.main()
