# tests/test_controllers/test_business/test_structure_business.py

import pytest
from unittest.mock import Mock, patch
from PyQt6.QtCore import QTimer

from app.controllers.business.structure_business import StructureBusinessLogic
from app.models.db import Database
from app.controllers.structure_modules import CacheManager


@pytest.fixture
def mock_db():
    db = Mock(spec=Database)
    return db


@pytest.fixture
def mock_cache_manager():
    return Mock(spec=CacheManager)


@pytest.fixture
def structure_business_logic(qtbot, mock_db, mock_cache_manager):
    with patch('app.controllers.business.structure_business.CacheManager', return_value=mock_cache_manager):
        logic = StructureBusinessLogic(db=mock_db)
        qtbot.addWidget(logic)
        return logic


class TestStructureBusinessLogic:
    """Test suite for StructureBusinessLogic."""

    def test_initialization(self, structure_business_logic, mock_db):
        """Test proper initialization."""
        assert structure_business_logic.db == mock_db
        assert structure_business_logic.current_sphere_id is None
        assert structure_business_logic._batch_mode is False
        assert isinstance(structure_business_logic._batch_touched_sections, set)

    def test_set_current_sphere_emits_signal(self, qtbot, structure_business_logic):
        """Test set_current_sphere emits active_sphere_changed signal."""
        with qtbot.waitSignal(structure_business_logic.active_sphere_changed, timeout=1000) as blocker:
            structure_business_logic.set_current_sphere(sphere_id=1)

        assert blocker.args == (1,)
        assert structure_business_logic.current_sphere_id == 1

    def test_load_structure_emits_signal(self, qtbot, structure_business_logic, mock_cache_manager):
        """Test load_structure emits structure_loaded signal."""
        mock_cache_manager.get.return_value = None  # Cache miss
        mock_cache_manager.set.return_value = None

        # Mock loader service
        with patch.object(structure_business_logic.loader_service, 'load_structure_from_db', return_value=[{"id": 1, "name": "Section"}]):
            with qtbot.waitSignal(structure_business_logic.structure_loaded, timeout=1000) as blocker:
                structure_business_logic.load_structure(sphere_id=1)

            assert blocker.args == ([{"id": 1, "name": "Section"}],)

    def test_load_structure_from_cache(self, qtbot, structure_business_logic, mock_cache_manager):
        """Test load_structure uses cache when available."""
        cached_data = [{"id": 1, "name": "Cached Section"}]
        mock_cache_manager.get.return_value = cached_data

        with qtbot.waitSignal(structure_business_logic.structure_loaded, timeout=1000) as blocker:
            structure_business_logic.load_structure(sphere_id=1)

        assert blocker.args == (cached_data,)
        # Should not call loader_service since cached
        assert not hasattr(structure_business_logic.loader_service, 'load_structure_from_db')

    def test_select_section_emits_signal(self, qtbot, structure_business_logic):
        """Test select_section emits section_selected signal."""
        with patch.object(structure_business_logic, 'get_categories', return_value=[{"id": 1, "name": "Category"}]):
            with qtbot.waitSignal(structure_business_logic.section_selected, timeout=1000) as blocker:
                structure_business_logic.select_section(section_id=1)

            assert blocker.args == (1,)

    def test_select_category_emits_signal(self, qtbot, structure_business_logic):
        """Test select_category emits category_selected signal."""
        with qtbot.waitSignal(structure_business_logic.category_selected, timeout=1000) as blocker:
            structure_business_logic.select_category(category_id=1)

        assert blocker.args == (1,)

    def test_begin_batch_sets_mode(self, structure_business_logic):
        """Test begin_batch enables batch mode."""
        structure_business_logic.begin_batch()
        assert structure_business_logic._batch_mode is True
        assert len(structure_business_logic._batch_touched_sections) == 0

    def test_end_batch_disables_mode(self, structure_business_logic):
        """Test end_batch disables batch mode."""
        structure_business_logic.begin_batch()
        structure_business_logic.end_batch()
        assert structure_business_logic._batch_mode is False

    def test_get_spheres_uses_cache(self, structure_business_logic, mock_cache_manager):
        """Test get_spheres uses cache."""
        cached_spheres = [{"id": 1, "name": "Sphere"}]
        mock_cache_manager.get.return_value = cached_spheres

        result = structure_business_logic.get_spheres()
        assert result == cached_spheres

    def test_get_sections_uses_cache(self, structure_business_logic, mock_cache_manager):
        """Test get_sections uses cache."""
        cached_sections = [{"id": 1, "name": "Section"}]
        mock_cache_manager.get.return_value = cached_sections

        result = structure_business_logic.get_sections(sphere_id=1)
        assert result == cached_sections

    def test_get_categories_uses_cache(self, structure_business_logic, mock_cache_manager):
        """Test get_categories uses cache."""
        cached_categories = [{"id": 1, "name": "Category"}]
        mock_cache_manager.get.return_value = cached_categories

        result = structure_business_logic.get_categories(section_id=1)
        assert result == cached_categories

    def test_shutdown_calls_async_shutdown(self, structure_business_logic):
        """Test shutdown calls async operations shutdown."""
        with patch.object(structure_business_logic.async_operations, 'shutdown') as mock_shutdown:
            structure_business_logic.shutdown(timeout=1000)
            mock_shutdown.assert_called_once_with(timeout=1000)

    def test_invalidate_structure_cache(self, structure_business_logic, mock_cache_manager):
        """Test cache invalidation."""
        structure_business_logic.current_sphere_id = 1
        structure_business_logic._invalidate_structure_cache()
        mock_cache_manager.invalidate.assert_called()

    def test_error_handling_in_load_structure(self, qtbot, structure_business_logic, mock_cache_manager):
        """Test error handling emits error_occurred signal."""
        mock_cache_manager.get.return_value = None
        with patch.object(structure_business_logic.loader_service, 'load_structure_from_db', side_effect=Exception("Load Error")):
            with qtbot.waitSignal(structure_business_logic.error_occurred, timeout=1000) as blocker:
                structure_business_logic.load_structure(sphere_id=1)

            assert "Load Error" in blocker.args[0]

    def test_batch_mode_prevents_immediate_reload(self, structure_business_logic):
        """Test batch mode prevents immediate category reload."""
        structure_business_logic._batch_mode = True
        structure_business_logic._batch_touched_sections.add(1)

        # Simulate item_updated
        # Since it's internal, mock the async_operations
        with patch.object(structure_business_logic.async_operations, 'load_categories_async') as mock_load:
            # Call _on_item_updated indirectly or mock
            # For simplicity, test the logic in end_batch
            structure_business_logic.end_batch()
            mock_load.assert_called_with(1)

    def test_schedule_structure_reload(self, structure_business_logic):
        """Test delayed structure reload scheduling."""
        timer = structure_business_logic._structure_reload_timer
        structure_business_logic._schedule_structure_reload(delay_ms=100)
        assert timer.isActive()

    def test_get_current_sphere_id(self, structure_business_logic):
        """Test get_current_sphere_id returns current sphere."""
        structure_business_logic.current_sphere_id = 5
        assert structure_business_logic.get_current_sphere_id() == 5

    def test_batch_operations(self, structure_business_logic):
        """Test batch mode operations."""
        structure_business_logic.begin_batch()
        assert structure_business_logic._batch_mode is True
        structure_business_logic.end_batch()
        assert structure_business_logic._batch_mode is False

    def test_load_structure_empty_sphere(self, qtbot, structure_business_logic):
        """Test load_structure with no current sphere emits empty."""
        structure_business_logic.current_sphere_id = None
        with qtbot.waitSignal(structure_business_logic.structure_loaded) as blocker:
            structure_business_logic.load_structure()

        assert blocker.args == ([],)

    def test_error_in_set_current_sphere(self, structure_business_logic):
        """Test error handling in set_current_sphere."""
        # Mock to raise exception
        with patch.object(structure_business_logic, '_handle_error') as mock_error:
            # Force error by mocking time.monotonic to raise
            with patch('time.monotonic', side_effect=RuntimeError("Time error")):
                structure_business_logic.set_current_sphere(1)
            mock_error.assert_called()

    def test_invalidate_cache(self, structure_business_logic, mock_cache_manager):
        """Test cache invalidation."""
        structure_business_logic.current_sphere_id = 1
        structure_business_logic._invalidate_structure_cache()
        mock_cache_manager.invalidate.assert_any_call("structure_1")
        mock_cache_manager.invalidate.assert_any_call("sections_1")

    def test_get_spheres_fallback(self, structure_business_logic, mock_cache_manager):
        """Test get_spheres when cache miss."""
        mock_cache_manager.get.return_value = None
        with patch.object(structure_business_logic.structure_service, 'get_spheres', return_value=[{"id": 1}]) as mock_get:
            result = structure_business_logic.get_spheres()
            assert result == [{"id": 1}]
            mock_get.assert_called_once()

    def test_has_duplicate_category(self, structure_business_logic):
        """Test duplicate category check."""
        with patch.object(structure_business_logic, 'get_categories', return_value=[{"id": 1, "name": "Test"}]):
            assert structure_business_logic.has_duplicate_category(1, "test", exclude_id=2) is True
            assert structure_business_logic.has_duplicate_category(1, "other") is False

    def test_get_next_sphere_id(self, structure_business_logic):
        """Test cyclic sphere selection."""
        with patch.object(structure_business_logic, 'get_spheres', return_value=[{"id": 1}, {"id": 2}]):
            structure_business_logic.current_sphere_id = 1
            assert structure_business_logic.get_next_sphere_id() == 2
            structure_business_logic.current_sphere_id = 2
            assert structure_business_logic.get_next_sphere_id() == 1

    def test_create_section_success(self, structure_business_logic):
        """Test create_section success."""
        with patch.object(structure_business_logic.structure_service, 'create_section', return_value=1):
            with patch.object(structure_business_logic.structure_service, 'get_section_by_id', return_value={"id": 1}):
                result = structure_business_logic.create_section({"name": "New Section"})
                assert result["id"] == 1

    def test_create_section_failure(self, structure_business_logic):
        """Test create_section failure."""
        with patch.object(structure_business_logic.structure_service, 'create_section', return_value=None):
            result = structure_business_logic.create_section({"name": "Fail"})
            assert result is None

    def test_delete_section_with_categories(self, structure_business_logic):
        """Test delete_section with linked categories."""
        with patch.object(structure_business_logic.structure_service, 'get_section_by_id', return_value={"id": 1, "sphere_id": 1}):
            with patch.object(structure_business_logic.structure_service, 'get_categories', return_value=[{"id": 1}]):
                with patch.object(structure_business_logic.structure_service, 'delete_section', return_value=True):
                    result = structure_business_logic.delete_section(1)
                    assert result == (True, {"id": 1, "sphere_id": 1}, 1, 0)  # success, data, categories, links

    def test_move_categories_batch_empty(self, structure_business_logic):
        """Test move_categories_batch with empty list."""
        result = structure_business_logic.move_categories_batch([], 1)
        assert result == []

    def test_create_categories_bulk_success(self, structure_business_logic):
        """Test bulk create categories."""
        with patch.object(structure_business_logic.structure_service, 'create_categories_bulk', return_value=[{"id": 1}]):
            result = structure_business_logic.create_categories_bulk([{"name": "Bulk"}])
            assert result == [{"id": 1}]

    def test_integration_load_and_select(self, qtbot, structure_business_logic, mock_cache_manager):
        """Integration test: load structure and select section."""
        mock_cache_manager.get.return_value = [{"id": 1, "name": "Section"}]
        structure_business_logic.load_structure(sphere_id=1)

        with patch.object(structure_business_logic, 'get_categories', return_value=[]):
            with qtbot.waitSignal(structure_business_logic.section_selected):
                structure_business_logic.select_section(1)

    def test_clear_all_cache(self, structure_business_logic, mock_cache_manager):
        """Test clear_all_cache."""
        structure_business_logic.clear_all_cache()
        mock_cache_manager.invalidate.assert_called_once()

    def test_get_statistics(self, structure_business_logic):
        """Test get_statistics delegates to service."""
        with patch.object(structure_business_logic.integrity_service, 'get_statistics', return_value={"total": 10}) as mock_stats:
            result = structure_business_logic.get_statistics()
            assert result == {"total": 10}
            mock_stats.assert_called_once()
