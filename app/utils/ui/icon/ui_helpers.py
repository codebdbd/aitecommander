"""
UI утилиты для работы с иконками.
Функции для установки иконок на UI элементы.
"""
from pathlib import Path
from typing import Union

from PyQt6.QtGui import QIcon

from .icon_operations.creators import create_icon_from_path
from .validation import is_valid_icon_file


def set_icon_to_button(button, icon_path: Union[str, Path]) -> None:
    """
    Установить высококачественную иконку на кнопку.
    
    Args:
        button: Кнопка для установки иконки
        icon_path: Путь к файлу иконки
    """
    if icon_path and is_valid_icon_file(icon_path):
        icon = create_icon_from_path(str(icon_path))
        button.setIcon(icon)
    else:
        button.setIcon(QIcon())  # Пустая иконка
