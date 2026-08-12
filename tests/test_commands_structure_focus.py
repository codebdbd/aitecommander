from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.controllers.ui.undo.commands_structure import (
    PasteCategoriesCmd,
    PasteSectionsCmd,
    SaveCategoryCmd,
    SaveSectionCmd,
)
from app.core.results import Result


def _signal() -> SimpleNamespace:
    return SimpleNamespace(emit=Mock())


class _ConnectableSignal:
    def __init__(self) -> None:
        self._callbacks = []
        self.connect = Mock(side_effect=self._connect)
        self.disconnect = Mock(side_effect=self._disconnect)

    def _connect(self, callback) -> None:
        self._callbacks.append(callback)

    def _disconnect(self, callback) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def emit(self, *args) -> None:
        for callback in list(self._callbacks):
            callback(*args)


class TestSaveSectionCmdSignals(unittest.TestCase):
    def _build_business(self, service: Mock) -> SimpleNamespace:
        return SimpleNamespace(
            structure_service=service,
            item_added=_signal(),
            item_updated=_signal(),
            section_selected=_signal(),
            select_category=Mock(),
        )

    @staticmethod
    def _main_window() -> SimpleNamespace:
        return SimpleNamespace(_suppress_deletes=False)

    def test_redo_create_emits_item_added_without_premature_section_selected(self) -> None:
        payload = {"id": 101, "name": "New section", "sphere_id": 1, "position": 3}
        service = Mock()
        service.create_section.return_value = Result.success(payload)
        business = self._build_business(service)

        cmd = SaveSectionCmd(
            new_data={"name": "New section", "sphere_id": 1},
            old_data=None,
            main_window=self._main_window(),
            business=business,
        )
        cmd.redo()

        business.item_added.emit.assert_called_once_with("section", 101, payload)
        business.item_updated.emit.assert_not_called()
        business.section_selected.emit.assert_not_called()

    def test_redo_update_emits_item_updated_and_section_selected(self) -> None:
        payload = {"id": 9, "name": "Renamed", "sphere_id": 1, "position": 1}
        service = Mock()
        service.update_section.return_value = Result.success(payload)
        business = self._build_business(service)

        cmd = SaveSectionCmd(
            new_data={"id": 9, "name": "Renamed", "sphere_id": 1},
            old_data={"id": 9, "name": "Old", "sphere_id": 1},
            main_window=self._main_window(),
            business=business,
        )
        cmd.redo()

        business.section_selected.emit.assert_called_once_with(9)
        business.item_updated.emit.assert_called_once_with("section", 9, payload)
        business.item_added.emit.assert_not_called()

    def test_redo_update_preserves_position_from_old_data(self) -> None:
        payload = {
            "id": 9,
            "name": "Moved",
            "sphere_id": 2,
            "position": 7,
            "icon_path": "",
        }
        service = Mock()
        service.update_section.return_value = Result.success(payload)
        business = self._build_business(service)

        cmd = SaveSectionCmd(
            new_data={"id": 9, "name": "Moved", "sphere_id": 2, "icon_path": ""},
            old_data={
                "id": 9,
                "name": "Old",
                "sphere_id": 1,
                "position": 7,
                "icon_path": "custom.png",
            },
            main_window=self._main_window(),
            business=business,
        )
        cmd.redo()

        service.update_section.assert_called_once()
        sent_payload = service.update_section.call_args.args[1]
        self.assertEqual(sent_payload["position"], 7)
        self.assertEqual(sent_payload["icon_path"], "")

    @patch("app.controllers.ui.undo.commands_structure.schedule_selection_restore")
    def test_redo_update_moved_section_switches_sphere_and_schedules_focus(
        self,
        schedule_restore: Mock,
    ) -> None:
        payload = {"id": 9, "name": "Moved", "sphere_id": 2, "position": 1}
        service = Mock()
        service.update_section.return_value = Result.success(payload)
        business = self._build_business(service)
        selection_handler = SimpleNamespace(_restore_selection_after_load=Mock())
        main = SimpleNamespace(
            _suppress_deletes=False,
            structure=SimpleNamespace(
                switch_sphere=Mock(),
                selection_handler=selection_handler,
            ),
        )

        cmd = SaveSectionCmd(
            new_data={"id": 9, "name": "Moved", "sphere_id": 2},
            old_data={"id": 9, "name": "Old", "sphere_id": 1},
            main_window=main,
            business=business,
        )
        cmd.redo()

        main.structure.switch_sphere.assert_called_once_with(2)
        schedule_restore.assert_called_once()
        restore_callback = schedule_restore.call_args.args[0]
        self.assertEqual(schedule_restore.call_args.args[1], "section_move_sphere_9")

        restore_callback()

        selection_handler._restore_selection_after_load.assert_called_once_with(
            "section", 9
        )
        business.section_selected.emit.assert_not_called()
        business.item_updated.emit.assert_not_called()
        business.item_added.emit.assert_not_called()

    @patch("app.controllers.ui.undo.commands_structure.schedule_selection_restore")
    def test_redo_update_moved_section_waits_for_structure_loaded_before_focus(
        self,
        schedule_restore: Mock,
    ) -> None:
        payload = {"id": 9, "name": "Moved", "sphere_id": 2, "position": 1}
        service = Mock()
        service.update_section.return_value = Result.success(payload)
        business = self._build_business(service)
        business.structure_loaded = _ConnectableSignal()
        selection_handler = SimpleNamespace(_restore_selection_after_load=Mock())
        main = SimpleNamespace(
            _suppress_deletes=False,
            structure=SimpleNamespace(
                switch_sphere=Mock(),
                selection_handler=selection_handler,
            ),
        )

        cmd = SaveSectionCmd(
            new_data={"id": 9, "name": "Moved", "sphere_id": 2},
            old_data={"id": 9, "name": "Old", "sphere_id": 1},
            main_window=main,
            business=business,
        )
        cmd.redo()

        main.structure.switch_sphere.assert_called_once_with(2)
        business.structure_loaded.connect.assert_called_once()
        schedule_restore.assert_not_called()

        business.structure_loaded.emit([])

        business.structure_loaded.disconnect.assert_called_once()
        schedule_restore.assert_called_once()
        self.assertEqual(schedule_restore.call_args.kwargs, {"delay": 0})

    @patch("app.controllers.ui.undo.commands_structure.schedule_selection_restore")
    def test_undo_moved_section_switches_back_and_schedules_focus(
        self,
        schedule_restore: Mock,
    ) -> None:
        restored = {"id": 9, "name": "Old", "sphere_id": 1, "position": 1}
        service = Mock()
        service.update_section.return_value = Result.success(restored)
        business = self._build_business(service)
        selection_handler = SimpleNamespace(_restore_selection_after_load=Mock())
        main = SimpleNamespace(
            _suppress_deletes=False,
            structure=SimpleNamespace(
                switch_sphere=Mock(),
                selection_handler=selection_handler,
            ),
        )

        cmd = SaveSectionCmd(
            new_data={"id": 9, "name": "Moved", "sphere_id": 2},
            old_data=restored,
            main_window=main,
            business=business,
        )
        cmd.undo()

        main.structure.switch_sphere.assert_called_once_with(1)
        schedule_restore.assert_called_once()
        business.section_selected.emit.assert_not_called()
        business.item_updated.emit.assert_not_called()


