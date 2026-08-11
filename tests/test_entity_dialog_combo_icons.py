from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QApplication

from app.views.windows.dialogs.entity_dialogs import _combo_icon_loader


class TestEntityDialogComboIcons(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    @patch("app.views.windows.dialogs.entity_dialogs.get_cached_icon_with_fallback")
    def test_section_combo_icon_loader_uses_default_when_custom_icon_is_missing(
        self,
        fallback_loader_mock: Mock,
    ) -> None:
        fallback_icon = QIcon(QPixmap(16, 16))
        fallback_loader_mock.return_value = fallback_icon

        icon = _combo_icon_loader("section")("deleted-custom-icon.png")

        fallback_loader_mock.assert_called_once_with(
            "deleted-custom-icon.png", "section"
        )
        self.assertIs(icon, fallback_icon)


if __name__ == "__main__":
    unittest.main()
