from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QApplication, QWidget

from app.views.widgets.theme_selector import ThemeSelector


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TestThemeSelector(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_theme_selector_populates_from_controller(self) -> None:
        theme_ctrl = MagicMock()
        theme_ctrl.available.return_value = [
            ("light", "Light Theme"),
            ("dark", "Dark Theme"),
        ]

        parent = QWidget()
        selector = ThemeSelector(theme_ctrl, parent=parent)

        try:
            self.assertEqual(2, selector.count())
            self.assertEqual("Light Theme", selector.itemText(0))
            self.assertEqual("light", selector.itemData(0))
            self.assertEqual("Dark Theme", selector.itemText(1))
            self.assertEqual("dark", selector.itemData(1))
        finally:
            selector.close()
            parent.close()