class TestSaveCategoryCmdSignals(unittest.TestCase):
    def _build_business(self, service: Mock) -> SimpleNamespace:
        return SimpleNamespace(
            structure_service=service,
            item_added=_signal(),
            item_updated=_signal(),
            section_selected=_signal(),
            select_category=Mock(),
        )

    def test_redo_create_emits_item_added_without_premature_select_category(self) -> None:
        payload = {"id": 77, "name": "New cat", "section_id": 10, "position": 2}
        service = Mock()
        service.create_category.return_value = Result.success(payload)
        business = self._build_business(service)

        cmd = SaveCategoryCmd(
            new_data={"name": "New cat", "section_id": 10},
            old_data=None,
            main_window=Mock(),
            business=business,
        )
        cmd.redo()

        business.item_added.emit.assert_called_once_with("category", 10, payload)
        business.item_updated.emit.assert_not_called()
        business.select_category.assert_not_called()

    def test_redo_update_emits_item_updated_and_select_category(self) -> None:
        payload = {"id": 42, "name": "Updated cat", "section_id": 10, "position": 1}
        service = Mock()
        service.update_category.return_value = Result.success(payload)
        business = self._build_business(service)

        cmd = SaveCategoryCmd(
            new_data={"id": 42, "name": "Updated cat", "section_id": 10},
            old_data={"id": 42, "name": "Old cat", "section_id": 10},
            main_window=Mock(),
            business=business,
        )
        cmd.redo()

        business.select_category.assert_called_once_with(42)
        business.item_updated.emit.assert_called_once_with("category", 42, payload)
        business.item_added.emit.assert_not_called()


