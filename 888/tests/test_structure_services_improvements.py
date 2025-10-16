"""
Тесты для проверки улучшений в structure_services после аудита PyQt6.

Проверяет:
1. Ужесточенную обработку исключений
2. Устранение дублирования кода
3. Унифицированное логирование
4. Оптимизированные циклы
"""

import logging
import pytest
from unittest.mock import Mock, patch

from app.controllers.structure_services.exporter import ExportService
from app.controllers.structure_services.importer import ImportService
from app.controllers.structure_services.integrity import IntegrityService
from app.controllers.structure_services.loader import LoaderService
from app.controllers.structure_services.selection import SelectionService
from app.controllers.structure_services.utilities import UtilityService
from app.controllers.structure_services.validation import ValidationService


class TestExceptionHandling:
    """Тесты ужесточенной обработки исключений."""

    def test_exporter_handles_validation_errors(self):
        """Тест обработки ошибок валидации в ExportService."""
        service = ExportService()
        
        # Mock функции, которые вызывают ValueError
        def mock_get_spheres():
            raise ValueError("Ошибка валидации данных")
        
        mock_logger = Mock()
        
        result = service.export_structure_data(
            current_sphere_id=1,
            get_spheres=mock_get_spheres,
            get_sections=Mock(return_value=[]),
            get_categories=Mock(return_value=[]),
            logger=mock_logger
        )
        
        # Проверяем, что ошибка валидации обработана корректно
        assert result["error"] == "Ошибка валидации данных"
        mock_logger.error.assert_called_once()
        assert "валидации данных" in mock_logger.error.call_args[0][0]

    def test_exporter_reraises_critical_errors(self):
        """Тест проброса критических ошибок в ExportService."""
        service = ExportService()
        
        # Mock функции, которые вызывают критическую ошибку
        def mock_get_spheres():
            raise RuntimeError("Критическая ошибка системы")
        
        mock_logger = Mock()
        
        with pytest.raises(RuntimeError, match="Критическая ошибка системы"):
            service.export_structure_data(
                current_sphere_id=1,
                get_spheres=mock_get_spheres,
                get_sections=Mock(return_value=[]),
                get_categories=Mock(return_value=[]),
                logger=mock_logger
            )
        
        # Проверяем, что критическая ошибка залогирована через exception()
        mock_logger.exception.assert_called_once()

    def test_selection_service_handles_validation_errors(self):
        """Тест обработки ошибок валидации в SelectionService."""
        service = SelectionService()
        mock_model = Mock()
        mock_model.get_spheres.side_effect = KeyError("Отсутствует ключ")
        mock_logger = Mock()
        
        result = service.get_spheres(mock_model, mock_logger)
        
        assert result == []
        mock_logger.error.assert_called_once()
        assert "валидации данных" in mock_logger.error.call_args[0][0]


class TestCodeDeduplication:
    """Тесты устранения дублирования кода."""

    def test_get_first_category_id_is_alias(self):
        """Тест что get_first_category_id является алиасом для get_target_section_id."""
        service = UtilityService()
        
        # Mock зависимости
        mock_get_sections = Mock(return_value=[{"id": 1}])
        mock_get_categories = Mock(return_value=[{"id": 10}])
        mock_cache_get = Mock(return_value=None)
        mock_cache_set = Mock()
        
        # Вызываем оба метода с одинаковыми параметрами
        result1 = service.get_target_section_id(
            current_sphere_id=1,
            get_sections=mock_get_sections,
            get_categories=mock_get_categories,
            cache_get=mock_cache_get,
            cache_set=mock_cache_set
        )
        
        # Сбрасываем моки для чистого теста
        mock_get_sections.reset_mock()
        mock_get_categories.reset_mock()
        mock_cache_get.reset_mock()
        mock_cache_set.reset_mock()
        
        result2 = service.get_first_category_id(
            current_sphere_id=1,
            get_sections=mock_get_sections,
            get_categories=mock_get_categories,
            cache_get=mock_cache_get,
            cache_set=mock_cache_set
        )
        
        # Результаты должны быть идентичными
        assert result1 == result2
        
        # Вызовы должны быть идентичными
        assert mock_get_sections.call_count == 1
        assert mock_get_categories.call_count == 1


