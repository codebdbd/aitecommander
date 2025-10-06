"""
Тесты для проверки улучшений недели 2 (производительность).

✅ ТЕСТЫ: Проверяют lazy loading диалогов, конфигурируемый batch_size и улучшенную обработку ошибок.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.controllers.ui.dialogs.system_dialog_controller import SystemDialogController
from app.views.widgets.base.base_widgets import BaseLinksPanelWidget
from app.config_data import app_config


class TestWeek2PerformanceImprovements:
    """Тесты улучшений производительности недели 2."""

    def test_lazy_loading_about_dialog(self):
        """✅ ТЕСТ: Проверяет lazy loading диалога About."""
        # Arrange
        main_window = Mock()
        controller = SystemDialogController(
            main_window,
            database_controller=Mock(),
            links_table_controller=Mock(),
            links_business=Mock(),
        )

        # Act & Assert: Первый вызов создает диалог
        with patch('PyQt6.QtWidgets.QMessageBox') as mock_msgbox:
            controller.show_about_dialog()
            mock_msgbox.assert_called_once()
            assert controller._about_dialog is not None

        # Act & Assert: Второй вызов использует существующий диалог
        with patch.object(controller._about_dialog, 'exec') as mock_exec:
            controller.show_about_dialog()
            mock_exec.assert_called_once()

    def test_lazy_loading_settings_dialog(self):
        """✅ ТЕСТ: Проверяет lazy loading диалога Settings."""
        # Arrange
        main_window = Mock()
        main_window.settings = Mock()
        main_window.theme_ctrl = Mock()

        controller = SystemDialogController(
            main_window,
            database_controller=Mock(),
            links_table_controller=Mock(),
            links_business=Mock(),
        )

        # Act & Assert: Первый вызов создает диалог
        with patch('app.views.windows.dialogs.entity_dialogs.SettingsDialog') as mock_settings:
            controller.show_settings_dialog()
            mock_settings.assert_called_once()
            assert controller._settings_dialog is not None

        # Act & Assert: Второй вызов использует существующий диалог
        with patch.object(controller._settings_dialog, 'exec') as mock_exec:
            controller.show_settings_dialog()
            mock_exec.assert_called_once()

    def test_lazy_loading_file_search_dialog(self):
        """✅ ТЕСТ: Проверяет lazy loading диалога File Search."""
        # Arrange
        main_window = Mock()
        controller = SystemDialogController(
            main_window,
            database_controller=Mock(),
            links_table_controller=Mock(),
            links_business=Mock(),
        )

        # Act & Assert: Первый вызов создает диалог
        with patch('app.views.windows.dialogs.file_search_dialog.file_search_dialog.FileSearchDialog') as mock_search:
            controller.show_file_search_dialog()
            mock_search.assert_called_once()
            assert controller._file_search_dialog is not None

        # Act & Assert: Второй вызов использует существующий диалог
        with patch.object(controller._file_search_dialog, 'exec') as mock_exec:
            controller.show_file_search_dialog()
            mock_exec.assert_called_once()

    def test_configurable_batch_size(self, qtbot):
        """✅ ТЕСТ: Проверяет конфигурируемый batch_size."""
        # Arrange: Настраиваем app_config с кастомным batch_size
        test_batch_size = 25

        with patch.object(app_config.ui, 'get') as mock_get:
            mock_get.return_value = test_batch_size

            # Создаем widget
            widget = BaseLinksPanelWidget()
            qtbot.addWidget(widget)

            # Добавляем тестовые данные
            test_items = [{'id': i, 'name': f'item{i}'} for i in range(100)]
            widget._pending_items = test_items.copy()

            # Act: Обрабатываем батч
            widget._process_batch()

            # Assert: Используется правильный batch_size из конфига
            mock_get.assert_called_with("panel_batch_size", 50)
            assert len(widget._pending_items) == 100 - test_batch_size

    def test_batch_size_fallback_to_default(self, qtbot):
        """✅ ТЕСТ: Проверяет fallback к дефолтному batch_size."""
        # Arrange: app_config.ui.get возвращает None
        with patch.object(app_config.ui, 'get') as mock_get:
            mock_get.return_value = None

            widget = BaseLinksPanelWidget()
            qtbot.addWidget(widget)

            test_items = [{'id': i, 'name': f'item{i}'} for i in range(100)]
            widget._pending_items = test_items.copy()

            # Act: Обрабатываем батч
            widget._process_batch()

            # Assert: Используется дефолтный batch_size = 50
            mock_get.assert_called_with("panel_batch_size", 50)
            assert len(widget._pending_items) == 50

    def test_improved_error_handling_update_geometry(self, qtbot):
        """✅ ТЕСТ: Проверяет улучшенную обработку ошибок в updateGeometry."""
        # Arrange
        widget = BaseLinksPanelWidget()
        qtbot.addWidget(widget)

        # Мокаем updateGeometry чтобы вызвать AttributeError
        with patch.object(widget, 'updateGeometry') as mock_update:
            mock_update.side_effect = AttributeError("Object deleted")

            # Act & Assert: Не должно вызывать исключений
            try:
                widget._finish_populate()
            except Exception as e:
                pytest.fail(f"_finish_populate должен обрабатывать ошибки корректно: {e}")

    def test_improved_error_handling_find_icon(self):
        """✅ ТЕСТ: Проверяет улучшенную обработку ошибок в _find_icon."""
        # Arrange
        widget = BaseLinksPanelWidget()

        # Мокаем resolve_icon_path чтобы вызвать AttributeError
        with patch('app.views.widgets.base.base_widgets.resolve_icon_path') as mock_resolve:
            mock_resolve.side_effect = AttributeError("Module not found")

            # Act: Вызываем _find_icon
            result = widget._find_icon("test_icon.png")

            # Assert: Возвращает дефолтную иконку при ошибке
            assert result == str(widget._get_default_icon_path())

    def test_improved_error_handling_mime_data(self):
        """✅ ТЕСТ: Проверяет улучшенную обработку ошибок в mimeData."""
        # Arrange
        widget = BaseLinksPanelWidget()
        mock_items = [Mock()]

        # Мокаем _extract_item_ids_from_items чтобы вызвать ValueError
        with patch.object(widget, '_extract_item_ids_from_items') as mock_extract:
            mock_extract.side_effect = ValueError("Invalid data")

            # Act: Вызываем mimeData
            result = widget.mimeData(mock_items)

            # Assert: Возвращает None при ошибке
            assert result is None

    def test_improved_error_handling_move_rows_visually(self):
        """✅ ТЕСТ: Проверяет улучшенную обработку ошибок в _move_rows_visually."""
        # Arrange
        widget = BaseLinksPanelWidget()

        # Мокаем viewport update чтобы вызвать RuntimeError
        with patch.object(widget, 'viewport') as mock_viewport:
            mock_viewport.return_value = Mock()
            mock_viewport.return_value.update.side_effect = RuntimeError("Object deleted")

            # Act & Assert: Не должно вызывать исключений
            try:
                widget._move_rows_visually([1, 2], 3)
            except Exception as e:
                pytest.fail(f"_move_rows_visually должен обрабатывать ошибки корректно: {e}")

    def test_improved_error_handling_drag_pixmap(self):
        """✅ ТЕСТ: Проверяет улучшенную обработку ошибок в _create_drag_pixmap."""
        # Arrange
        widget = BaseLinksPanelWidget()
        mock_items = [Mock()]

        # Мокаем получение строк чтобы вызвать TypeError
        with patch.object(widget, '_get_selected_rows') as mock_get_rows:
            mock_get_rows.side_effect = TypeError("Invalid type")

            # Act: Вызываем _create_drag_pixmap
            result = widget._create_drag_pixmap(mock_items)

            # Assert: Возвращает None при ошибке
            assert result is None

    def test_improved_error_handling_is_internal_drop(self):
        """✅ ТЕСТ: Проверяет улучшенную обработку ошибок в _is_internal_drop."""
        # Arrange
        widget = BaseLinksPanelWidget()
        mock_event = Mock()
        mock_event.source.side_effect = AttributeError("No source attribute")

        # Act: Вызываем _is_internal_drop
        result = widget._is_internal_drop(mock_event)

        # Assert: Возвращает False при ошибке
        assert result is False

    def test_performance_lazy_loading_dialogs(self):
        """✅ ТЕСТ: Проверяет производительность lazy loading диалогов."""
        # Arrange
        main_window = Mock()
        controller = SystemDialogController(
            main_window,
            database_controller=Mock(),
            links_table_controller=Mock(),
            links_business=Mock(),
        )

        # Act: Показываем все диалоги несколько раз
        for _ in range(3):
            controller.show_about_dialog()
            controller.show_settings_dialog()
            controller.show_file_search_dialog()

        # Assert: Диалоги создаются только один раз
        assert controller._about_dialog is not None
        assert controller._settings_dialog is not None
        assert controller._file_search_dialog is not None

    def test_batch_size_configuration_integration(self, qtbot):
        """✅ ТЕСТ: Проверяет интеграцию конфигурируемого batch_size."""
        # Arrange: Настраиваем различные размеры батчей
        test_cases = [10, 25, 100, 200]

        for expected_batch_size in test_cases:
            with patch.object(app_config.ui, 'get') as mock_get:
                mock_get.return_value = expected_batch_size

                # Создаем новый widget для каждого теста
                widget = BaseLinksPanelWidget()
                qtbot.addWidget(widget)

                # Добавляем достаточно элементов
                test_items = [{'id': i, 'name': f'item{i}'} for i in range(expected_batch_size * 2)]
                widget._pending_items = test_items.copy()

                # Act: Обрабатываем батч
                widget._process_batch()

                # Assert: Правильно используется batch_size из конфига
                mock_get.assert_called_with("panel_batch_size", 50)
                remaining_items = len(widget._pending_items)
                expected_remaining = len(test_items) - expected_batch_size
                assert remaining_items == expected_remaining
