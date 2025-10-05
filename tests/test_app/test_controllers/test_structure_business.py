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
def structure_business(qapp, mock_db, mock_structure_service, mock_cache_manager):
    """Create StructureBusinessLogic instance with mocks."""
    async_service = Mock()
    cache_service = Mock()
    crud_service = Mock()
    validation_facade = Mock()

    with patch('app.controllers.business.structure_business.StructureService', return_value=mock_structure_service), \
         patch('app.controllers.business.structure_business.CacheManager', return_value=mock_cache_manager), \
         patch('app.controllers.business.structure_business.StructureAsyncService', return_value=async_service), \
         patch('app.controllers.business.structure_business.StructureCacheService', return_value=cache_service), \
         patch('app.controllers.business.structure_business.StructureCrudService', return_value=crud_service), \
         patch('app.controllers.business.structure_business.StructureValidationService', return_value=validation_facade), \
         patch('app.controllers.business.structure_business.ExportService'), \
         patch('app.controllers.business.structure_business.ImportService'), \
         patch('app.controllers.business.structure_business.IntegrityService'), \
         patch('app.controllers.business.structure_business.LoaderService'), \
         patch('app.controllers.business.structure_business.SelectionService'), \
         patch('app.controllers.business.structure_business.ValidationService'), \
         patch('app.controllers.business.structure_business.UtilityService'):
        business = StructureBusinessLogic(mock_db)
        business.async_service = async_service
        business.cache_service = cache_service
        business.crud_service = crud_service
        business.validation_facade = validation_facade
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

        assert blocker.args == [1]
        assert structure_business.current_sphere_id == 1

    def test_load_structure_cached(self, qtbot, structure_business):
        """Test loading structure delegates to cache service."""
        payload = [{"id": 1, "name": "Section 1"}]

        def emit_payload(sphere_id):
            structure_business.structure_loaded.emit(payload)

        structure_business.cache_service.load_structure.side_effect = emit_payload

        with qtbot.wait_signal(structure_business.structure_loaded) as blocker:
            structure_business.load_structure(1)

        assert blocker.args == [payload]
        structure_business.cache_service.load_structure.assert_called_with(1)

    def test_load_structure_without_argument(self, qtbot, structure_business):
        """Test loading structure uses current sphere when argument omitted."""
        payload = [{"id": 2, "name": "Section 2"}]

        def emit_payload(sphere_id):
            structure_business.structure_loaded.emit(payload)

        structure_business.cache_service.load_structure.side_effect = emit_payload
        structure_business.current_sphere_id = 2

        with qtbot.wait_signal(structure_business.structure_loaded) as blocker:
            structure_business.load_structure()

        assert blocker.args == [payload]
        structure_business.cache_service.load_structure.assert_called_with(2)

    def test_create_section_success(self, structure_business, mock_structure_service):
        """Test successful section creation delegates to CRUD service."""
        data = {"name": "New Section", "sphere_id": 1}
        expected = {"id": 42, "name": "New Section", "sphere_id": 1}
        structure_business.crud_service.create_section.return_value = expected

        result = structure_business.create_section(data)

        structure_business.crud_service.create_section.assert_called_once_with(data)
        assert result == expected

    def test_create_section_failure(self, structure_business):
        """Test section creation failure propagates None."""
        data = {"name": "New Section"}
        structure_business.crud_service.create_section.return_value = None

        result = structure_business.create_section(data)

        assert result is None
        structure_business.crud_service.create_section.assert_called_once_with(data)

    def test_update_section_success(self, structure_business):
        """Test successful section update delegates to CRUD service."""
        data = {"name": "Updated Section"}
        expected = {"id": 1, "name": "Updated Section", "sphere_id": 1}
        structure_business.crud_service.update_section.return_value = expected

        result = structure_business.update_section(1, data)

        structure_business.crud_service.update_section.assert_called_once_with(1, data)
        assert result == expected

    def test_delete_section_success(self, structure_business):
        """Test successful section deletion delegates to CRUD service."""
        expected = (True, {"id": 1}, 0, 0)
        structure_business.crud_service.delete_section.return_value = expected

        result = structure_business.delete_section(1)

        structure_business.crud_service.delete_section.assert_called_once_with(1)
        assert result == expected

    def test_get_spheres_cached(self, structure_business):
        """Test getting spheres delegates to cache service."""
        cached_spheres = [{"id": 1, "name": "Sphere 1"}]
        structure_business.cache_service.get_spheres.return_value = cached_spheres

        result = structure_business.get_spheres()

        assert result == cached_spheres
        structure_business.cache_service.get_spheres.assert_called_once()

    def test_get_sections_cached(self, structure_business):
        """Test getting sections delegates to cache service."""
        cached_sections = [{"id": 1, "name": "Section 1"}]
        structure_business.cache_service.get_sections.return_value = cached_sections

        result = structure_business.get_sections(1)

        assert result == cached_sections
        structure_business.cache_service.get_sections.assert_called_once_with(1)

    def test_get_categories_cached(self, structure_business):
        """Test getting categories delegates to cache service."""
        cached_categories = [{"id": 1, "name": "Category 1"}]
        structure_business.cache_service.get_categories.return_value = cached_categories

        result = structure_business.get_categories(1)

        assert result == cached_categories
        structure_business.cache_service.get_categories.assert_called_once_with(1)

    def test_select_section(self, qtbot, structure_business):
        """Test section selection."""
        with patch.object(structure_business, 'get_categories', return_value=[{"id": 1}]) as mock_get_cat:
            with qtbot.wait_signal(structure_business.section_selected) as blocker:
                structure_business.select_section(1)

        assert blocker.args == [1]
        mock_get_cat.assert_called_with(1)

    def test_select_category(self, qtbot, structure_business):
        """Test category selection."""
        with qtbot.wait_signal(structure_business.category_selected) as blocker:
            structure_business.select_category(1)

        assert blocker.args == [1]

    def test_get_links_delegates_to_validation_facade(self, structure_business):
        """Ensure get_links uses validation facade."""
        structure_business.validation_facade.get_links.return_value = [{'id': 1}]

        result = structure_business.get_links(5)

        structure_business.validation_facade.get_links.assert_called_once_with(5)
        assert result == [{'id': 1}]

    def test_get_section_data_delegates_to_validation_facade(self, structure_business):
        """Ensure get_section_data uses validation facade."""
        payload = {'id': 7}
        structure_business.validation_facade.get_section_data.return_value = payload

        result = structure_business.get_section_data(7)

        structure_business.validation_facade.get_section_data.assert_called_once_with(7)
        assert result == payload

    def test_get_item_for_editing_delegates_to_validation_facade(self, structure_business):
        """Ensure get_item_for_editing uses validation facade."""
        payload = {'id': 9}
        structure_business.validation_facade.get_item_for_editing.return_value = payload

        result = structure_business.get_item_for_editing(9, 'category')

        structure_business.validation_facade.get_item_for_editing.assert_called_once_with(9, 'category')
        assert result == payload

    def test_has_duplicate_category_delegates_to_validation_facade(self, structure_business):
        """Ensure duplicate check uses validation facade."""
        structure_business.validation_facade.has_duplicate_category.return_value = True

        result = structure_business.has_duplicate_category(3, 'Name', exclude_id=4)

        structure_business.validation_facade.has_duplicate_category.assert_called_once_with(3, 'Name', 4)
        assert result is True

    def test_batch_mode(self, structure_business):
        """Test batch mode operations."""
        assert not structure_business._batch_mode

        structure_business.begin_batch()
        assert structure_business._batch_mode
        assert structure_business._batch_touched_sections == set()

        structure_business.end_batch()
        assert not structure_business._batch_mode

    def test_shutdown(self, structure_business, mock_cache_manager):
        """Test shutdown calls async service and clears cache."""
        structure_business.shutdown(1000)

        structure_business.async_service.shutdown.assert_called_once_with(timeout=1000)
        mock_cache_manager.invalidate.assert_called_once()

    def test_clear_all_cache(self, structure_business, mock_cache_manager):
        """Test clearing all caches."""
        structure_business.clear_all_cache()

        mock_cache_manager.invalidate.assert_called_once()
