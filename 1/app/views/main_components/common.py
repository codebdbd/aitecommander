from PyQt6.QtGui import QFont


def create_font(point_size: int) -> QFont:
    """Создать и вернуть QFont с указанным размером."""
    font = QFont()
    font.setPointSize(point_size)
    return font
