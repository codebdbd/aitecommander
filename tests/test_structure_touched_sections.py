from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.controllers.business.structure.crud_service import MoveCategoriesBatchResult
from app.controllers.business.structure.event_service import StructureEventService
from app.controllers.business.structure_business import StructureBusinessLogic


def _make_logic():
    logic = StructureBusinessLogic.__new__(StructureBusinessLogic)
    logic.logger = Mock()
    logic.crud_service = SimpleNamespace()
    logic.event_service = SimpleNamespace(replace_touched_sections=Mock())
    return logic


def test_move_categories_batch_forwards_touched_sections():
    logic = _make_logic()
    logic.crud_service.move_categories_batch = Mock(
        return_value=MoveCategoriesBatchResult(
            moved_ids=[10, 11],
            touched_sections={1, 2},
        )
    )

    result = logic.move_categories_batch([10, 11], target_section_id=5)

    assert result == [10, 11]
    logic.event_service.replace_touched_sections.assert_called_once_with({1, 2})


def test_move_categories_batch_handles_plain_list_return():
    logic = _make_logic()
    logic.crud_service.move_categories_batch = Mock(return_value=[5])

    result = logic.move_categories_batch([5], target_section_id=2)

    assert result == [5]
    logic.event_service.replace_touched_sections.assert_not_called()


@pytest.fixture
def event_service():
    owner = Mock()
    cache_service = Mock()
    async_service = Mock()
    logger = Mock()
    return StructureEventService(owner, cache_service, async_service, logger)


def test_replace_touched_sections_in_batch(event_service):
    event_service.begin_batch()
    event_service.replace_touched_sections({7, 8})

    event_service.end_batch()

    event_service._async_service.load_categories_async.assert_any_call(7)
    event_service._async_service.load_categories_async.assert_any_call(8)
    event_service._cache_service.invalidate_structure_cache.assert_called_once()
    event_service._async_service.schedule_structure_reload.assert_not_called()


def test_replace_touched_sections_outside_batch(event_service):
    event_service.replace_touched_sections({3})

    event_service._async_service.load_categories_async.assert_called_once_with(3)
    event_service._cache_service.invalidate_structure_cache.assert_not_called()
