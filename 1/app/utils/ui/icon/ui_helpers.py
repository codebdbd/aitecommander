"""
UI utilities for working with icons.
Functions for setting icons on UI elements.
"""

from pathlib import Path
from typing import Union

from PyQt6.QtGui import QIcon

from .icon_operations.creators import create_icon_from_path
from .validation import is_valid_icon_file


def set_icon_to_button(button, icon_path: Union[str, Path]) -> None:
    """
    Set a high-quality icon on a button.

    Args:
        button: Button to set the icon on
        icon_path: Path to the icon file
    """
    if icon_path and is_valid_icon_file(icon_path):
        icon = create_icon_from_path(str(icon_path))
        button.setIcon(icon)
    else:
        button.setIcon(QIcon())  # Empty icon
