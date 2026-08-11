from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.controllers.ui.undo.commands_links import (
    BatchDeleteLinksCmd,
    BatchSaveLinksCmd,
    SaveLinkCmd,
)


class TestBatchDeleteLinksCmdAsync(unittest.TestCase):
    def _build_main(self) -> SimpleNamespace:
        links_business = SimpleNamespace(
            links=SimpleNamespace(
                batch_delete_links=Mock(return_value=3),
                batch_create_or_update_links=Mock(return_value=[1, 2, 3]),
            ),
            items_batch_deleted=SimpleNamespace(emit=Mock()),
            batch_updated=SimpleNamespace(emit=Mock()),
            invalidate_cache=Mock(),
        )
        link_operations = SimpleNamespace(emit_top_panels_changed=Mock())
        links_table_controller = SimpleNamespace(reload=Mock())
        return SimpleNamespace(
            database_controller=SimpleNamespace(db=Mock()),
            links_business=links_business,
            link_operations=link_operations,
            links_table_controller=links_table_controller,
        )

    @patch("app.controllers.ui.undo.commands_links.run_db")
    def test_redo_uses_run_db_and_defers_ui_updates(self, run_db_mock: Mock) -> None:
        main = self._build_main()
        cmd = BatchDeleteLinksCmd(
            [
                {"id": 1, "category_id": 11},
                {"id": 2, "category_id": 11},
                {"id": 3, "category_id": 12},
            ],
            main,
        )

        cmd.redo()

        main.links_business.items_batch_deleted.emit.assert_not_called()
        main.links_table_controller.reload.assert_not_called()
        run_db_mock.assert_called_once()
        on_finished = run_db_mock.call_args.kwargs["on_finished"]
        on_finished(3)

        main.links_business.items_batch_deleted.emit.assert_called_once_with(
            "link", [1, 2, 3]
        )
        self.assertEqual(main.links_table_controller.reload.call_count, 2)
        main.link_operations.emit_top_panels_changed.assert_called_once()
        main.links_business.invalidate_cache.assert_called_once()

    @patch("app.controllers.ui.undo.commands_links.run_db")
    def test_undo_uses_run_db_and_defers_ui_updates(self, run_db_mock: Mock) -> None:
        main = self._build_main()
        cmd = BatchDeleteLinksCmd(
            [
                {"id": 1, "category_id": 11},
                {"id": 2, "category_id": 11},
                {"id": 3, "category_id": 12},
            ],
            main,
        )

        cmd.undo()

        main.links_business.batch_updated.emit.assert_not_called()
        main.links_table_controller.reload.assert_not_called()
        run_db_mock.assert_called_once()
        on_finished = run_db_mock.call_args.kwargs["on_finished"]
        on_finished([1, 2, 3])

        main.links_business.batch_updated.emit.assert_called_once_with(True)
        self.assertEqual(main.links_table_controller.reload.call_count, 2)
        main.link_operations.emit_top_panels_changed.assert_called_once()
        main.links_business.invalidate_cache.assert_called_once()

    @patch("app.controllers.ui.undo.commands_links.DialogManager.show_error")
    @patch("app.controllers.ui.undo.commands_links.run_db")
    def test_redo_error_shows_dialog_and_skips_success_effects(
        self, run_db_mock: Mock, show_error_mock: Mock
    ) -> None:
        main = self._build_main()
        cmd = BatchDeleteLinksCmd(
            [{"id": 1, "category_id": 11}],
            main,
        )

        cmd.redo()

        on_error = run_db_mock.call_args.kwargs["on_error"]
        on_error(RuntimeError("boom"))

        main.links_business.items_batch_deleted.emit.assert_not_called()
        main.links_table_controller.reload.assert_not_called()
        main.link_operations.emit_top_panels_changed.assert_not_called()
        main.links_business.invalidate_cache.assert_not_called()
        show_error_mock.assert_called_once()

    @patch("app.controllers.ui.undo.commands_links.DialogManager.show_error")
    @patch("app.controllers.ui.undo.commands_links.run_db")
    def test_undo_error_shows_dialog_and_skips_success_effects(
        self, run_db_mock: Mock, show_error_mock: Mock
    ) -> None:
        main = self._build_main()
        cmd = BatchDeleteLinksCmd(
            [{"id": 1, "category_id": 11}],
            main,
        )

        cmd.undo()

        on_error = run_db_mock.call_args.kwargs["on_error"]
        on_error(RuntimeError("boom"))

        main.links_business.batch_updated.emit.assert_not_called()
        main.links_table_controller.reload.assert_not_called()
        main.link_operations.emit_top_panels_changed.assert_not_called()
        main.links_business.invalidate_cache.assert_not_called()
        show_error_mock.assert_called_once()

    @patch("app.controllers.ui.undo.commands_links.run_db")
    def test_undo_task_raises_on_partial_restore_result(self, run_db_mock: Mock) -> None:
        main = self._build_main()
        main.links_business.links.batch_create_or_update_links.return_value = [1, 2]
        cmd = BatchDeleteLinksCmd(
            [
                {"id": 1, "category_id": 11},
                {"id": 2, "category_id": 11},
                {"id": 3, "category_id": 12},
            ],
            main,
        )

        cmd.undo()

        task = run_db_mock.call_args.args[0]
        with self.assertRaisesRegex(RuntimeError, "expected to restore 3 links, restored 2"):
            task()

    @patch("app.controllers.ui.undo.commands_links.run_db")
    def test_undo_task_raises_on_mismatched_restored_ids(self, run_db_mock: Mock) -> None:
        main = self._build_main()
        main.links_business.links.batch_create_or_update_links.return_value = [1, 2, 999]
        cmd = BatchDeleteLinksCmd(
            [
                {"id": 1, "category_id": 11},
                {"id": 2, "category_id": 11},
                {"id": 3, "category_id": 12},
            ],
            main,
        )

        cmd.undo()

        task = run_db_mock.call_args.args[0]
        with self.assertRaisesRegex(RuntimeError, "restored link ids do not match"):
            task()


