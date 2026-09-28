from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.controllers.ui.structure.item_deletion_service import ItemDeletionService


class TestItemDeletionService(unittest.TestCase):
    def _build_service(self) -> tuple[ItemDeletionService, SimpleNamespace, Mock]:
        tree_manager = SimpleNamespace(_find_item_by_id=Mock(return_value=None))
        controller = SimpleNamespace(tree_manager=tree_manager)
        business = Mock()
        business.get_category_data.return_value = {"id": 101, "name": "Cat 101"}
        business.db = SimpleNamespace(
            links=SimpleNamespace(
                count_links_by_category=Mock(return_value=0),
                count_links_by_categories=Mock(return_value={}),
            ),
            sections=SimpleNamespace(
                count_nested_objects_for_section=Mock(return_value=(0, 0))
            ),
        )
        undo_stack = Mock()
        service = ItemDeletionService(
            controller=controller,
            tree=Mock(),
            business=business,
            main_window=Mock(),
            undo_stack=undo_stack,
        )
        return service, business, undo_stack

    def test_handle_delete_category_uses_business_payload_without_tree_index(self) -> None:
        service, business, _undo_stack = self._build_service()
        service._push_category_delete = Mock()  # type: ignore[method-assign]

        service.handle_delete_category(101)

        business.get_category_data.assert_called_once_with(101)
        service._push_category_delete.assert_called_once_with(  # type: ignore[attr-defined]
            {"id": 101, "name": "Cat 101"}
        )

    def test_handle_delete_category_ignores_invalid_ids(self) -> None:
        service, business, _undo_stack = self._build_service()
        service._push_category_delete = Mock()  # type: ignore[method-assign]

        service.handle_delete_category("bad")
        service.handle_delete_category(0)

        business.get_category_data.assert_not_called()
        service._push_category_delete.assert_not_called()  # type: ignore[attr-defined]


    def test_delete_section_confirms_even_when_links_count_is_zero(self) -> None:
        service, business, _undo_stack = self._build_service()
        business.get_section_data.return_value = {"id": 10, "name": "Sec 10"}
        service._confirm_section_deletion = Mock(return_value=True)  # type: ignore[method-assign]
        service._push_section_delete = Mock()  # type: ignore[method-assign]

        service._delete_section(10)

        business.get_section_data.assert_called_once_with(10)
        service._confirm_section_deletion.assert_called_once_with(
            {"id": 10, "name": "Sec 10"}, 0, 0
        )
        service._push_section_delete.assert_called_once_with(
            {"id": 10, "name": "Sec 10"}
        )

    def test_delete_section_cancelled_by_user(self) -> None:
        service, business, _undo_stack = self._build_service()
        business.get_section_data.return_value = {"id": 10, "name": "Sec 10"}
        service._confirm_section_deletion = Mock(return_value=False)  # type: ignore[method-assign]
        service._push_section_delete = Mock()  # type: ignore[method-assign]

        service._delete_section(10)

        service._confirm_section_deletion.assert_called_once()
        service._push_section_delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
