from __future__ import annotations

import unittest

from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QApplication, QComboBox

from app.utils.ui.qt.combo_helpers import (
    add_combo_item,
    add_combo_mapping_item,
    select_combo_data,
    select_first_combo_item,
    try_select_combo_data,
    try_select_first_combo_item,
)


class TestComboHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_select_combo_data_prefers_current_then_preferred(self) -> None:
        combo = QComboBox()
        combo.addItem("Dark", "dark")
        combo.addItem("Light", "light")

        index = select_combo_data(
            combo,
            current_data="light",
            preferred_data="dark",
            fallback_to_first=False,
        )

        self.assertEqual(1, index)
        self.assertEqual("light", combo.currentData())

    def test_select_combo_data_falls_back_to_preferred(self) -> None:
        combo = QComboBox()
        combo.addItem("Dark", "dark")
        combo.addItem("Light", "light")

        index = select_combo_data(
            combo,
            current_data="missing",
            preferred_data="light",
            fallback_to_first=False,
        )

        self.assertEqual(1, index)
        self.assertEqual("light", combo.currentData())

    def test_select_combo_data_can_fall_back_to_first_item(self) -> None:
        combo = QComboBox()
        combo.addItem("Dark", "dark")
        combo.addItem("Light", "light")

        index = select_combo_data(
            combo,
            current_data="missing",
            preferred_data="also-missing",
        )

        self.assertEqual(0, index)
        self.assertEqual("dark", combo.currentData())

    def test_select_first_combo_item_can_preserve_existing_selection(self) -> None:
        combo = QComboBox()
        combo.addItem("Dark", "dark")
        combo.addItem("Light", "light")
        combo.setCurrentIndex(1)

        changed = select_first_combo_item(combo, only_if_unset=True)

        self.assertFalse(changed)
        self.assertEqual("light", combo.currentData())

    def test_try_helpers_are_safe_with_invalid_object(self) -> None:
        self.assertFalse(try_select_combo_data(object(), "light"))
        self.assertFalse(try_select_first_combo_item(object(), only_if_unset=True))

    def test_add_combo_item_supports_optional_icon_and_data(self) -> None:
        combo = QComboBox()
        icon = QIcon(QPixmap(16, 16))

        add_combo_item(combo, "Dreamy", "dreamy_room", icon=icon)

        self.assertEqual(1, combo.count())
        self.assertEqual("Dreamy", combo.itemText(0))
        self.assertEqual("dreamy_room", combo.itemData(0))
        self.assertFalse(combo.itemIcon(0).isNull())

    def test_add_combo_mapping_item_uses_mapping_keys_and_icon_loader(self) -> None:
        combo = QComboBox()
        icon = QIcon(QPixmap(16, 16))

        added = add_combo_mapping_item(
            combo,
            {"name": "Work", "id": 7, "icon_path": "work.png"},
            icon_key="icon_path",
            icon_loader=lambda path: icon if path == "work.png" else None,
        )

        self.assertTrue(added)
        self.assertEqual(1, combo.count())
        self.assertEqual("Work", combo.itemText(0))
        self.assertEqual(7, combo.itemData(0))
        self.assertFalse(combo.itemIcon(0).isNull())

    def test_add_combo_mapping_item_skips_incomplete_records(self) -> None:
        combo = QComboBox()

        added = add_combo_mapping_item(combo, {"name": "Broken"})

        self.assertFalse(added)
        self.assertEqual(0, combo.count())


if __name__ == "__main__":
    unittest.main()
