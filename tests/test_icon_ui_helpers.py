# test_icon_ui_helpers.py
"""Тесты для модуля ui_helpers.py.

Проверяет:
- Установку иконок на кнопки
- Обработку невалидных путей
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QPushButton

from app.utils.ui.icon.ui_helpers import set_icon_to_button


class TestSetIconToButton:
    """Тесты set_icon_to_button."""

    def test_set_valid_icon(self, qapp, tmp_path):
        """Должен устанавливать валидную иконку на кнопку."""
        button = QPushButton()
        
        icon_file = tmp_path / "icon.png"
        icon_file.write_bytes(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        
        set_icon_to_button(button, str(icon_file))
        
        assert not button.icon().isNull()

    def test_set_icon_with_path_object(self, qapp, tmp_path):
        """Должен работать с Path объектом."""
        button = QPushButton()
        
        icon_file = tmp_path / "icon.png"
        icon_file.write_bytes(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        
        set_icon_to_button(button, icon_file)
        
        assert not button.icon().isNull()

    def test_set_invalid_icon(self, qapp, tmp_path):
        """Невалидная иконка должна устанавливать пустую."""
        button = QPushButton()
        
        invalid_file = tmp_path / "invalid.png"
        invalid_file.write_bytes(b"invalid data")
        
        set_icon_to_button(button, str(invalid_file))
        
        assert button.icon().isNull()

    def test_set_nonexistent_icon(self, qapp, tmp_path):
        """Несуществующий файл должен устанавливать пустую иконку."""
        button = QPushButton()
        
        set_icon_to_button(button, str(tmp_path / "nonexistent.png"))
        
        assert button.icon().isNull()

    def test_set_none_icon(self, qapp):
        """None должен устанавливать пустую иконку."""
        button = QPushButton()
        
        set_icon_to_button(button, None)
        
        assert button.icon().isNull()

    def test_set_empty_string_icon(self, qapp):
        """Пустая строка должна устанавливать пустую иконку."""
        button = QPushButton()
        
        set_icon_to_button(button, "")
        
        assert button.icon().isNull()


@pytest.fixture
def qapp():
    """Фикстура для QApplication."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
