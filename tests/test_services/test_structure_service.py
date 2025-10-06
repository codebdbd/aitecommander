"""
Тесты для StructureService.

✅ НОВЫЙ ФАЙЛ: Покрытие основных сценариев.
"""

from unittest.mock import Mock, patch

import pytest

from app.services import StructureService


@pytest.fixture
def mock_db():
    """Создаёт mock Database."""
    db = Mock()
    db.spheres = Mock()
    db.sections = Mock()
    db.categories = Mock()
    db.links = Mock()
    db.transaction = Mock()
    db.get_full_structure = Mock(return_value=[])
    db.export_category_tree = Mock(return_value={})
    db.import_category_trees_bulk = Mock()
    return db


@pytest.fixture
def structure_service(mock_db):
    """Создаёт StructureService с mock DB."""
    return StructureService(mock_db)


class TestStructureServiceRead:
    """Тесты операций чтения."""

    def test_get_spheres_delegates_to_model(self, structure_service):
        """get_spheres() делегирует в модель."""
        # Arrange
        structure_service._model.get_spheres = Mock(return_value=[{"id": 1}])

        # Act
        result = structure_service.get_spheres()

        # Assert
        structure_service._model.get_spheres.assert_called_once()
        assert result == [{"id": 1}]

    def test_get_categories_delegates_to_model(self, structure_service):
        """get_categories() делегирует в модель."""
        # Arrange
        structure_service._model.get_categories = Mock(return_value=[{"id": 1}])

        # Act
        result = structure_service.get_categories(section_id=1)

        # Assert
        structure_service._model.get_categories.assert_called_once_with(1)
        assert result == [{"id": 1}]


class TestStructureServiceMutations:
    """Тесты операций изменения."""

    def test_create_section_uses_unit_of_work(self, structure_service, mock_db):
        """create_section() использует unit_of_work."""
        # Arrange
        structure_service._model.create_section = Mock(return_value=1)
        mock_db.transaction = Mock()
        mock_db.transaction.return_value.__enter__ = Mock()
        mock_db.transaction.return_value.__exit__ = Mock()

        # Act
        result = structure_service.create_section({"name": "Test"})

        # Assert
        structure_service._model.create_section.assert_called_once_with({"name": "Test"})
        assert result == 1

    def test_update_category_no_unit_of_work(self, structure_service):
        """update_category() НЕ использует unit_of_work (модель сама управляет транзакцией)."""
        # Arrange
        structure_service._model.update_category = Mock(return_value=True)

        # Act
        result = structure_service.update_category(1, {"name": "Updated"})

        # Assert
        structure_service._model.update_category.assert_called_once_with(1, {"name": "Updated"})
        assert result is True


class TestStructureServiceBatch:
    """Тесты batch операций."""

    def test_create_categories_bulk_delegates_to_model(self, structure_service):
        """create_categories_bulk() делегирует в модель."""
        # Arrange
        items = [{"name": "Cat1", "section_id": 1}]
        structure_service._model.create_categories_bulk = Mock(return_value=[{"id": 1}])

        # Act
        result = structure_service.create_categories_bulk(items)

        # Assert
        structure_service._model.create_categories_bulk.assert_called_once_with(items)
        assert result == [{"id": 1}]

    def test_delete_categories_bulk_delegates_to_db(self, structure_service, mock_db):
        """delete_categories_bulk() делегирует в db.categories."""
        # Arrange
        mock_db.categories.delete_categories_bulk = Mock(return_value=3)

        # Act
        result = structure_service.delete_categories_bulk([1, 2, 3])

        # Assert
        mock_db.categories.delete_categories_bulk.assert_called_once_with([1, 2, 3])
        assert result == 3


class TestStructureServiceImportExport:
    """Тесты импорта/экспорта."""

    def test_export_full_structure_delegates_to_db(self, structure_service, mock_db):
        """export_full_structure() делегирует в db."""
        # Arrange
        mock_db.export_full_structure = Mock(return_value={"spheres": []})

        # Act
        result = structure_service.export_full_structure()

        # Assert
        mock_db.export_full_structure.assert_called_once()
        assert result == {"spheres": []}

    def test_import_category_trees_bulk_delegates_to_db(self, structure_service, mock_db):
        """import_category_trees_bulk() делегирует в db."""
        # Arrange
        trees = [{"category": {"name": "Test"}, "links": []}]

        # Act
        structure_service.import_category_trees_bulk(trees)

        # Assert
        mock_db.import_category_trees_bulk.assert_called_once_with(trees)


class TestEdgeCases:
    """Тесты граничных случаев."""

    def test_create_categories_bulk_with_empty_list(self, structure_service):
        """create_categories_bulk() обрабатывает пустой список."""
        # Arrange
        structure_service._model.create_categories_bulk = Mock(return_value=[])

        # Act
        result = structure_service.create_categories_bulk([])

        # Assert
        assert result == []

    def test_count_links_by_categories_with_empty_list(self, structure_service):
        """count_links_by_categories() обрабатывает пустой список."""
        # Arrange
        structure_service._model.count_links_by_categories = Mock(return_value={})

        # Act
        result = structure_service.count_links_by_categories([])

        # Assert
        structure_service._model.count_links_by_categories.assert_called_once_with([])
        assert result == {}
