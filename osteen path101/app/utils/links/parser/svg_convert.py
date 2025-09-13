"""SVG to PNG conversion using Qt's QSvgRenderer."""

from __future__ import annotations

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSize
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

from .constants import TARGET_SIZE


def convert_svg(svg_data: bytes, target_size: int | None = None) -> bytes | None:
    renderer = QSvgRenderer(QByteArray(svg_data))
    if not renderer.isValid():
        return None

    # Определяем целевой размер и исходный размер SVG
    ts = int(target_size or TARGET_SIZE or 64)
    if ts <= 0:
        ts = 64
    base_size = renderer.defaultSize()
    bw = max(1, int(base_size.width()) if base_size.isValid() else 64)
    bh = max(1, int(base_size.height()) if base_size.isValid() else 64)

    # Масштабируем пропорционально, вписывая в квадрат ts x ts
    scale = min(ts / bw, ts / bh)
    dw = max(1, int(round(bw * scale)))
    dh = max(1, int(round(bh * scale)))
    # Центрируем растеризованный результат в квадрате ts x ts
    offset_x = (ts - dw) // 2
    offset_y = (ts - dh) // 2

    image = QImage(QSize(ts, ts), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter()
    # Важно: проверяем успешность begin(), иначе QPainter останется неактивным
    if not painter.begin(image):
        return None
    try:
        # Качество рендера
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        # Рендерим в прямоугольник нужного размера с сохранением пропорций
        target_rect = QRectF(float(offset_x), float(offset_y), float(dw), float(dh))
        renderer.render(painter, target_rect)
    finally:
        painter.end()

    buffer = QBuffer()
    try:
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if image.save(buffer, "PNG"):
            return bytes(buffer.data())
    finally:
        buffer.close()
    return None


__all__ = ["convert_svg"]
