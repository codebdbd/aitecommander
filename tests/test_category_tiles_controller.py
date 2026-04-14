from __future__ import annotations

import logging
from unittest.mock import Mock

from app.controllers.ui.category_tiles_controller import CategoryTilesController


class _CacheManagerStub:
    def __init__(self, value):
        self._value = value

    def get(self, key):
        assert key.startswith("categories_")
        return self._value


def _make_controller(*, cache_value, force_fresh=False):
    ui_state = Mock()
    ui_state.switch_to_category_tiles.return_value = True
    business = Mock()
    business.cache_manager = _CacheManagerStub(cache_value)
    business.should_force_fresh_tiles.return_value = force_fresh
    business.get_cached_categories.return_value = []
    business.get_categories.return_value = [{"id": 1, "name": "A"}]
    return CategoryTilesController(ui_state, business), business


def test_refresh_logs_cache_optimistic_source_when_cache_exists(caplog):
    controller, _business = _make_controller(cache_value=[])

    with caplog.at_level(logging.INFO):
        controller.refresh(513)

    assert "source=cache/optimistic" in caplog.text


def test_refresh_logs_db_source_when_force_fresh_bypasses_cache(caplog):
    controller, _business = _make_controller(cache_value=[{"id": 1}], force_fresh=True)

    with caplog.at_level(logging.INFO):
        controller.refresh(513)

    assert "source=db" in caplog.text
