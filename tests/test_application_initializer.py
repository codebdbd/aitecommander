"""Тесты для ApplicationInitializer (app/main.py)."""

import sqlite3
import unittest
from unittest.mock import Mock, patch


class TestApplicationInitializer(unittest.TestCase):
    """Проверка успешного/неуспешного выполнения initialize_all с моками."""

    @patch("app.main.create_main_window")
    @patch("app.main.ThemeController")
    @patch("app.main.Database")
    @patch("app.main.AppSettings")
    def test_initialize_all_success(self, mock_settings_cls, mock_db_cls, mock_theme_cls, mock_create_window):
        from app.main import ApplicationInitializer

        # Настройка моков
        mock_settings = Mock()
        mock_settings.get_theme.return_value = "Dark"
        mock_settings_cls.return_value = mock_settings

        mock_db = Mock()
        mock_db_cls.return_value = mock_db

        mock_theme = Mock()
        mock_theme.apply.return_value = None
        mock_theme_cls.return_value = mock_theme

        mock_window = Mock()
        mock_create_window.return_value = mock_window

        init = ApplicationInitializer(settings=None)
        result = init.initialize_all()

        self.assertTrue(result)
        # Проверяем, что каждый шаг был выполнен
        mock_settings_cls.assert_called_once()
        mock_db_cls.assert_called_once()
        mock_theme_cls.assert_called_once_with(mock_settings, top_panels_controller=None)
        mock_theme.apply.assert_called_once_with("Dark")
        mock_create_window.assert_called_once()
        # Установлена ссылка на окно в контроллер темы
        self.assertIs(init.main_window, mock_window)

    @patch("app.main.AppSettings", side_effect=Exception("Settings error"))
    def test_initialize_all_fail_settings(self, _mock_settings_cls):
        from app.main import ApplicationInitializer

        init = ApplicationInitializer(settings=None)
        self.assertFalse(init.initialize_all())

    @patch("app.main.AppSettings")
    @patch("app.main.Database", side_effect=Exception("DB error"))
    def test_initialize_all_fail_database(self, _mock_db_cls, _mock_settings_cls):
        from app.main import ApplicationInitializer

        init = ApplicationInitializer(settings=None)
        self.assertFalse(init.initialize_all())

    @patch("app.main.AppSettings")
    @patch("app.main.Database")
    @patch("app.main.ThemeController", side_effect=Exception("Theme error"))
    def test_initialize_all_fail_theme_controller(self, _mock_theme_cls, _mock_db_cls, _mock_settings_cls):
        from app.main import ApplicationInitializer

        init = ApplicationInitializer(settings=None)
        self.assertFalse(init.initialize_all())

    @patch("app.main.create_main_window", side_effect=Exception("Window error"))
    @patch("app.main.ThemeController")
    @patch("app.main.Database")
    @patch("app.main.AppSettings")
    def test_initialize_all_fail_main_window(self, _mock_settings_cls, _mock_db_cls, _mock_theme_cls, _mock_create_window):
        from app.main import ApplicationInitializer

        init = ApplicationInitializer(settings=None)
        self.assertFalse(init.initialize_all())

    def test_cleanup_swallows_predictable_errors(self):
        from app.main import ApplicationInitializer

        init = ApplicationInitializer()
        # database.close может бросать
        init.database = Mock()
        # Предсказуемые ошибки: AttributeError или sqlite3.Error должны логироваться и подавляться
        init.database.close.side_effect = AttributeError("no close attr works")

        # Вызов не должен падать
        init.cleanup()

    def test_cleanup_raises_unexpected_error(self):
        from app.main import ApplicationInitializer

        init = ApplicationInitializer()
        init.database = Mock()
        # Неожиданная ошибка не должна подавляться
        init.database.close.side_effect = RuntimeError("unexpected")

        with self.assertRaises(RuntimeError):
            init.cleanup()


if __name__ == "__main__":
    unittest.main()