@patch("app.controllers.ui.undo.commands_links.QCoreApplication")
class TestSaveLinkCmdCategoryRecovery(unittest.TestCase):
    def _build_main(self, *, current_category_id: int | None = 77) -> SimpleNamespace:
        links_business = SimpleNamespace(
            links=SimpleNamespace(create_or_update_link=Mock(return_value=123)),
            link_updated=SimpleNamespace(emit=Mock()),
            invalidate_cache=Mock(),
        )
        link_operations = SimpleNamespace(emit_top_panels_changed=Mock())
        links_table_controller = SimpleNamespace(reload=Mock())
        main = SimpleNamespace(
            database_controller=SimpleNamespace(db=Mock()),
            links_business=links_business,
            link_operations=link_operations,
            links_table_controller=links_table_controller,
            get_current_category_id=Mock(return_value=current_category_id),
        )
        return main

    def test_redo_backfills_missing_category_id_from_main_window(self, qapp_mock: Mock) -> None:
        qapp_mock.instance.return_value = None
        main = self._build_main(current_category_id=77)
        cmd = SaveLinkCmd(
            new_data={"name": "Example", "url": "https://example.com", "type": "web"},
            old_data=None,
            main_window=main,
        )

        cmd.redo()

        payload = main.links_business.links.create_or_update_link.call_args.args[0]
        self.assertEqual(payload["category_id"], 77)
        self.assertEqual(cmd.new_data["category_id"], 77)
        main.links_table_controller.reload.assert_called_once_with(77)

    @patch("app.controllers.ui.undo.commands_links.DialogManager.show_error")
    def test_redo_shows_error_and_skips_save_when_category_missing_everywhere(
        self, show_error_mock: Mock, qapp_mock: Mock
    ) -> None:
        qapp_mock.instance.return_value = None
        main = self._build_main(current_category_id=None)
        cmd = SaveLinkCmd(
            new_data={"name": "Example", "url": "https://example.com", "type": "web"},
            old_data=None,
            main_window=main,
        )

        cmd.redo()

        main.links_business.links.create_or_update_link.assert_not_called()
        main.links_table_controller.reload.assert_not_called()
        show_error_mock.assert_called_once()


