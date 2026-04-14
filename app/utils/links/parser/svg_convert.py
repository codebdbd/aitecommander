"""SVG to PNG conversion using Qt's QSvgRenderer with caching."""

from __future__ import annotations

import hashlib
import threading

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSize
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

from .constants import TARGET_SIZE

# Thread-safe cache for converted SVGs (max 100 entries)
_svg_cache: dict[str, bytes | None] = {}
_svg_cache_lock = threading.Lock()
_SVG_CACHE_MAX_SIZE = 100


def _compute_svg_cache_key(svg_data: bytes, target_size: int) -> str:
    """Compute cache key from SVG data hash and target size."""
    h = hashlib.sha256(svg_data).hexdigest()[:16]
    return f"{h}_{target_size}"


def _convert_svg_impl(svg_data: bytes, target_size: int) -> bytes | None:
    """Internal SVG conversion implementation (not cached)."""
    renderer = QSvgRenderer(QByteArray(svg_data))
    if not renderer.isValid():
        return None

    # Use provided target_size (already validated by caller)
    ts = target_size
    base_size = renderer.defaultSize()
    bw = max(1, int(base_size.width()) if base_size.isValid() else 64)
    bh = max(1, int(base_size.height()) if base_size.isValid() else 64)

    # Scale proportionally to fit within ts x ts square
    scale = min(ts / bw, ts / bh)
    dw = max(1, int(round(bw * scale)))
    dh = max(1, int(round(bh * scale)))
    # Center rendered result within ts x ts square
    offset_x = (ts - dw) // 2
    offset_y = (ts - dh) // 2

    image = QImage(QSize(ts, ts), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter()
    # Important: check begin() success, otherwise QPainter remains inactive
    if not painter.begin(image):
        return None
    try:
        # Render quality
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        # Render into rectangle of required size while preserving proportions
        target_rect = QRectF(float(offset_x), float(offset_y), float(dw), float(dh))
        renderer.render(painter, target_rect)
    finally:
        painter.end()

    buffer = QBuffer()
    try:
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if image.save(buffer, "PNG"):
            return buffer.data().data()
    finally:
        buffer.close()
    return None


def convert_svg(svg_data: bytes, target_size: int | None = None) -> bytes | None:
    """Convert SVG to PNG with caching.
    
    Cache is based on SHA256 hash of SVG data + target size.
    Max cache size is 100 entries (LRU eviction).
    """
    ts = int(target_size or TARGET_SIZE or 64)
    if ts <= 0:
        ts = 64
    
    # Check cache first
    cache_key = _compute_svg_cache_key(svg_data, ts)
    with _svg_cache_lock:
        if cache_key in _svg_cache:
            return _svg_cache[cache_key]
    
    # Convert SVG
    result = _convert_svg_impl(svg_data, ts)
    
    # Store in cache with LRU eviction
    with _svg_cache_lock:
        if len(_svg_cache) >= _SVG_CACHE_MAX_SIZE:
            # Remove oldest entry (first key)
            try:
                first_key = next(iter(_svg_cache))
                _svg_cache.pop(first_key, None)
            except (StopIteration, RuntimeError):
                pass
        _svg_cache[cache_key] = result
    
    return result


__all__ = ["convert_svg"]
