"""Tests for MoveSectionToSphereCommand and SphereToolButton."""

import unittest
from unittest.mock import Mock

from PyQt6.QtWidgets import QApplication

from app.utils.ui.dnd.section_command import MoveSectionToSphereCommand
from app.views.widgets.spheres.sphere_tool_button import SphereToolButton


class TestMoveSectionToSphereCommand(unittest.TestCase):
    """Unit tests for MoveSectionToSphereCommand."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.main = Mock()
        self.sb = Mock()
        self.structure_ctrl = Mock()
        self.main.structure_business = self.sb
        self.main.structure = self.structure_ctrl

        self.db = Mock()
        self.db.sections = Mock()
        self.sb.structure_service = Mock()
        self.sb.structure_service.db = self.db
        self.sb.cache_service = Mock()

    def test_prepare_data_normal(self):
        self.sb.get_section_data.return_value = {
            "id": 10,
            "name": "Frontend",
            "sphere_id": 1,
            "position": 2,
            "icon_path": "icon.png",
        }
        self.sb.has_duplicate_section.return_value = False
        self.sb.get_sections.return_value = [
            {"id": 20, "name": "Backend", "sphere_id": 2, "position": 0},
            {"id": 21, "name": "DevOps", "sphere_id": 2, "position": 1},
        ]

        cmd = MoveSectionToSphereCommand(10, 2, self.main)
        cmd._prepare_data()

        self.assertEqual(cmd.old_sphere_id, 1)
        self.assertEqual(cmd.target_sphere_id, 2)
        self.assertEqual(cmd.original_name, "Frontend")
        self.assertEqual(cmd.new_name, "Frontend")
        self.assertEqual(cmd.old_position, 2)
        self.assertEqual(cmd.new_position, 2)

    def test_prepare_data_with_duplicate_name_auto_suffix(self):
        self.sb.get_section_data.return_value = {
            "id": 10,
            "name": "Docs",
            "sphere_id": 1,
            "position": 0,
            "icon_path": "",
        }
        # First call has duplicate for "Docs", second call has no duplicate for "Docs (1)"
        def mock_has_duplicate(sphere_id, name, exclude_id=None):
            return name == "Docs"

        self.sb.has_duplicate_section.side_effect = mock_has_duplicate
        self.sb.get_sections.return_value = []

        cmd = MoveSectionToSphereCommand(10, 2, self.main)
        cmd._prepare_data()

        self.assertEqual(cmd.new_name, "Docs (1)")
        self.assertEqual(cmd.new_position, 0)

    def test_execute_and_restore_operation(self):
        self.sb.get_section_data.return_value = {
            "id": 10,
            "name": "Design",
            "sphere_id": 1,
            "position": 3,
            "icon_path": "brush.png",
        }
        self.sb.has_duplicate_section.return_value = False
        self.sb.get_sections.return_value = []
        self.sb.update_section.return_value = {"id": 10}

        cmd = MoveSectionToSphereCommand(10, 2, self.main)

        # 1. Redo / Execute
        success = cmd._execute_operation()
        self.assertTrue(success)

        self.sb.update_section.assert_called_with(
            10,
            {
                "name": "Design",
                "sphere_id": 2,
                "position": 0,
                "icon_path": "brush.png",
            },
        )
        self.db.sections._reindex_positions.assert_called_with(
            "section", "sphere_id", 1
        )
        self.sb.cache_service.invalidate_structure_cache.assert_any_call(1)
        self.sb.cache_service.invalidate_structure_cache.assert_any_call(2)

        # 2. Refresh UI on redo
        cmd._last_operation = "redo"
        cmd._refresh_ui()
        self.structure_ctrl.switch_sphere.assert_called_with(
            2, item_to_select=("section", 10)
        )

        # 3. Undo / Restore
        self.sb.update_section.reset_mock()
        self.db.sections._reindex_positions.reset_mock()
        self.structure_ctrl.switch_sphere.reset_mock()

        undo_success = cmd._restore_original_state()
        self.assertTrue(undo_success)

        self.sb.update_section.assert_called_with(
            10,
            {
                "name": "Design",
                "sphere_id": 1,
                "position": 3,
                "icon_path": "brush.png",
            },
        )
        self.db.sections._reindex_positions.assert_called_with(
            "section", "sphere_id", 2
        )

        # 4. Refresh UI on undo
        cmd._last_operation = "undo"
        cmd._refresh_ui()
        self.structure_ctrl.switch_sphere.assert_called_with(
            1, item_to_select=("section", 10)
        )


class TestSphereToolButton(unittest.TestCase):
    """Unit tests for SphereToolButton DnD validation."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_sphere_button_accepts_drops(self):
        btn = SphereToolButton(sphere_id=3)
        self.assertTrue(btn.acceptDrops())
        self.assertEqual(btn.sphere_id, 3)

    def test_is_valid_drop_rejects_same_sphere(self):
        from app.utils.ui.dnd.mime import MimeDataParser

        btn = SphereToolButton(sphere_id=3)
        btn.setChecked(False)

        # Drag event from same sphere (source_sphere_id = 3)
        mime_same = MimeDataParser.create_section_mime_data([5], source_sphere_id=3)
        event_same = Mock()
        event_same.mimeData.return_value = mime_same
        self.assertFalse(btn._is_valid_drop(event_same))

        # Drag event from different sphere (source_sphere_id = 1)
        mime_diff = MimeDataParser.create_section_mime_data([5], source_sphere_id=1)
        event_diff = Mock()
        event_diff.mimeData.return_value = mime_diff
        self.assertTrue(btn._is_valid_drop(event_diff))

    def test_is_valid_drop_rejects_when_checked(self):
        from app.utils.ui.dnd.mime import MimeDataParser

        btn = SphereToolButton(sphere_id=2)
        btn.setChecked(True)  # Active sphere

        mime = MimeDataParser.create_section_mime_data([5], source_sphere_id=1)
        event = Mock()
        event.mimeData.return_value = mime

        self.assertFalse(btn._is_valid_drop(event))


if __name__ == "__main__":
    unittest.main()