class TestPasteCategoriesCmdRefresh(unittest.TestCase):
    def test_refresh_after_categories_uses_targeted_section_refresh(self) -> None:
        tree_manager = SimpleNamespace(replace_section_categories=Mock())
        business = SimpleNamespace(
            _invalidate_categories_cache=Mock(),
            get_categories=Mock(return_value=[{"id": 1, "section_id": 10, "name": "cat"}]),
            section_selected=_signal(),
            async_service=SimpleNamespace(schedule_structure_reload=Mock()),
        )
        cmd = PasteCategoriesCmd.__new__(PasteCategoriesCmd)
        cmd.main = SimpleNamespace(
            structure=SimpleNamespace(tree_manager=tree_manager),
        )
        cmd._business = business
        cmd._section_id = 10

        cmd._refresh_after_categories()

        business._invalidate_categories_cache.assert_called_once_with(10)
        business.get_categories.assert_called_once_with(10)
        tree_manager.replace_section_categories.assert_called_once_with(
            10,
            [{"id": 1, "section_id": 10, "name": "cat"}],
        )
        business.section_selected.emit.assert_called_once_with(10)
        business.async_service.schedule_structure_reload.assert_not_called()


class TestPasteSectionsCmdRefresh(unittest.TestCase):
    def test_refresh_after_sections_uses_targeted_refresh(self) -> None:
        tree_manager = SimpleNamespace(replace_section_categories=Mock())
        business = SimpleNamespace(
            _invalidate_structure_cache=Mock(),
            get_sections=Mock(
                return_value=[{"id": 101, "sphere_id": 3, "name": "sec"}]
            ),
            get_categories=Mock(
                side_effect=lambda section_id: [{"id": 1, "section_id": section_id, "name": "cat"}]
            ),
            item_added=_signal(),
            item_deleted=_signal(),
            async_service=SimpleNamespace(schedule_structure_reload=Mock()),
        )
        cmd = PasteSectionsCmd.__new__(PasteSectionsCmd)
        cmd.main = SimpleNamespace(
            structure=SimpleNamespace(tree_manager=tree_manager),
        )
        cmd._business = business
        cmd._sphere_id = 3
        cmd._created_section_ids = [101]
        cmd._merged_section_ids = [102]
        cmd._merged_category_ids = []
        cmd._merged_link_ids = []

        cmd._refresh_after_sections()

        business._invalidate_structure_cache.assert_called_once()
        business.get_sections.assert_called_once_with(3)
        business.item_added.emit.assert_called_once_with(
            "section",
            3,
            {"id": 101, "sphere_id": 3, "name": "sec"},
        )
        tree_manager.replace_section_categories.assert_any_call(
            101,
            [{"id": 1, "section_id": 101, "name": "cat"}],
        )
        tree_manager.replace_section_categories.assert_any_call(
            102,
            [{"id": 1, "section_id": 102, "name": "cat"}],
        )
        business.async_service.schedule_structure_reload.assert_not_called()

    def test_refresh_after_sections_falls_back_to_full_reload_when_targeted_refresh_fails(self) -> None:
        business = SimpleNamespace(
            _invalidate_structure_cache=Mock(),
            get_sections=Mock(side_effect=RuntimeError("boom")),
            get_categories=Mock(),
            item_added=_signal(),
            item_deleted=_signal(),
            async_service=SimpleNamespace(schedule_structure_reload=Mock()),
        )
        cmd = PasteSectionsCmd.__new__(PasteSectionsCmd)
        cmd.main = SimpleNamespace(structure=SimpleNamespace(tree_manager=None))
        cmd._business = business
        cmd._sphere_id = 3
        cmd._created_section_ids = [101]
        cmd._merged_section_ids = []
        cmd._merged_category_ids = []
        cmd._merged_link_ids = []

        cmd._refresh_after_sections()

        business.async_service.schedule_structure_reload.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
