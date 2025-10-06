"""
Тесты для проверки критичных исправлений недели 1.

✅ ТЕСТЫ: Проверяют применение протоколов и TypedDict'ов.
"""

import pytest
from unittest.mock import Mock
from typing import get_type_hints

from app.views.windows.main_window import MainWindow
from app.views.widgets.protocols import (
    LinkDict, TreeNodeDict, SystemDialogsProtocol, LinksBusinessProtocol
)
from app.views.widgets.base.base_widgets import BaseLinksPanelWidget


class TestWeek1CriticalFixes:
    """Тесты критичных исправлений недели 1."""

    def test_main_window_system_dialogs_protocol(self):
        """✅ ТЕСТ: Проверяет использование SystemDialogsProtocol в MainWindow."""
        # Arrange & Act
        hints = get_type_hints(MainWindow)

        # Assert: MainWindow использует SystemDialogsProtocol вместо object
        assert 'system_dialogs' in hints
        assert hints['system_dialogs'] == SystemDialogsProtocol

    def test_base_links_panel_links_business_protocol(self):
        """✅ ТЕСТ: Проверяет использование LinksBusinessProtocol в BaseLinksPanelWidget."""
        # Arrange & Act
        hints = get_type_hints(BaseLinksPanelWidget.__init__)

        # Assert: BaseLinksPanelWidget использует LinksBusinessProtocol вместо Any
        assert 'links_business' in hints
        assert hints['links_business'] == LinksBusinessProtocol

    def test_link_dict_typed_dict_structure(self):
        """✅ ТЕСТ: Проверяет структуру LinkDict TypedDict."""
        # Arrange & Act & Assert
        expected_fields = {
            'id': int,
            'name': str,
            'url': str,
            'category_id': int,
            'type': str,
            'browser_key': str,
            'icon_path': str,
            'position': int,
            'is_favorite': int,
            'notes': str
        }

        # Проверяем что все поля присутствуют и имеют правильные типы
        for field_name, expected_type in expected_fields.items():
            assert hasattr(LinkDict, '__annotations__')
            assert field_name in LinkDict.__annotations__
            assert LinkDict.__annotations__[field_name] == expected_type

    def test_tree_node_dict_typed_dict_structure(self):
        """✅ ТЕСТ: Проверяет структуру TreeNodeDict TypedDict."""
        # Arrange & Act & Assert
        expected_fields = {
            'type': str,
            'id': int,
            'name': str,
            'icon_path': str,
            'position': int
        }

        # Проверяем что все поля присутствуют и имеют правильные типы
        for field_name, expected_type in expected_fields.items():
            assert hasattr(TreeNodeDict, '__annotations__')
            assert field_name in TreeNodeDict.__annotations__
            assert TreeNodeDict.__annotations__[field_name] == expected_type

    def test_system_dialogs_protocol_methods(self):
        """✅ ТЕСТ: Проверяет методы SystemDialogsProtocol."""
        # Arrange & Act & Assert
        protocol_methods = SystemDialogsProtocol.__protocol_attrs__

        expected_methods = {
            'show_about_dialog',
            'show_settings_dialog',
            'show_file_search_dialog',
            'handle_import_browser_bookmarks'
        }

        # Проверяем что все ожидаемые методы присутствуют в протоколе
        for method in expected_methods:
            assert method in protocol_methods

    def test_links_business_protocol_methods(self):
        """✅ ТЕСТ: Проверяет методы LinksBusinessProtocol."""
        # Arrange & Act & Assert
        protocol_methods = LinksBusinessProtocol.__protocol_attrs__

        expected_methods = {
            'get_links',
            'create_link',
            'update_link',
            'delete_link'
        }

        # Проверяем что все ожидаемые методы присутствуют в протоколе
        for method in expected_methods:
            assert method in protocol_methods

    def test_main_window_cleanup_method_exists(self):
        """✅ ТЕСТ: Проверяет наличие метода cleanup в MainWindow."""
        # Arrange & Act & Assert
        assert hasattr(MainWindow, '_cleanup_resources')
        assert callable(MainWindow._cleanup_resources)

    def test_base_dialog_context_menu_cleanup(self):
        """✅ ТЕСТ: Проверяет наличие context menu cleanup в BaseDialog."""
        from app.views.windows.dialogs.base_dialog import BaseDialog

        # Arrange & Act & Assert
        assert hasattr(BaseDialog, '_cleanup_context_menus')
        assert callable(BaseDialog._cleanup_context_menus)

    def test_base_widgets_improved_error_handling(self):
        """✅ ТЕСТ: Проверяет улучшенную обработку ошибок в BaseLinksPanelWidget."""
        # Arrange: Создаем мок функцию которая вызывает различные исключения
        def failing_create_func(link_data):
            if link_data.get('id') == 1:
                raise AttributeError("Test attribute error")
            elif link_data.get('id') == 2:
                raise KeyError("Test key error")
            elif link_data.get('id') == 3:
                raise ValueError("Test value error")
            elif link_data.get('id') == 4:
                raise TypeError("Test type error")
            elif link_data.get('id') == 5:
                raise Exception("Unexpected error")
            return Mock()

        # Act: Создаем widget и пробуем создать кнопки
        widget = BaseLinksPanelWidget()
        test_links = [
            {'id': 1, 'name': 'link1'},
            {'id': 2, 'name': 'link2'},
            {'id': 3, 'name': 'link3'},
            {'id': 4, 'name': 'link4'},
            {'id': 5, 'name': 'link5'},
        ]

        # Assert: Не должно вызывать исключений при обработке ошибок
        try:
            widget._populate_panel(test_links, failing_create_func)
        except Exception as e:
            pytest.fail(f"Widget должен обрабатывать ошибки корректно: {e}")

    def test_structure_tree_model_deleted_object_checks(self):
        """✅ ТЕСТ: Проверяет проверки на deleted objects в StructureTreeModel."""
        from app.views.models.structure_tree_model import StructureTreeModel
        from PyQt6.QtCore import QModelIndex

        # Arrange: Создаем модель
        model = StructureTreeModel()

        # Создаем мок индекс с None internalPointer
        mock_index = Mock(spec=QModelIndex)
        mock_index.isValid.return_value = True
        mock_index.internalPointer.return_value = None

        # Act: Вызываем методы модели
        data_result = model.data(mock_index)
        set_data_result = model.setData(mock_index, "test")

        # Assert: Методы должны возвращать None/False для None объектов
        assert data_result is None
        assert set_data_result is False
