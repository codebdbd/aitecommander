from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.controllers.business.structure.event_service import StructureEventService


class TestStructureEventServiceCategoryRefresh(unittest.TestCase):
    def _build_service(self) -> tuple[StructureEventService, Mock, Mock]:
        owner = SimpleNamespace(
            top_panels_controller=SimpleNamespace(
                schedule_structure_refresh=Mock(),
                request_refresh=Mock(),
            ),
            cache_manager=SimpleNamespace(get=Mock(return_value=None)),
            prime_categories_cache=Mock(),
            section_selected=SimpleNamespace(emit=Mock()),
            _last_selected_section_id=None,
        )
        cache_service = Mock()
        async_service = Mock()
        logger = Mock()
        svc = StructureEventService(
            owner=owner,
            cache_service=cache_service,
            async_service=async_service,
            logger=logger,
        )
        return svc, cache_service, async_service

    def test_category_added_uses_targeted_reload_without_structure_reload(self) -> None:
        svc, cache_service, async_service = self._build_service()

        svc.on_item_added("category", 506, {"id": 1, "section_id": 506, "name": "cat"})

        cache_service.invalidate_categories_cache.assert_called_once_with(506)
        async_service.load_categories_async.assert_called_once_with(506)
        async_service.schedule_structure_reload.assert_not_called()

    def test_category_updated_uses_targeted_reload_without_structure_reload(self) -> None:
        svc, cache_service, async_service = self._build_service()

        svc.on_item_updated("category", 1, {"id": 1, "section_id": 506, "name": "cat2"})

        cache_service.invalidate_categories_cache.assert_called_once_with(506)
        async_service.load_categories_async.assert_called_once_with(506)
        async_service.schedule_structure_reload.assert_not_called()

    def test_section_added_uses_incremental_update_without_structure_reload(self) -> None:
        svc, cache_service, async_service = self._build_service()

        svc.on_item_added("section", 508, {"id": 508, "sphere_id": 3, "name": "sec"})

        cache_service.invalidate_sections_cache.assert_called_once_with(3)
        cache_service.invalidate_structure_cache.assert_called_once()
        async_service.schedule_structure_reload.assert_not_called()

    def test_category_added_uses_optimistic_refresh_when_cache_available(self) -> None:
        svc, cache_service, async_service = self._build_service()
        svc._owner.cache_manager.get.return_value = [
            {"id": 10, "section_id": 506, "name": "old", "position": 0}
        ]
        svc._owner._last_selected_section_id = 506

        svc.on_item_added("category", 506, {"id": 11, "section_id": 506, "name": "new", "position": 1})

        svc._owner.prime_categories_cache.assert_called_once()
        svc._owner.section_selected.emit.assert_called_once_with(506)
        cache_service.invalidate_categories_cache.assert_not_called()
        async_service.load_categories_async.assert_not_called()

    def test_category_updated_uses_optimistic_refresh_when_cache_available(self) -> None:
        svc, cache_service, async_service = self._build_service()
        svc._owner.cache_manager.get.return_value = [
            {"id": 1, "section_id": 506, "name": "old", "position": 0}
        ]
        svc._owner._last_selected_section_id = 506

        svc.on_item_updated("category", 1, {"id": 1, "section_id": 506, "name": "cat2", "position": 0})

        svc._owner.prime_categories_cache.assert_called_once()
        svc._owner.section_selected.emit.assert_called_once_with(506)
        cache_service.invalidate_categories_cache.assert_not_called()
        async_service.load_categories_async.assert_not_called()

    def test_section_updated_uses_incremental_update_without_structure_reload(self) -> None:
        svc, cache_service, async_service = self._build_service()

        svc.on_item_updated("section", 508, {"id": 508, "sphere_id": 3, "name": "sec2"})

        cache_service.invalidate_sections_cache.assert_called_once_with(3)
        cache_service.invalidate_structure_cache.assert_called_once()
        async_service.schedule_structure_reload.assert_not_called()

    def test_section_deleted_uses_incremental_update_without_structure_reload(self) -> None:
        svc, cache_service, async_service = self._build_service()

        svc.on_item_deleted("section", 508)

        cache_service.invalidate_structure_cache.assert_called_once()
        async_service.schedule_structure_reload.assert_not_called()

    def test_link_added_uses_targeted_refresh_without_structure_reload(self) -> None:
        svc, cache_service, async_service = self._build_service()

        svc.on_item_added("link", 0, {"id": 1, "category_id": 506, "name": "link"})

        cache_service.invalidate_categories_cache.assert_called_once_with(506)
        async_service.schedule_structure_reload.assert_not_called()

    def test_link_deleted_does_not_trigger_structure_reload(self) -> None:
        svc, _cache_service, async_service = self._build_service()

        svc.on_item_deleted("link", 123)

        async_service.schedule_structure_reload.assert_not_called()

    def test_link_batch_delete_does_not_trigger_structure_reload(self) -> None:
        svc, cache_service, async_service = self._build_service()

        svc.on_items_batch_deleted("link", [1, 2, 3])

        cache_service.invalidate_structure_cache.assert_not_called()
        async_service.schedule_structure_reload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