class TestUnifiedLogging:
    """Тесты унифицированного логирования."""

    def test_all_services_have_module_loggers(self):
        """Тест что все сервисы имеют модульные логгеры."""
        from app.controllers.structure_services import exporter, importer, integrity
        from app.controllers.structure_services import loader, selection, utilities, validation
        
        # Проверяем наличие модульных логгеров
        assert hasattr(exporter, 'logger')
        assert hasattr(importer, 'logger')  # Добавлен в importer.py
        assert hasattr(integrity, 'logger')
        assert hasattr(loader, 'logger')
        assert hasattr(selection, 'logger')
        assert hasattr(utilities, 'logger')
        assert hasattr(validation, 'logger')
        
        # Проверяем, что логгеры правильно настроены
        assert exporter.logger.name == 'app.controllers.structure_services.exporter'
        assert integrity.logger.name == 'app.controllers.structure_services.integrity'


class TestOptimizedCycles:
    """Тесты оптимизированных циклов."""

    def test_integrity_statistics_optimized(self):
        """Тест оптимизированного метода get_statistics."""
        service = IntegrityService()
        
        # Mock данные
        spheres = [{"id": 1}, {"id": 2}]
        sections_data = {
            1: [{"id": 10}, {"id": 11}],
            2: [{"id": 20}]
        }
        categories_data = {
            10: [{"id": 100}, {"id": 101}],
            11: [{"id": 110}],
            20: [{"id": 200}]
        }
        
        mock_get_spheres = Mock(return_value=spheres)
        mock_get_sections = Mock(side_effect=lambda sphere_id: sections_data.get(sphere_id, []))
        mock_get_categories = Mock(side_effect=lambda section_id: categories_data.get(section_id, []))
        mock_logger = Mock()
        
        result = service.get_statistics(
            get_spheres=mock_get_spheres,
            get_sections=mock_get_sections,
            get_categories=mock_get_categories,
            current_sphere_id=1,
            logger=mock_logger
        )
        
        # Проверяем корректность результата
        assert result["spheres_count"] == 2
        assert result["sections_count"] == 3  # 2 + 1
        assert result["categories_count"] == 4  # 2 + 1 + 1
        assert result["current_sphere_sections"] == 2
        assert result["current_sphere_categories"] == 3  # 2 + 1
        
        # Проверяем, что get_sections вызывается только один раз для каждой сферы
        assert mock_get_sections.call_count == 2
        assert mock_get_categories.call_count == 3  # По одному разу для каждой секции

    def test_integrity_validation_optimized(self):
        """Тест оптимизированного метода validate_structure_integrity."""
        service = IntegrityService()
        
        # Mock данные с ошибками связей
        spheres = [{"id": 1}]
        sections = [
            {"id": 10, "sphere_id": 1},  # Корректная связь
            {"id": 11, "sphere_id": 999}  # Неверная связь
        ]
        categories = [
            {"id": 100, "section_id": 10},  # Корректная связь
            {"id": 101, "section_id": 999}  # Неверная связь
        ]
        
        mock_get_spheres = Mock(return_value=spheres)
        mock_get_sections = Mock(return_value=sections)
        mock_get_categories = Mock(return_value=categories)
        mock_get_statistics = Mock(return_value={})
        mock_logger = Mock()
        
        result = service.validate_structure_integrity(
            get_spheres=mock_get_spheres,
            get_sections=mock_get_sections,
            get_categories=mock_get_categories,
            get_statistics=mock_get_statistics,
            logger=mock_logger
        )
        
        # Проверяем, что найдены ошибки
        assert result["is_valid"] is False
        assert len(result["errors"]) == 2
        assert "Раздел 11" in result["errors"][0]
        assert "Категория 101" in result["errors"][1]
        
        # Проверяем оптимизацию - использование list comprehensions
        assert mock_get_spheres.call_count == 1
        assert mock_get_sections.call_count == 1
        assert mock_get_categories.call_count == 1


class TestImporterSimplification:
    """Тесты упрощения двойных try/except в importer."""

    def test_importer_handles_service_creation_error(self):
        """Тест обработки ошибки создания StructureService."""
        service = ImportService()
        mock_model = Mock()
        mock_model.create_category.return_value = 123
        mock_logger = Mock()
        
        category_data = {"name": "Test Category", "section_id": 1}
        
        # Патчим StructureService чтобы он вызывал ошибку
        with patch('app.controllers.structure_services.importer.StructureService') as mock_service_class:
            mock_service_class.side_effect = ImportError("Не удалось импортировать сервис")
            
            result = service.create_category_for_import(
                model=mock_model,
                category_data=category_data,
                logger=mock_logger
            )
        
        # Проверяем, что используется fallback на прямую модель
        assert result == 123
        mock_model.create_category.assert_called_once_with(category_data)
        
        # Проверяем, что предупреждение залогировано
        mock_logger.warning.assert_called_once()
        assert "StructureService" in mock_logger.warning.call_args[0][0]


if __name__ == "__main__":
    pytest.main([__file__])
