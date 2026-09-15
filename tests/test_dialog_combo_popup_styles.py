from __future__ import annotations

import unittest

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QListView, QWidget

from app.views.windows.dialogs.base_dialog import ComboRowHeightDelegate
from app.views.windows.dialogs.entity_dialogs import SettingsDialog


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

    def test_dialog_combo_icon_vertical_centering(self) -> None:
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QIcon, QImage, QPainter, QPixmap
        from PyQt6.QtWidgets import QComboBox, QDialog

        from app.config_data.runtime_config import runtime_app_config as app_config
        from app.services.theme_stylesheet_service import ThemeStylesheetService

        svc = ThemeStylesheetService(app_config)
        qss = svc.load_stylesheet("violet_pulse", "violet_pulse.qss")
        self._app.setStyleSheet(qss)

        dlg = QDialog()
        try:
            combo = QComboBox(dlg)
            combo.setFixedHeight(32)
            combo.setFixedWidth(200)
            combo.setIconSize(QSize(24, 24))

            pix = QPixmap(24, 24)
            pix.fill(Qt.GlobalColor.cyan)
            combo.addItem(QIcon(pix), "AI")
            dlg.show()
            self._app.processEvents()

            img = QImage(combo.size(), QImage.Format.Format_ARGB32)
            img.fill(Qt.GlobalColor.black)
            p = QPainter(img)
            combo.render(p)
            p.end()

            icon_ys = []
            for y in range(img.height()):
                for x in range(35):
                    c = img.pixelColor(x, y)
                    if c.blue() > 200 and c.green() > 200 and c.red() < 50:
                        icon_ys.append(y)
                        break

            self.assertTrue(bool(icon_ys), "Icon pixels not found in rendered combo")
            top_gap = min(icon_ys)
            bot_gap = combo.height() - 1 - max(icon_ys)
            self.assertEqual(
                top_gap,
                bot_gap,
                f"Icon in QComboBox is not vertically centered: top_gap={top_gap}, bot_gap={bot_gap}",
            )
        finally:
            dlg.close()

    def test_dialog_button_icon_vertical_centering(self) -> None:
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QIcon, QImage, QPainter, QPixmap
        from PyQt6.QtWidgets import QDialog, QPushButton

        from app.config_data.runtime_config import runtime_app_config as app_config
        from app.services.theme_stylesheet_service import ThemeStylesheetService

        svc = ThemeStylesheetService(app_config)
        qss = svc.load_stylesheet("violet_pulse", "violet_pulse.qss")
        self._app.setStyleSheet(qss)

        dlg = QDialog()
        try:
            btn = QPushButton("Icon", dlg)
            btn.setFixedHeight(32)
            btn.setFixedWidth(100)
            btn.setIconSize(QSize(24, 24))

            pix = QPixmap(24, 24)
            pix.fill(Qt.GlobalColor.cyan)
            btn.setIcon(QIcon(pix))
            dlg.show()
            self._app.processEvents()

            img = QImage(btn.size(), QImage.Format.Format_ARGB32)
            img.fill(Qt.GlobalColor.black)
            p = QPainter(img)
            btn.render(p)
            p.end()

            icon_ys = []
            for y in range(img.height()):
                for x in range(35):
                    c = img.pixelColor(x, y)
                    if c.blue() > 200 and c.green() > 200 and c.red() < 50:
                        icon_ys.append(y)
                        break

            self.assertTrue(bool(icon_ys), "Icon pixels not found in rendered button")
            top_gap = min(icon_ys)
            bot_gap = btn.height() - 1 - max(icon_ys)
            self.assertEqual(
                top_gap,
                bot_gap,
                f"Icon in QPushButton is not vertically centered: top_gap={top_gap}, bot_gap={bot_gap}",
            )
        finally:
            dlg.close()


if __name__ == "__main__":
    unittest.main()
