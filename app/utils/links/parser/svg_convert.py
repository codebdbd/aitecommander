"""SVG to PNG conversion using Qt's QSvgRenderer."""

from __future__ import annotations

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QSize
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer


def convert_svg(svg_data: bytes) -> bytes | None:
    renderer = QSvgRenderer(QByteArray(svg_data))
    if not renderer.isValid():
        return None

    image = QImage(QSize(64, 64), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter()
    try:
        painter.begin(image)
        try:
            renderer.render(painter)
        finally:
            painter.end()
    except Exception:
        return None

    buffer = QBuffer()
    try:
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if image.save(buffer, "PNG"):
            return bytes(buffer.data())
    finally:
        buffer.close()
    return None


__all__ = ["convert_svg"]
