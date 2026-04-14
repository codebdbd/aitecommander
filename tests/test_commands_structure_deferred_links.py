from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.controllers.ui.undo.commands_structure import DeleteSectionsCmd


class _BusinessStub:
    def __init__(self) -> None:
        self.structure_service = Mock()
        self._generation = 1
        self.begin_batch = Mock()
        self.end_batch = Mock()
        self.select_section = Mock()
        self.suspend_structure_preload = Mock()
        self.resume_structure_preload = Mock()

    def current_structure_mutation_generation(self) -> int:
        return self._generation

    def is_structure_mutation_generation_current(self, generation: int) -> bool:
        return int(generation) == int(self._generation)


class TestDeleteSectionsDeferredLinksRestore(unittest.TestCase):
    def test_undo_skips_stale_deferred_links_restore(self) -> None:
        business = _BusinessStub()
        import_links_bulk = Mock()
        main = SimpleNamespace(
            structure=SimpleNamespace(selection_handler=None, tree_manager=None),
            get_current_category_id=Mock(return_value=None),
            reload_current_category=Mock(),
        )
        cmd = DeleteSectionsCmd(
            sections_data=[],
            main_window=main,
            business=business,
        )
        cmd._backup_trees = [
            {
                "section": {"id": 501, "sphere_id": 3, "name": "Sec", "position": 1},
                "categories": [
                    {"category": {"id": idx, "section_id": 501, "name": f"Cat {idx}"}}
                    for idx in range(1000, 1065)
                ],
            }
        ]

        deferred_dispatch: dict[str, object] = {}

        def fake_run_db(task, description, on_finished=None, on_error=None):
            if description == "delete_sections_undo_restore":
                result = task()
                if on_finished is not None:
                    on_finished(result)
                return None
            if description == "delete_sections_undo_restore_links":
                deferred_dispatch["task"] = task
                deferred_dispatch["on_finished"] = on_finished
                deferred_dispatch["on_error"] = on_error
                return None
            raise AssertionError(f"unexpected description: {description}")

        split_trees = (
            list(cmd._backup_trees),
            [{"id": 9001, "category_id": 1000, "name": "Link"}],
            {1000},
        )

        with (
            patch(
                "app.controllers.ui.undo.commands_structure.run_db",
                side_effect=fake_run_db,
            ),
            patch(
                "app.controllers.ui.undo.commands_structure._split_section_trees_for_deferred_links",
                return_value=split_trees,
            ),
            patch(
                "app.controllers.ui.undo.commands_structure._resolve_database",
                return_value=SimpleNamespace(
                    import_export_manager=SimpleNamespace(import_links_bulk=import_links_bulk)
                ),
            ),
        ):
            cmd.undo()

            self.assertIn("task", deferred_dispatch)
            business._generation = 2
            result = deferred_dispatch["task"]()
            deferred_dispatch["on_finished"](result)

        import_links_bulk.assert_not_called()
        main.reload_current_category.assert_not_called()


if __name__ == "__main__":
    unittest.main()
