"""Тесты для главного входа приложения (main())."""

import logging
import unittest
from unittest.mock import Mock, patch


class TestMainEntrypoint(unittest.TestCase):
    """Проверка поведения main() без запуска реального GUI."""

    @patch("app.main.BrowserProfilesLoader")
    @patch("app.main.DatabaseInitializer")
    @patch("app.main.ApplicationInitializer")
    @patch("app.main.create_application")
    @patch("app.main.setup_logging")
    @patch("app.main.determine_log_level")
    @patch("app.main.parse_arguments")
    def test_main_success_flow(
        self,
        mock_parse_args,
        mock_determine_level,
        mock_setup_logging,
        mock_create_app,
        mock_app_initializer_cls,
        mock_db_initializer_cls,
        mock_profiles_loader_cls,
    ):
        """Успешный путь: initialize_all=True, app.exec() возвращает код выхода."""
        from app.main import main

        # Аргументы и уровень логирования
        mock_parse_args.return_value = Mock()
        mock_determine_level.return_value = logging.INFO

        # Мокаем приложение
        mock_app = Mock()
        mock_app.exec.return_value = 0
        mock_create_app.return_value = mock_app

        # Мокаем ApplicationInitializer
        mock_app_initializer = Mock()
        mock_app_initializer.initialize_all.return_value = True
        mock_app_initializer_cls.return_value = mock_app_initializer

        # Мокаем DatabaseInitializer
        mock_db_initializer = Mock()
        mock_db_initializer_cls.return_value = mock_db_initializer

        # Мокаем BrowserProfilesLoader
        mock_profiles_loader = Mock()
        mock_profiles_loader_cls.return_value = mock_profiles_loader

        exit_code = main()

        self.assertEqual(exit_code, 0)
        mock_setup_logging.assert_called_once()
        mock_create_app.assert_called_once()
        mock_app_initializer.initialize_all.assert_called_once()
        mock_db_initializer.initialize_async.assert_called_once()
        mock_profiles_loader.setup_lazy_loading.assert_called_once()
        mock_app.exec.assert_called_once()

    @patch("app.main.BrowserProfilesLoader")
    @patch("app.main.DatabaseInitializer")
    @patch("app.main.ApplicationInitializer")
    @patch("app.main.create_application")
    @patch("app.main.setup_logging")
    @patch("app.main.determine_log_level")
    @patch("app.main.parse_arguments")
    def test_main_init_fails_quits_and_returns_1(
        self,
        mock_parse_args,
        mock_determine_level,
        mock_setup_logging,
        mock_create_app,
        mock_app_initializer_cls,
        mock_db_initializer_cls,
        mock_profiles_loader_cls,
    ):
        """Инициализация не удалась: ожидаем app.quit() и код 1."""
        from app.main import main

        mock_parse_args.return_value = Mock()
        mock_determine_level.return_value = logging.INFO

        mock_app = Mock()
        mock_create_app.return_value = mock_app

        mock_app_initializer = Mock()
        mock_app_initializer.initialize_all.return_value = False
        mock_app_initializer_cls.return_value = mock_app_initializer

        exit_code = main()

        self.assertEqual(exit_code, 1)
        mock_app.quit.assert_called_once()
        mock_db_initializer_cls.assert_not_called()
        mock_profiles_loader_cls.assert_not_called()
        mock_app.exec.assert_not_called()

    @patch("app.main.log_shutdown")
    @patch("app.main.BrowserProfilesLoader")
    @patch("app.main.DatabaseInitializer")
    @patch("app.main.ApplicationInitializer")
    @patch("app.main.create_application")
    @patch("app.main.setup_logging")
    @patch("app.main.determine_log_level")
    @patch("app.main.parse_arguments")
    def test_main_exception_handling_returns_1_and_cleanup(
        self,
        mock_parse_args,
        mock_determine_level,
        mock_setup_logging,
        mock_create_app,
        mock_app_initializer_cls,
        mock_db_initializer_cls,
        mock_profiles_loader_cls,
        mock_log_shutdown,
    ):
        """Исключение внутри main(): ожидаем 1 и вызов cleanup в finally."""
        from app.main import main

        mock_parse_args.return_value = Mock()
        mock_determine_level.return_value = logging.INFO

        mock_create_app.side_effect = Exception("boom")

        mock_app_initializer = Mock()
        mock_app_initializer_cls.return_value = mock_app_initializer

        exit_code = main()

        self.assertEqual(exit_code, 1)
        mock_app_initializer.cleanup.assert_called_once()
        mock_log_shutdown.assert_called_once()

    @patch("app.main.parse_arguments")
    @patch("app.main.determine_log_level")
    @patch("app.main.setup_logging")
    @patch("app.main.create_application")
    @patch("app.main.ApplicationInitializer")
    def test_main_cleanup_unexpected_error_propagates(
        self,
        mock_app_initializer_cls,
        mock_create_app,
        mock_setup_logging,
        mock_determine_level,
        mock_parse_args,
    ):
        """Неожиданное исключение из cleanup() не должно подавляться main()."""
        from app.main import main

        mock_parse_args.return_value = Mock()
        mock_determine_level.return_value = logging.INFO

        # Форсируем раннюю ошибка в try, чтобы попасть в finally
        mock_create_app.side_effect = Exception("boom")

        mock_app_initializer = Mock()
        mock_app_initializer.cleanup.side_effect = RuntimeError("cleanup crash")
        mock_app_initializer_cls.return_value = mock_app_initializer

        with self.assertRaises(RuntimeError):
            main()


if __name__ == "__main__":
    unittest.main()
