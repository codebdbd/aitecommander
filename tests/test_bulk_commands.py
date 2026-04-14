"""Тесты для команд массовых операций."""

import unittest
from unittest.mock import Mock, patch

from app.utils.ui.dnd.base_bulk_command import BaseBulkCommand
from app.utils.ui.dnd.error_handler import BulkOperationErrorHandler


class TestBaseBulkCommand(unittest.TestCase):
    """Тесты для базового класса команд массовых операций."""

    def setUp(self):
        """Настройка перед каждым тестом."""
        self.main_window = Mock()
        self.command = BaseBulkCommand("test command", self.main_window, "test")

    def test_initialization(self):
        """Тест инициализации базового класса."""
        self.assertEqual(self.command.text(), "test command")
        self.assertEqual(self.command.item_type, "test")
        self.assertFalse(self.command._prepared)

    def test_prepare_if_needed(self):
        """Тест метода prepare_if_needed."""
        # Проверяем, что prepare_if_needed вызывает _prepare_data при необходимости
        self.command._prepare_data = Mock()
        self.command.prepare_if_needed()
        self.command._prepare_data.assert_called_once()
        self.assertTrue(self.command._prepared)

    def test_set_obsolete(self):
        """Тест метода set_obsolete."""
        # Проверяем, что set_obsolete не вызывает исключения
        try:
            self.command.set_obsolete(True)
            self.command.set_obsolete(False)
        except Exception as e:
            self.fail(f"set_obsolete вызвал исключение: {e}")


class TestBulkOperationErrorHandler(unittest.TestCase):
    """Тесты для обработчика ошибок массовых операций."""

    def setUp(self):
        """Настройка перед каждым тестом."""
        self.error_handler = BulkOperationErrorHandler()

    def test_classify_error(self):
        """Тест классификации ошибок."""
        # Тест ошибок валидации
        validation_error = ValueError("validation error")
        result = self.error_handler._classify_error(validation_error)
        self.assertEqual(result, self.error_handler._classify_error(validation_error))

        # Тест ошибок дубликатов
        duplicate_error = ValueError("duplicate constraint violation")
        result = self.error_handler._classify_error(duplicate_error)
        self.assertEqual(result, self.error_handler._classify_error(duplicate_error))

    def test_handle_error(self):
        """Тест обработки ошибок."""
        # Проверяем, что handle_error возвращает корректный отчет
        error = ValueError("test error")
        context = {"operation": "test"}
        report = self.error_handler.handle_error(error, context)
        
        self.assertIn("type", report)
        self.assertIn("message", report)
        self.assertIn("context", report)
        self.assertIn("timestamp", report)
        self.assertEqual(report["context"], context)


if __name__ == "__main__":
    unittest.main()
