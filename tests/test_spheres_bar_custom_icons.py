from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QToolButton,
    QWidget,
)

from app.controllers.business.structure_business import StructureBusinessLogic
from app.controllers.ui.structure.spheres_bar_controller import SpheresBarController
from app.core.database_manager import DatabaseManager
from app.models.db import Database


class FakeMainWindow(QWidget):
    def __init__(self, sb):
        super().__init__()
        self.structure_business = sb
        self.structure = MagicMock()
        self.sphere_group = QButtonGroup(self)
        self.spheres_bar = QWidget(self)
        self.spheres_bar.setLayout(QHBoxLayout())
        self.sphere_buttons = {}
        self.settings = MagicMock()
        self.settings.get_theme.return_value = "dark"


class TestSpheresBarCustomIcons(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        DatabaseManager.configure(self.db_path)
        DatabaseManager.ensure_schema()
        self.db = Database()
        self.db.spheres.initialize_default_spheres()
        self.sb = StructureBusinessLogic(self.db)
        self.window = FakeMainWindow(self.sb)
        self.controller = SpheresBarController(self.window)

    def tearDown(self) -> None:
        try:
            if hasattr(self.sb, "async_service") and hasattr(self.sb.async_service, "async_operations"):
                self.sb.async_service.async_operations.cleanup()
                pool = getattr(self.sb.async_service.async_operations, "_structure_db_pool", None)
                if pool is not None:
                    pool.waitForDone(2000)
        except Exception:
            pass
        self.db.close()
        DatabaseManager.close_all()
        DatabaseManager.configure(None)
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_update_sphere_icon_db_and_cache(self) -> None:
        # Fetch initial spheres
        spheres = self.sb.structure_coordinator.db.spheres.get_spheres()
        self.assertTrue(len(spheres) > 0)
        sphere_id = spheres[0]["id"]

        # Cache warmup
        self.sb._cached_spheres = [dict(s) for s in spheres]

        # Update to custom icon
        success = self.sb.update_sphere_icon(sphere_id, "my_custom_sphere.png")
        self.assertTrue(success)

        # Check DB
        updated_sphere = self.sb.structure_coordinator.db.spheres.get_sphere_by_id(sphere_id)
        self.assertIsNotNone(updated_sphere)
        self.assertEqual("my_custom_sphere.png", updated_sphere.get("icon_path"))

        # Check cache
        cached = next((s for s in self.sb._cached_spheres if s["id"] == sphere_id), None)
        self.assertIsNotNone(cached)
        self.assertEqual("my_custom_sphere.png", cached.get("icon_path"))

        # Reset icon
        reset_success = self.sb.update_sphere_icon(sphere_id, "")
        self.assertTrue(reset_success)

        updated_sphere_after_reset = self.sb.structure_coordinator.db.spheres.get_sphere_by_id(sphere_id)
        self.assertEqual("", updated_sphere_after_reset.get("icon_path"))

    def test_resolve_sphere_icon_fallback(self) -> None:
        # Default sphere with empty icon_path (English)
        sphere = {"id": 1, "name": "Work", "icon_path": ""}
        icon = self.controller._resolve_sphere_icon(sphere)
        self.assertFalse(icon.isNull())
        self.assertEqual("work_icon.png", self.controller._get_default_icon_name_for_sphere(sphere))

        # Russian sphere names must resolve to sphere icons, NEVER section.png
        self.assertEqual("work_icon.png", self.controller._get_default_icon_name_for_sphere("Работа"))
        self.assertEqual("personal_icon.png", self.controller._get_default_icon_name_for_sphere("Личное"))
        self.assertEqual("study_icon.png", self.controller._get_default_icon_name_for_sphere("Учёба"))
        self.assertEqual("study_icon.png", self.controller._get_default_icon_name_for_sphere("Учеба"))
        self.assertEqual("ai_icon.png", self.controller._get_default_icon_name_for_sphere("AI"))

        # Unknown sphere name fallback to sphere icon, not section.png
        custom_sphere = {"id": 99, "name": "RandomName", "icon_path": ""}
        icon_unknown = self.controller._resolve_sphere_icon(custom_sphere)
        self.assertFalse(icon_unknown.isNull())
        self.assertNotEqual("section.png", self.controller._get_default_icon_name_for_sphere(custom_sphere))

    def test_resolve_sphere_icon_from_user_dir(self) -> None:
        # Create a dummy user icon file in user_icons_dir
        with tempfile.TemporaryDirectory() as user_dir_str:
            user_dir = Path(user_dir_str)
            dummy_icon_file = user_dir / "custom_work.png"

            # Create a 16x16 PNG
            pix = QPixmap(16, 16)
            pix.fill()
            pix.save(str(dummy_icon_file), "PNG")

            with patch("app.controllers.ui.structure.spheres_bar_controller.icon_path_service.get_user_icons_dir", return_value=user_dir):
                sphere = {"id": 1, "name": "Work", "icon_path": "custom_work.png"}
                icon = self.controller._resolve_sphere_icon(sphere)
                self.assertFalse(icon.isNull())

    def test_build_button_sets_context_menu_policy(self) -> None:
        sphere = {"id": 1, "name": "Work", "icon_path": ""}
        btn = self.controller._build_button(sphere)

        from PyQt6.QtCore import Qt
        self.assertEqual(Qt.ContextMenuPolicy.CustomContextMenu, btn.contextMenuPolicy())
        self.assertIn(1, self.window.sphere_buttons)

    def test_context_menu_actions_state(self) -> None:
        spheres = self.sb.structure_coordinator.db.spheres.get_spheres()
        sphere_id = spheres[0]["id"]
        sphere = spheres[0]
        btn = self.controller._build_button(sphere)

        # Spy on QMenu.exec
        captured_actions = []

        def fake_exec(menu, global_pos):
            for action in menu.actions():
                if action.isSeparator():
                    continue
                captured_actions.append((action.text(), action.isEnabled()))

        with patch("PyQt6.QtWidgets.QMenu.exec", new=fake_exec):
            self.controller._on_context_menu(sphere_id, QPoint(0, 0))

        # 4 actions total: Rename, Reset Name, Change Icon, Reset Icon
        self.assertEqual(4, len(captured_actions))
        action_names = [a[0] for a in captured_actions]
        self.assertTrue(any("Rename" in a or "Переименовать" in a for a in action_names))
        self.assertTrue(any("Change" in a or "Сменить" in a for a in action_names))

        # Initially, name matches default ("AI") and icon_path is empty -> both resets are disabled
        reset_name_action = next((a for a in captured_actions if ("Reset" in a[0] or "Сбросить" in a[0]) and ("Name" in a[0] or "название" in a[0])), None)
        self.assertIsNotNone(reset_name_action)
        self.assertFalse(reset_name_action[1])  # isEnabled is False

        reset_icon_action = next((a for a in captured_actions if ("Reset" in a[0] or "Сбросить" in a[0]) and ("Icon" in a[0] or "иконку" in a[0])), None)
        self.assertIsNotNone(reset_icon_action)
        self.assertFalse(reset_icon_action[1])  # isEnabled is False

        # Now test with custom icon_path and custom name
        captured_actions.clear()
        self.sb.update_sphere_icon(sphere_id, "custom.png")
        self.sb.update_sphere_name(sphere_id, "Custom Sphere Name")
        btn.setProperty("sphereName", "Custom Sphere Name")

        with patch("PyQt6.QtWidgets.QMenu.exec", new=fake_exec):
            self.controller._on_context_menu(sphere_id, QPoint(0, 0))

        reset_name_custom = next((a for a in captured_actions if "Name" in a[0] or "название" in a[0]), None)
        self.assertIsNotNone(reset_name_custom)
        self.assertTrue(reset_name_custom[1])  # isEnabled is True

        reset_icon_custom = next((a for a in captured_actions if "Icon" in a[0] or "иконку" in a[0]), None)
        self.assertIsNotNone(reset_icon_custom)
        self.assertTrue(reset_icon_custom[1])  # isEnabled is True

    def test_reset_sphere_icon_handler(self) -> None:
        spheres = self.sb.structure_coordinator.db.spheres.get_spheres()
        sphere_id = spheres[0]["id"]
        sphere = spheres[0]
        btn = self.controller._build_button(sphere)
        self.sb.update_sphere_icon(sphere_id, "custom.png")

        self.controller._reset_sphere_icon(sphere_id)

        # Check that update_sphere_icon restored the explicit default icon filename
        updated_sphere = self.sb.structure_coordinator.db.spheres.get_sphere_by_id(sphere_id)
        expected_icon = self.controller._get_default_icon_name_for_sphere(sphere)
        self.assertEqual(expected_icon, updated_sphere.get("icon_path"))

    def test_update_sphere_name_db_and_cache(self) -> None:
        spheres = self.sb.structure_coordinator.db.spheres.get_spheres()
        sphere_id = spheres[0]["id"]

        # Cache warmup
        self.sb._cached_spheres = [dict(s) for s in spheres]

        # Update to custom name
        success = self.sb.update_sphere_name(sphere_id, "Новая Сфера")
        self.assertTrue(success)

        # Check DB
        updated_sphere = self.sb.structure_coordinator.db.spheres.get_sphere_by_id(sphere_id)
        self.assertEqual("Новая Сфера", updated_sphere.get("name"))

        # Check cache
        cached = next((s for s in self.sb._cached_spheres if s["id"] == sphere_id), None)
        self.assertIsNotNone(cached)
        self.assertEqual("Новая Сфера", cached.get("name"))

        # Empty name should fail validation
        empty_success = self.sb.update_sphere_name(sphere_id, "   ")
        self.assertFalse(empty_success)

    def test_rename_and_reset_sphere_name_handlers(self) -> None:
        spheres = self.sb.structure_coordinator.db.spheres.get_spheres()
        sphere_id = spheres[0]["id"]
        sphere = spheres[0]
        btn = self.controller._build_button(sphere)

        # 1. Rename sphere via dialog mock
        with patch(
            "app.controllers.ui.structure.spheres_bar_controller.SphereRenameDialog"
        ) as mock_dialog_cls:
            mock_dialog_instance = mock_dialog_cls.return_value
            mock_dialog_instance.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog_instance.get_name.return_value = "Мой ИИ"
            self.controller._rename_sphere(sphere_id)

        updated_sphere = self.sb.structure_coordinator.db.spheres.get_sphere_by_id(sphere_id)
        self.assertEqual("Мой ИИ", updated_sphere.get("name"))
        self.assertEqual("Мой ИИ", btn.property("sphereName"))
        self.assertEqual("Мой ИИ", btn.toolTip())

        # 2. Reset sphere name
        self.controller._reset_sphere_name(sphere_id)
        reset_sphere = self.sb.structure_coordinator.db.spheres.get_sphere_by_id(sphere_id)
        self.assertEqual("AI", reset_sphere.get("name"))
        self.assertEqual("AI", btn.property("sphereName"))

    def test_sphere_rename_dialog_properties(self) -> None:
        from app.views.windows.dialogs.entity_dialogs import SphereRenameDialog
        from PyQt6.QtWidgets import QDialogButtonBox
        from app.config_data.runtime_config import runtime_app_config as app_config

        dialog = SphereRenameDialog(current_name="Test Sphere")
        dialog.show()

        # Check input line edit initial value and height
        self.assertEqual(dialog.get_name(), "Test Sphere")
        self.assertEqual(dialog.name_le.height(), app_config.ui.get_dialog_control_height())

        # Check buttons text and width
        bb = dialog._button_box
        self.assertIsNotNone(bb)
        ok_btn = bb.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = bb.button(QDialogButtonBox.StandardButton.Cancel)

        self.assertEqual(ok_btn.width(), app_config.ui.get_fixed_button_width())
        self.assertEqual(cancel_btn.width(), app_config.ui.get_fixed_button_width())
        self.assertEqual(ok_btn.height(), app_config.ui.get_dialog_control_height())
        self.assertEqual(cancel_btn.height(), app_config.ui.get_dialog_control_height())

        # Buttons localized text (Сохранить / Отмена in Russian environment or Save / Cancel)
        self.assertIn(ok_btn.text(), ["Сохранить", "Save"])
        self.assertIn(cancel_btn.text(), ["Отмена", "Cancel"])

        dialog.close()


if __name__ == "__main__":
    unittest.main()

