from __future__ import annotations

import os
import unittest

from PyQt6.QtWidgets import QApplication, QWidget

from app.views.windows.dialogs.about_dialog import AboutDialog


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TestAboutDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_about_dialog_builds_and_exposes_release_metadata(self) -> None:
        parent = QWidget()
        dialog = AboutDialog(parent=parent)

        try:
            self.assertEqual("AboutDialog", type(dialog).__name__)
            self.assertIn("1.1.", dialog.version_label.text())
            self.assertIn("Codebdbd", dialog.developer_label.text())
            self.assertIn("MIT", dialog.license_label.text())
            self.assertTrue(dialog.support_button.text())
            self.assertTrue(dialog.repo_button.text())
            self.assertTrue(dialog.license_button.text())
        finally:
            dialog.close()
            parent.close()


if __name__ == "__main__":
    unittest.main()
