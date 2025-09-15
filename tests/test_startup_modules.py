"""Тесты для модулей запуска приложения."""

import logging
import sys
import unittest
from unittest.mock import Mock, patch

from app.controllers.system.db_init import DatabaseInitializer
from app.startup.app_factory import create_application
from app.startup.argument_parser import (
    AppArguments,
    determine_log_level,
    parse_arguments,
)
from app.startup.logging_setup import log_shutdown, log_system_info, setup_logging


class TestArgumentParser(unittest.TestCase):
    """Тесты для парсера аргументов командной строки."""

    @patch("sys.argv", ["test_app"])
    def test_parse_arguments_default(self):
        """Тест парсинга аргументов по умолчанию."""
        args = parse_arguments()
        self.assertIsInstance(args, AppArguments)
        self.assertFalse(args.debug)
        self.assertIsNone(args.log_level)

    @patch("sys.argv", ["test_app", "--debug"])
    def test_parse_arguments_debug(self):
        """Тест парсинга аргументов с флагом debug."""
        args = parse_arguments()
        self.assertTrue(args.debug)
        self.assertIsNone(args.log_level)

    @patch("sys.argv", ["test_app", "--log-level", "ERROR"])
    def test_parse_arguments_log_level(self):
        """Тест парсинга аргументов с уровнем логирования."""
        args = parse_arguments()
        self.assertFalse(args.debug)
        self.assertEqual(args.log_level, "ERROR")

    def test_determine_log_level_default(self):
        """Тест определения уровня логирования по умолчанию."""
        args = AppArguments(debug=False, log_level=None)
        level = determine_log_level(args)
        self.assertEqual(level, logging.INFO)

    def test_determine_log_level_debug(self):
        """Тест определения уровня логирования в режиме отладки."""
        args = AppArguments(debug=True, log_level=None)
        level = determine_log_level(args)
        self.assertEqual(level, logging.DEBUG)

    def test_determine_log_level_explicit(self):
        """Тест определения явно заданного уровня логирования."""
        args = AppArguments(debug=True, log_level="WARNING")
        level = determine_log_level(args)
        self.assertEqual(level, logging.WARNING)


class TestLoggingSetup(unittest.TestCase):
    """Тесты для настройки логирования."""

    @patch("app.startup.logging_setup.ApplicationLogger")
    @patch("app.startup.logging_setup.ExceptionHandler")
    @patch("app.startup.logging_setup.logger.info")
    def test_setup_logging(
        self, mock_log_info, mock_exception_handler, mock_app_logger
    ):
        """Тест настройки системы логирования."""
        setup_logging(logging.DEBUG)

        mock_app_logger.assert_called_once_with(logging.DEBUG)
        mock_exception_handler.assert_called_once()
        self.assertEqual(mock_log_info.call_count, 3)  # Заголовок из 3 строк

    @patch("app.startup.logging_setup.logger.isEnabledFor")
    @patch("app.startup.logging_setup.logger.info")
    def test_log_system_info_debug_disabled(self, mock_log_info, mock_is_enabled_for):
        """Тест логирования системной информации при отключенном DEBUG."""
        mock_is_enabled_for.return_value = False

        log_system_info()

        mock_is_enabled_for.assert_called_once_with(logging.DEBUG)
        mock_log_info.assert_not_called()

    @patch("app.startup.logging_setup.logger.info")
    def test_log_shutdown(self, mock_log_info):
        """Тест логирования завершения работы."""
        log_shutdown()

        self.assertEqual(mock_log_info.call_count, 3)  # Заголовок из 3 строк


class TestAppFactory(unittest.TestCase):
    """Тесты для фабрики приложения."""

    @patch("app.startup.app_factory.QApplication")
    @patch("app.startup.app_factory.QFont")
    def test_create_application(self, mock_qfont, mock_qapp):
        """Тест создания приложения."""
        mock_app = Mock()
        mock_qapp.return_value = mock_app
        mock_font = Mock()
        mock_qfont.return_value = mock_font
        mock_app.font.return_value.family.return_value = "Arial"

        result = create_application()

        mock_qapp.assert_called_once_with(sys.argv)
        mock_app.setApplicationName.assert_called_once_with("MyPyQtApp")
        mock_app.setApplicationVersion.assert_called_once_with("1.0.0")
        mock_app.setOrganizationName.assert_called_once_with("MyCompany")
        mock_qfont.assert_called_once_with("Arial", 10)
        mock_app.setFont.assert_called_once_with(mock_font)
        self.assertEqual(result, mock_app)


class TestDatabaseInitializer(unittest.TestCase):
    """Тесты для инициализатора базы данных."""

    def setUp(self):
        """Настройка тестов."""
        self.mock_database = Mock()
        self.mock_main_window = Mock()
        self.db_initializer = DatabaseInitializer(
            self.mock_database, self.mock_main_window
        )

    def test_init(self):
        """Тест инициализации DatabaseInitializer."""
        self.assertEqual(self.db_initializer.database, self.mock_database)
        self.assertEqual(self.db_initializer.main_window, self.mock_main_window)

    def test_do_db_init_success(self):
        """Тест успешной инициализации БД."""
        result = self.db_initializer._do_db_init()

        self.mock_database.prepare_dirs.assert_called_once()
        self.mock_database.initialize_or_migrate.assert_called_once()
        self.assertTrue(result)

    def test_do_db_init_failure(self):
        """Тест неуспешной инициализации БД."""
        self.mock_database.prepare_dirs.side_effect = Exception("Test error")
        with self.assertRaises(Exception):
            self.db_initializer._do_db_init()

    def test_update_status_message(self):
        """Тест обновления сообщения статуса."""
        self.mock_main_window.message_label = Mock()

        self.db_initializer._update_status_message("Test message")

        self.mock_main_window.message_label.setText.assert_called_once_with(
            "Test message"
        )

    def test_update_status_message_no_label(self):
        """Тест обновления сообщения статуса без label."""
        self.mock_main_window.message_label = None

        # Не должно вызывать исключение
        self.db_initializer._update_status_message("Test message")

    def test_set_ui_enabled(self):
        """Тест включения/отключения UI."""
        self.db_initializer._set_ui_enabled(False)

        self.mock_main_window.setEnabled.assert_called_once_with(False)

    @patch("app.controllers.system.db_init.QMessageBox")
    def test_show_critical_error(self, mock_message_box):
        """Тест показа критической ошибки."""
        self.db_initializer._show_critical_error("Test Title", "Test Message")

        mock_message_box.critical.assert_called_once_with(
            self.mock_main_window, "Test Title", "Test Message"
        )

    @patch("app.controllers.system.db_init.QApplication")
    def test_quit_application(self, mock_qapp):
        """Тест завершения приложения."""
        mock_app_instance = Mock()
        mock_qapp.instance.return_value = mock_app_instance

        self.db_initializer._quit_application()

        mock_app_instance.quit.assert_called_once()

    @patch("app.controllers.system.db_init.run_db")
    def test_initialize_async(self, mock_run_db):
        """Тест асинхронной инициализации."""
        mock_callback = Mock()
        mock_error_callback = Mock()

        self.db_initializer.initialize_async(mock_callback, mock_error_callback)

        mock_run_db.assert_called_once()
        call_args = mock_run_db.call_args
        self.assertEqual(call_args[0][0], self.db_initializer._do_db_init)
        self.assertTrue(call_args[1]["use_lock"])
        self.assertEqual(call_args[1]["description"], "db_init")


if __name__ == "__main__":
    unittest.main()
