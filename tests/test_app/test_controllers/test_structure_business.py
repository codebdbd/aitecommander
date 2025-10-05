"""Tests for StructureBusinessLogic."""

import pytest
from unittest.mock import Mock, patch
from PyQt6.QtCore import QObject

from app.controllers.business.structure_business import StructureBusinessLogic
from app.models.db import Database


@pytest.fixture
def mock_db():
    """Mock database."""
    return Mock(spec=Database)


@pytest.fixture
def mock_structure_service():
    """Mock StructureService."""
    return Mock()


@pytest.fixture
def mock_cache_manager():
    """Mock CacheManager."""
    return Mock()


@pytest.fixture
def structure_business(qt_app, mock_db, mock_structure_service, mock_cache_manager):
    """Create StructureBusinessLogic instance with mocks."""
    with patch('app.controllers.business.structure_business.StructureService', return_value=mock_structure_service), \
         patch('app.controllers.business.structure_business.CacheManager', return_value=mock_cache_manager), \
         patch('app.controllers.business.structure_business.AsyncOperations'), \
         patch('app.controllers.business.structure_business.AsyncSignalHandlers'), \
         patch('app.controllers.business.structure_business.ExportService'), \
         patch('app.controllers.business.structure_business.ImportService'), \
         patch('app.controllers.business.structure_business.IntegrityService'), \
         patch('app.controllers.business.structure_business.LoaderService'), \
         patch('app.controllers.business.structure_business.SelectionService'), \
         patch('app.controllers.business.structure_business.ValidationService'), \
         patch('app.controllers.business.structure_business.UtilityService'):
        business = StructureBusinessLogic(mock_db)
        yield business


