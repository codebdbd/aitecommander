from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QPushButton

from app.views.windows.dialogs.browser_profile_dialog import BrowserProfileDialog
from app.views.windows.dialogs.bad_url_cleanup_dialog import BadUrlCleanupDialog
from app.views.windows.dialogs.entity_dialogs import (
    SectionDialog,
    CategoryDialog,
    SettingsDialog,
    ChromeProfileDialog,
)
from app.views.windows.dialogs.import_browser_dialog import ImportBrowserDialog
from app.config_data.runtime_config import runtime_app_config as app_config

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TestDialogButtonsUnification(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_buttons_equalized_and_fixed(self):
        sb = MagicMock()
        sb.get_all_spheres.return_value = []
        sb.get_sections_by_sphere.return_value = []

        settings = MagicMock()
        settings.get_language.return_value = "ru"
        settings.get_theme.return_value = "dark"
        settings.get_font_size.return_value = 10
        settings.get_max_backup_copies.return_value = 5

        theme_ctrl = MagicMock()
        theme_ctrl.get_available_themes.return_value = ["dark", "light"]

        dialogs = [
            ("BrowserProfileDialog", BrowserProfileDialog(mode="multi", profile_mode="rotation")),
            ("SectionDialog", SectionDialog(structure_business=sb)),
            ("CategoryDialog", CategoryDialog(structure_business=sb)),
            ("SettingsDialog", SettingsDialog(settings=settings, theme_ctrl=theme_ctrl)),
            ("ChromeProfileDialog", ChromeProfileDialog(parent=None)),
            ("ImportBrowserDialog", ImportBrowserDialog(structure_business_logic=sb)),
        ]

        for name, dlg in dialogs:
            dlg.retranslateUi()
            dlg.show()
            self._app.processEvents()

            boxes = dlg.findChildren(QDialogButtonBox)
            for box in boxes:
                btns = box.findChildren(QPushButton)
                widths = [b.width() for b in btns]
                if len(widths) > 1:
                    self.assertEqual(len(set(widths)), 1, f"Mismatched button widths in {name}: {widths}")
                for b in btns:
                    self.assertGreaterEqual(
                        b.width(),
                        app_config.ui.get_fixed_button_width(),
                        f"Button {b.text()} in {name} is {b.width()} < {app_config.ui.get_fixed_button_width()}",
                    )

    def test_browser_profile_dialog_layout_and_buttons(self):
        b = BrowserProfileDialog(mode="multi", profile_mode="rotation")
        b.retranslateUi()
        b.show()
        self._app.processEvents()

        self.assertGreaterEqual(b.width(), 740)
        self.assertEqual(b.select_all_btn.width(), b.deselect_all_btn.width())
        self.assertGreaterEqual(b.select_all_btn.width(), app_config.ui.get_fixed_button_width())

        # Footer buttons
        footer_btns = b.button_box.findChildren(QPushButton)
        self.assertEqual(len(footer_btns), 2)
        self.assertEqual(footer_btns[0].width(), footer_btns[1].width())

    def test_bad_url_cleanup_dialog_button_pairs(self):
        service = MagicMock()
        db = MagicMock()
        dlg = BadUrlCleanupDialog(service=service, db=db)
        dlg.retranslateUi()
        dlg.show()
        self._app.processEvents()

        self.assertEqual(dlg.select_all_button.width(), dlg.select_none_button.width())
        self.assertEqual(dlg.background_button.width(), dlg.cancel_button.width())
        self.assertEqual(dlg.close_button.width(), dlg.delete_button.width())
