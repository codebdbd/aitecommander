"""Тесты для проверки исправлений обработки исключений в базовых виджетах."""

import unittest
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication, QToolButton

from app.views.base_widgets import BaseLinksPanelWidget


class TestBaseLinksPanelWidgetExceptionHandling(unittest.TestCase):
    """Тесты обработки исключений в BaseLinksPanelWidget."""

    @classmethod
    def setUpClass(cls):
        """Инициализация QApplication для тестов."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        """Настройка для каждого теста."""
        self.widget = BaseLinksPanelWidget()

    def test_find_icon_handles_file_not_found_error(self):
        """Тест обработки FileNotFoundError в _find_icon."""
        with patch('app.views.base_widgets.resolve_icon_path') as mock_resolve:
            mock_resolve.side_effect = FileNotFoundError("File not found")
            
            with patch('app.views.base_widgets.logging.warning') as mock_log:
                result = self.widget._find_icon("/nonexistent/path.png")
                
                # Проверяем, что вернулся путь по умолчанию
                self.assertIsInstance(result, str)
                
                # Проверяем, что было залогировано предупреждение
                mock_log.assert_called_once()
                args = mock_log.call_args[0]
                self.assertIn("Не удалось разрешить путь к иконке", args[0])
                self.assertIn("/nonexistent/path.png", args[1])

    def test_find_icon_handles_os_error(self):
        """Тест обработки OSError в _find_icon."""
        with patch('app.views.base_widgets.resolve_icon_path') as mock_resolve:
            mock_resolve.side_effect = OSError("Permission denied")
            
            with patch('app.views.base_widgets.logging.warning') as mock_log:
                result = self.widget._find_icon("/restricted/path.png")
                
                # Проверяем, что вернулся путь по умолчанию
                self.assertIsInstance(result, str)
                
                # Проверяем логирование
                mock_log.assert_called_once()
                args = mock_log.call_args[0]
                self.assertIn("Не удалось разрешить путь к иконке", args[0])

    def test_find_icon_handles_unexpected_exception(self):
        """Тест обработки неожиданных исключений в _find_icon."""
        with patch('app.views.base_widgets.resolve_icon_path') as mock_resolve:
            mock_resolve.side_effect = ValueError("Unexpected error")
            
            with patch('app.views.base_widgets.logging.exception') as mock_log:
                result = self.widget._find_icon("/some/path.png")
                
                # Проверяем, что вернулся путь по умолчанию
                self.assertIsInstance(result, str)
                
                # Проверяем логирование с полной трассировкой
                mock_log.assert_called_once()
                args = mock_log.call_args[0]
                self.assertIn("Неожиданная ошибка при разрешении иконки", args[0])

    def test_find_icon_returns_default_for_empty_path(self):
        """Тест возврата иконки по умолчанию для пустого пути."""
        result = self.widget._find_icon("")
        self.assertIsInstance(result, str)
        
        result = self.widget._find_icon(None)
        self.assertIsInstance(result, str)

    def test_populate_panel_handles_button_creation_error(self):
        """Тест обработки ошибок создания кнопок в _populate_panel."""
        # Мокаем функцию создания кнопки, которая выбрасывает исключение
        def failing_create_button(link):
            if link.get('id') == 'failing_link':
                raise ValueError("Button creation failed")
            return QToolButton()

        test_items = [
            {'id': 'good_link', 'name': 'Good Link', 'url': 'http://example.com'},
            {'id': 'failing_link', 'name': 'Failing Link', 'url': 'http://fail.com'},
            {'id': 'another_good_link', 'name': 'Another Good Link', 'url': 'http://good.com'}
        ]

        with patch('app.views.base_widgets.logging.exception') as mock_exception:
            self.widget._populate_panel(test_items, failing_create_button)
            
            # Проверяем, что было залогировано исключение об ошибке
            mock_exception.assert_called_once()
            args = mock_exception.call_args[0]
            self.assertIn("Не удалось создать кнопку для элемента панели", args[0])
            
            # Проверяем, что в логе есть информация о проблемной ссылке
            link_info = args[1]
            self.assertIn('failing_link', str(link_info))

    def test_populate_panel_debug_logging_for_button_creation_error(self):
        """Тест детального логирования при ошибке создания кнопки."""
        def failing_create_button(link):
            raise RuntimeError("Detailed error for debugging")

        test_items = [{'id': 'test_link', 'name': 'Test Link', 'url': 'http://test.com'}]

        with patch('app.views.base_widgets.logging.exception') as mock_exception:
            self.widget._populate_panel(test_items, failing_create_button)
            
            # Проверяем, что вызывается logging.exception с диагностикой
            mock_exception.assert_called_once()
            args = mock_exception.call_args[0]
            self.assertIn("Не удалось создать кнопку для элемента панели", args[0])

    def test_populate_panel_logs_none_button_return(self):
        """Тест логирования когда create_button_func возвращает None."""
        def none_returning_create_button(link):
            return None

        test_items = [{'id': 'test_link', 'name': 'Test Link'}]

        with patch('app.views.base_widgets.logging.debug') as mock_debug:
            self.widget._populate_panel(test_items, none_returning_create_button)
            
            # Проверяем, что залогировано сообщение о None
            mock_debug.assert_called_once()
            args = mock_debug.call_args[0]
            self.assertIn("create_button_func вернула None", args[0])

    def test_populate_panel_handles_size_policy_error(self):
        """Тест обработки ошибок при работе с sizePolicy."""
        def good_create_button(link):
            return QToolButton()

        test_items = [{'id': 'test_link', 'name': 'Test Link'}]

        # Мокаем sizePolicy чтобы выбросить исключение
        with patch.object(self.widget, 'sizePolicy') as mock_size_policy:
            mock_size_policy.side_effect = AttributeError("sizePolicy not available")
            
            with patch('app.views.base_widgets.logging.warning') as mock_warning:
                self.widget._populate_panel(test_items, good_create_button)
                
                # Проверяем, что ошибка sizePolicy была залогирована
                mock_warning.assert_called_once()
                args = mock_warning.call_args[0]
                self.assertIn("Не удалось добавить stretch в layout", args[0])

    def test_populate_panel_successful_case(self):
        """Тест успешного выполнения _populate_panel."""
        def good_create_button(link):
            button = QToolButton()
            button.setObjectName(f"button_{link['id']}")
            return button

        test_items = [
            {'id': 'link1', 'name': 'Link 1'},
            {'id': 'link2', 'name': 'Link 2'}
        ]

        # Мокаем sizePolicy для избежания реальных Qt вызовов
        with patch.object(self.widget, 'sizePolicy') as mock_size_policy:
            mock_policy = Mock()
            mock_policy.horizontalPolicy.return_value = Mock()
            mock_size_policy.return_value = mock_policy
            
            self.widget._populate_panel(test_items, good_create_button)
            
            # Проверяем, что кнопки были добавлены в layout панели
            self.assertEqual(self.widget.panel_layout.count(), 2)


if __name__ == '__main__':
    unittest.main()
