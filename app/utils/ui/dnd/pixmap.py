# app/utils/dnd/pixmap.py
"""Shared drag pixmap builders used across the app.

Provides small, readable functions to render drag previews for
single-row and multi-row selections.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap


def create_text_pixmap(text: str, single_row: bool = True) -> QPixmap:
    """Create a styled pixmap with text."""
    font = QFont()
    font.setPointSize(9)

    if single_row:
        bg_color = QColor(240, 240, 240, 200)
        text_color = QColor(50, 50, 50)
        border_color = QColor(150, 150, 150)
    else:
        bg_color = QColor(100, 150, 200, 200)
        text_color = QColor(255, 255, 255)
        border_color = QColor(70, 120, 170)

    metrics = QFontMetrics(font)
    text_rect = metrics.boundingRect(text)

    padding = 8
    width = max(40, text_rect.width() + padding * 2)
    height = max(20, text_rect.height() + padding * 2)

    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.setBrush(bg_color)
    painter.setPen(border_color)
    painter.drawRoundedRect(0, 0, width, height, 4, 4)

    painter.setFont(font)
    painter.setPen(text_color)
    painter.drawText(padding, padding + metrics.ascent(), text)

    painter.end()
    return pixmap


def create_multi_row_pixmap(count: int) -> QPixmap:
    return create_text_pixmap(f"{count} элементов", single_row=False)


def create_default_pixmap() -> QPixmap:
    return create_text_pixmap("Перемещение...", single_row=True)