class TestStructureBusinessLogic:
    """Test StructureBusinessLogic."""

    def test_init(self, structure_business, mock_db, mock_structure_service):
        """Test initialization."""
        assert structure_business.db == mock_db
        assert structure_business.structure_service == mock_structure_service
        assert structure_business.current_sphere_id is None

    def test_set_current_sphere(self, qtbot, structure_business):
        """Test setting current sphere."""
        with qtbot.wait_signal(structure_business.active_sphere_changed) as blocker:
            structure_business.set_current_sphere(1)

        assert blocker.args == (1,)
        assert structure_business.current_sphere_id == 1

    def test_load_structure_cached(self, qtbot, structure_business, mock_cache_manager):
        """Test loading structure from cache."""
        cached_data = [{"id": 1, "name": "Section 1"}]
        mock_cache_manager.get.return_value = cached_data

        with qtbot.wait_signal(structure_business.structure_loaded) as blocker:
            structure_business.load_structure(1)

        assert blocker.args == (cached_data,)
        mock_cache_manager.get.assert_called_with("structure_1")

    def test_load_structure_from_db(self, qtbot, structure_business, mock_cache_manager):
        """Test loading structure from database."""
        mock_cache_manager.get.return_value = None
        db_data = [{"id": 1, "name": "Section 1"}]

        with patch.object(structure_business, '_load_structure_from_db', return_value=db_data):
            with qtbot.wait_signal(structure_business.structure_loaded) as blocker:
                structure_business.load_structure(1)

        assert blocker.args == (db_data,)
        mock_cache_manager.set.assert_called_with("structure_1", db_data)

    def test_create_section_success(self, qtbot, structure_business, mock_structure_service):
        """Test successful section creation."""
        data = {"name": "New Section", "sphere_id": 1}
        mock_structure_service.create_section.return_value = 42
        mock_structure_service.get_section_by_id.return_value = {"id": 42, "name": "New Section", "sphere_id": 1}

        with qtbot.wait_signal(structure_business.item_added) as blocker:
            result = structure_business.create_section(data)

        assert blocker.args == ("section", 1, {"id": 42, "name": "New Section", "sphere_id": 1})
        assert result == {"id": 42, "name": "New Section", "sphere_id": 1}

    def test_create_section_failure(self, structure_business, mock_structure_service):
        """Test section creation failure."""
        data = {"name": "New Section"}
        mock_structure_service.create_section.return_value = None

        result = structure_business.create_section(data)

        assert result is None

    def test_update_section_success(self, qtbot, structure_business, mock_structure_service):
        """Test successful section update."""
        data = {"name": "Updated Section"}
        mock_structure_service.update_section.return_value = True
        mock_structure_service.get_section_by_id.return_value = {"id": 1, "name": "Updated Section", "sphere_id": 1}

        with qtbot.wait_signal(structure_business.item_updated) as blocker:
            result = structure_business.update_section(1, data)

        assert blocker.args == ("section", 1, {"id": 1, "name": "Updated Section", "sphere_id": 1})
        assert result == {"id": 1, "name": "Updated Section", "sphere_id": 1}

    def test_delete_section_success(self, qtbot, structure_business, mock_structure_service):
        """Test successful section deletion."""
        mock_structure_service.get_section_by_id.return_value = {"id": 1, "name": "Section", "sphere_id": 1}
        mock_structure_service.delete_section.return_value = True

        with qtbot.wait_signal(structure_business.item_deleted) as blocker:
            success, data, cat_count, link_count = structure_business.delete_section(1)

        assert blocker.args == ("section", 1)
        assert success is True
        assert data == {"id": 1, "name": "Section", "sphere_id": 1}
        assert cat_count == 0  # Mocked as 0
        assert link_count == 0

    def test_get_spheres_cached(self, structure_business, mock_cache_manager):
        """Test getting spheres from cache."""
        cached_spheres = [{"id": 1, "name": "Sphere 1"}]
        mock_cache_manager.get.return_value = cached_spheres

        result = structure_business.get_spheres()

        assert result == cached_spheres
        mock_cache_manager.get.assert_called_with("all_spheres")

    def test_get_spheres_from_service(self, structure_business, mock_cache_manager, mock_structure_service):
        """Test getting spheres from service."""
        mock_cache_manager.get.return_value = None
        service_spheres = [{"id": 1, "name": "Sphere 1"}]
        mock_structure_service.get_spheres.return_value = service_spheres

        result = structure_business.get_spheres()

        assert result == service_spheres
        mock_cache_manager.set.assert_called_with("all_spheres", service_spheres)

    def test_get_sections_cached(self, structure_business, mock_cache_manager):
        """Test getting sections from cache."""
        cached_sections = [{"id": 1, "name": "Section 1"}]
        mock_cache_manager.get.return_value = cached_sections

        result = structure_business.get_sections(1)

        assert result == cached_sections

    def test_get_categories_cached(self, structure_business, mock_cache_manager):
        """Test getting categories from cache."""
        cached_categories = [{"id": 1, "name": "Category 1"}]
        mock_cache_manager.get.return_value = cached_categories

        result = structure_business.get_categories(1)

        assert result == cached_categories

    def test_select_section(self, qtbot, structure_business):
        """Test section selection."""
        with patch.object(structure_business, 'get_categories', return_value=[{"id": 1}]) as mock_get_cat:
            with qtbot.wait_signal(structure_business.section_selected) as blocker:
                structure_business.select_section(1)

        assert blocker.args == (1,)
        mock_get_cat.assert_called_with(1)

    def test_select_category(self, qtbot, structure_business):
        """Test category selection."""
        with qtbot.wait_signal(structure_business.category_selected) as blocker:
            structure_business.select_category(1)

        assert blocker.args == (1,)

    def test_batch_mode(self, structure_business):
        """Test batch mode operations."""
        assert not structure_business._batch_mode

        structure_business.begin_batch()
        assert structure_business._batch_mode
        assert structure_business._batch_touched_sections == set()

        structure_business.end_batch()
        assert not structure_business._batch_mode

    def test_shutdown(self, structure_business, mock_cache_manager):
        """Test shutdown."""
        with patch.object(structure_business, '_structure_reload_timer', Mock()) as mock_timer:
            mock_timer.isActive.return_value = True

            structure_business.shutdown(1000)

            mock_timer.stop.assert_called_once()
            mock_cache_manager.invalidate.assert_called_once()

    def test_clear_all_cache(self, structure_business, mock_cache_manager):
        """Test clearing all caches."""
        structure_business.clear_all_cache()

        mock_cache_manager.invalidate.assert_called_once()