class TestBatchSaveLinksCmdCategoryRecovery(unittest.TestCase):
    def _build_main(self, *, current_category_id: int | None = 88) -> SimpleNamespace:
        links_business = SimpleNamespace(
            links=SimpleNamespace(batch_create_or_update_links=Mock(return_value=[1, 2])),
            batch_updated=SimpleNamespace(emit=Mock()),
            invalidate_cache=Mock(),
        )
        link_operations = SimpleNamespace(emit_top_panels_changed=Mock())
        links_table_controller = SimpleNamespace(reload=Mock())
        return SimpleNamespace(
            database_controller=SimpleNamespace(db=Mock()),
            links_business=links_business,
            link_operations=link_operations,
            links_table_controller=links_table_controller,
            get_current_category_id=Mock(return_value=current_category_id),
        )

    def test_redo_backfills_missing_categories_for_batch(self) -> None:
        main = self._build_main(current_category_id=88)
        cmd = BatchSaveLinksCmd(
            links_data=[
                {"name": "One", "url": "https://one.example", "type": "web"},
                {"name": "Two", "url": "https://two.example", "type": "web"},
            ],
            _old_link_data=None,
            main_window=main,
        )

        cmd.redo()

        payloads = main.links_business.links.batch_create_or_update_links.call_args.args[0]
        self.assertEqual([payload["category_id"] for payload in payloads], [88, 88])
        main.links_table_controller.reload.assert_called_once_with(88)

    @patch("app.controllers.ui.links.icon_enrichment_service.enqueue_link_icon_enrichment")
    def test_redo_resolves_saved_ids_before_icon_enrichment(
        self,
        enqueue_icon_mock: Mock,
    ) -> None:
        main = self._build_main(current_category_id=88)
        main.links_business.links.batch_create_or_update_links.return_value = [42]
        main.links_business.links.resolve_link_id = Mock(side_effect=[7, 42])
        cmd = BatchSaveLinksCmd(
            links_data=[
                {
                    "name": "Existing",
                    "url": "https://one.example",
                    "type": "web",
                    "category_id": 88,
                },
                {
                    "name": "New",
                    "url": "https://two.example",
                    "type": "web",
                    "category_id": 88,
                },
            ],
            _old_link_data=None,
            main_window=main,
        )

        cmd.redo()

        self.assertEqual(cmd.created_ids, [42])
        self.assertEqual(cmd.links_data[0]["id"], 7)
        self.assertEqual(cmd.links_data[1]["id"], 42)
        first_payload = enqueue_icon_mock.call_args_list[0].args[1]
        second_payload = enqueue_icon_mock.call_args_list[1].args[1]
        self.assertEqual(first_payload["id"], 7)
        self.assertEqual(second_payload["id"], 42)

    @patch("app.controllers.ui.undo.commands_links.DialogManager.show_error")
    def test_redo_shows_error_and_skips_batch_when_category_missing_everywhere(
        self, show_error_mock: Mock
    ) -> None:
        main = self._build_main(current_category_id=None)
        cmd = BatchSaveLinksCmd(
            links_data=[{"name": "One", "url": "https://one.example", "type": "web"}],
            _old_link_data=None,
            main_window=main,
        )

        cmd.redo()

        main.links_business.links.batch_create_or_update_links.assert_not_called()
        main.links_table_controller.reload.assert_not_called()
        show_error_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
