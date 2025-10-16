# creators.py
"""Icon creation functions with async support and thread safety."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt, QThread
from PyQt6.QtGui import QGuiApplication, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

from app.config_data import app_config
from app.utils.ui.qt.gui_exec import is_gui_thread, run_in_gui_thread_async

from ..cache_manager import (
    get_icon,
    record_actual_miss,
    record_not_found,
    set_icon,
)
from ..path_service import (
    metrics_record_disk_load,
    metrics_record_hit,
    metrics_record_miss,
    metrics_record_not_found,
)
from ..validation import (
    InvalidIconError,
    _validate_icon_name,
    is_valid_icon_file,
    validate_theme,
)

logger = logging.getLogger(__name__)


def _ensure_gui_thread(context: str = "") -> bool:
    """Ensure code runs in GUI thread. True if in GUI thread.

    Note:
      QImage and QPainter can be used outside GUI thread for QImage rendering.
      QPixmap and QIcon must only be created in GUI thread.
    """
    if not is_gui_thread():
        try:
            app = QApplication.instance()
            if app:
                logger.debug(
                    "Attempt to execute %s not in GUI thread. Current thread: %s, GUI thread: %s",
                    context,
                    QThread.currentThread(),
                    app.thread(),
                )
                # Defer execution to GUI thread
                # Return False so the calling function can make a decision
                return False
            logger.warning(
                "Attempt to execute %s before QApplication initialization", context
            )
        except (ImportError, RuntimeError):
            logger.warning(
                "Attempt to execute %s before QApplication initialization (ImportError/RuntimeError)",
            )
        return False
    return True


def _create_svg_icon_fast(svg_path: str, size: int) -> QIcon:
    """Fast SVG icon creation for standard sizes using QPixmap directly."""
    try:
        renderer = QSvgRenderer(svg_path)
        if not renderer.isValid():
            return QIcon()

        # Use QPixmap directly for standard sizes - faster than QImage rendering
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter()
        if not painter.begin(pixmap):
            return QIcon()

        # Use faster render hints for standard sizes
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        try:
            renderer.render(painter, QRectF(0, 0, size, size))
            return QIcon(pixmap)
        finally:
            painter.end()

    except Exception:
        # Fall back to original implementation on any error
        return QIcon()


# === SVG ICON CREATION ===


def _create_svg_icon(svg_path: str) -> QIcon:
    """Create QIcon from SVG file.

    Note:
        QImage and QPainter can be used outside GUI thread for QImage rendering.
        QPixmap and QIcon must only be created in GUI thread.
    """
    try:
        renderer = QSvgRenderer(svg_path)
        if not renderer.isValid():
            raise InvalidIconError(f"Invalid SVG file: {svg_path}")

        # Render to QImage instead of QPixmap for thread safety
        # Account for HiDPI: rasterize in physical pixels and set DPR for Pixmap
        base_size = app_config.get_default_icon_size()
        try:
            screen = QGuiApplication.primaryScreen()
            dpr = float(screen.devicePixelRatio()) if screen is not None else 1.0
        except Exception:
            dpr = 1.0

        render_w = max(1, int(round(base_size * dpr)))
        render_h = max(1, int(round(base_size * dpr)))
        image = QImage(
            QSize(render_w, render_h), QImage.Format.Format_ARGB32_Premultiplied
        )
        image.fill(Qt.GlobalColor.transparent)

        painter = QPainter()
        if not painter.begin(image):
            raise InvalidIconError(f"Failed to initialize painter for: {svg_path}")

        # Set render hints for better quality
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        try:
            renderer.render(painter, QRectF(0, 0, render_w, render_h))
            # Convert QImage to QPixmap and set DPR
            pixmap = QPixmap.fromImage(image)
            try:
                pixmap.setDevicePixelRatio(dpr)
            except Exception:
                pass
            return QIcon(pixmap)
        finally:
            painter.end()

    except (OSError, RuntimeError) as exc:
        raise InvalidIconError(
            f"Error creating SVG icon from {svg_path}: {exc}"
        ) from exc
    except Exception as exc:
        raise InvalidIconError(
            f"Unexpected error creating SVG icon from {svg_path}: {exc}"
        ) from exc


async def _create_svg_icon_async(svg_path: str) -> QIcon:
    """Asynchronously create QIcon from SVG file."""
    # QPixmap/QIcon creation must happen in GUI thread
    return await run_in_gui_thread_async(lambda: _create_svg_icon(svg_path))


def _create_icon_from_file_path(file_path: str) -> QIcon:
    """General function for creating high-quality icon from file."""
    path_obj = Path(file_path)

    if path_obj.suffix.lower() == ".svg":
        # Special SVG handling
        try:
            icon = _create_svg_icon(str(path_obj))
            if not icon.isNull():
                return icon
        except InvalidIconError as exc:
            logger.debug("Error creating SVG icon from %s: %s", file_path, exc)

        # Fallback to PNG version of icon
        png_path = path_obj.with_suffix(".png")
        if png_path.exists() and is_valid_icon_file(str(png_path)):
            logger.debug("Falling back to PNG version: %s", png_path)
            return _create_icon_from_file_path(str(png_path))

        return QIcon()
    else:
        # Regular image formats - create QIcon directly
        if path_obj.exists() and is_valid_icon_file(str(path_obj)):
            # Simple icon creation without scaling
            return QIcon(str(path_obj))
        else:
            logger.debug("Invalid or non-existent icon file: %s", path_obj)
            return QIcon()


async def _create_icon_from_file_path_async(file_path: str) -> QIcon:
    """Asynchronous version of general function for creating icon from file."""
    path_obj = Path(file_path)

    if path_obj.suffix.lower() == ".svg":
        # Special SVG handling
        try:
            icon = await _create_svg_icon_async(str(path_obj))
            if not icon.isNull():
                return icon
        except InvalidIconError as exc:
            logger.debug("Error creating SVG icon from %s: %s", file_path, exc)

        # Fallback to PNG version of icon
        png_path = path_obj.with_suffix(".png")
        if png_path.exists() and is_valid_icon_file(str(png_path)):
            logger.debug("Falling back to PNG version: %s", png_path)
            # Create icon strictly in GUI thread
            return await run_in_gui_thread_async(lambda: QIcon(str(png_path)))

        # If PNG version unavailable, return empty icon
        return QIcon()
    else:
        # Regular image formats - create strictly in GUI thread
        return await run_in_gui_thread_async(
            lambda: _create_icon_from_file_path(str(path_obj))
        )


# === MAIN ICON CREATION FUNCTIONS ===
# NOTE: themed_icon() and themed_icon_async() have been removed.
# For UI icons, use the new simplified system: app.utils.ui.icons.get_icon()
# This file now contains only functions for user-provided icons (links, categories, etc.)


def _create_png_icon_fast(file_path: str, target_size: int = 24) -> QIcon:
    """Fast PNG icon creation with size optimization."""
    try:
        path_obj = Path(file_path)

        # For common sizes, try to load and scale efficiently
        if target_size in (16, 24, 32, 48, 64, 128) and path_obj.exists():
            # Create icon with specific size for better performance
            icon = QIcon(str(path_obj))

            # Check if icon was created successfully and has valid sizes
            if not icon.isNull() and len(icon.availableSizes()) > 0:
                return icon

        # Fall back to simple creation
        return QIcon(str(path_obj)) if path_obj.exists() else QIcon()

    except Exception:
        # Fall back to simple creation on any error
        try:
            return QIcon(str(path_obj)) if path_obj.exists() else QIcon()
        except Exception:
            return QIcon()


# === CREATING ICONS FROM ABSOLUTE PATHS ===


def create_icon_from_path(icon_path: str) -> QIcon:
    """Create QIcon from file path with caching."""
    # Thread safety check: QIcon must be created only in the GUI thread
    if not _ensure_gui_thread(f"creating icon from path ({icon_path})"):
        logger.warning(
            "create_icon_from_path called from non-GUI thread for %s, returning empty icon",
            icon_path,
        )
        return QIcon()

    # Use namespaced key to avoid collisions
    cache_key = f"abspath::{icon_path}"
    # Check cache - TTL logic already implemented in cache_manager
    cached_icon = get_icon(cache_key, "__abs__")

    if cached_icon is not None:
        logger.debug("Cache HIT for absolute path icon: %s", icon_path)
        return cached_icon
    logger.debug("Cache MISS for absolute path icon: %s", icon_path)

    # Measure load time
    start_time = time.time()

    # Create new icon with high quality
    exists = Path(icon_path).exists()
    if exists:
        path_obj = Path(icon_path)

        # Use fast loading for PNG files with common sizes
        if path_obj.suffix.lower() in (
            ".png",
            ".jpg",
            ".jpeg",
            ".bmp",
            ".gif",
        ) and app_config.get_default_icon_size() in (16, 24, 32, 48, 64, 128):
            icon = _create_png_icon_fast(icon_path, app_config.get_default_icon_size())
        else:
            icon = _create_icon_from_file_path(icon_path)

        logger.debug("Created high-quality icon from existing file: %s", icon_path)
    else:
        icon = QIcon()
        logger.debug("Created empty icon for non-existent file: %s", icon_path)

    # Measure load time and record successful disk load
    load_time = time.time() - start_time
    metrics_record_disk_load(load_time)

    # Cache result with negative flag for missing files
    set_icon(cache_key, "__abs__", icon, negative=not exists)

    # Log slow operations
    if load_time > 0.1:  # If load took more than 100 ms, log at INFO level
        logger.info(
            "Slow disk load: absolute path icon '%s' took %.2fms",
            icon_path,
            load_time * 1000,
        )
    else:
        logger.debug(
            "Cached icon for absolute path: %s with TTL in %.2fms",
            icon_path,
            load_time * 1000,
        )
    return icon


async def create_icon_from_path_async(icon_path: str) -> QIcon:
    """Asynchronously create QIcon from file path with caching."""
    # Use namespaced key to avoid collisions
    cache_key = f"abspath::{icon_path}"
    # Check cache - TTL logic already implemented in cache_manager
    cached_icon = get_icon(cache_key, "__abs__")

    if cached_icon is not None:
        logger.debug("Cache HIT for absolute path icon: %s", icon_path)
        return cached_icon
    logger.debug("Cache MISS for absolute path icon: %s", icon_path)

    # Measure load time
    start_time = time.time()

    # Asynchronously create new icon
    loop = asyncio.get_event_loop()

    def create_icon():
        if Path(icon_path).exists():
            path_obj = Path(icon_path)

            # Use fast loading for PNG files with common sizes
            if path_obj.suffix.lower() in (
                ".png",
                ".jpg",
                ".jpeg",
                ".bmp",
                ".gif",
            ) and app_config.get_default_icon_size() in (16, 24, 32, 48, 64, 128):
                return _create_png_icon_fast(
                    icon_path, app_config.get_default_icon_size()
                )
            else:
                return QIcon(icon_path)
        else:
            logger.debug("Created empty icon for non-existent file: %s", icon_path)
            return QIcon()

    icon = await loop.run_in_executor(None, create_icon)

    # Measure load time and record successful disk load
    load_time = time.time() - start_time
    metrics_record_disk_load(load_time)

    # Cache result with negative flag for missing files
    set_icon(cache_key, "__abs__", icon, negative=not Path(icon_path).exists())

    # Log slow operations
    if load_time > 0.1:
        logger.info(
            "Slow async disk load: absolute path icon '%s' took %.2fms",
            icon_path,
            load_time * 1000,
        )
    else:
        logger.debug(
            "Cached icon for absolute path: %s with TTL async in %.2fms",
            icon_path,
            load_time * 1000,
        )
    return icon


def _create_icon_from_path_deferred(icon_path: str) -> QIcon:
    """Deferred version of create_icon_from_path for execution in GUI thread."""
    # Use namespaced key to avoid collisions
    cache_key = f"abspath::{icon_path}"
    # Check cache - TTL logic already implemented in cache_manager
    cached_icon = get_icon(cache_key, "__abs__")

    if cached_icon is not None:
        logger.debug("Cache HIT for absolute path icon: %s", icon_path)
        return cached_icon
    logger.debug("Cache MISS for absolute path icon: %s", icon_path)

    # Measure load time
    start_time = time.time()

    # Create new icon
    exists = Path(icon_path).exists()
    if exists:
        path_obj = Path(icon_path)

        # Use fast loading for PNG files with common sizes
        if path_obj.suffix.lower() in (
            ".png",
            ".jpg",
            ".jpeg",
            ".bmp",
            ".gif",
        ) and app_config.get_default_icon_size() in (16, 24, 32, 48, 64, 128):
            icon = _create_png_icon_fast(icon_path, app_config.get_default_icon_size())
        else:
            icon = QIcon(icon_path)
    else:
        logger.warning("Icon file not found: %s", icon_path)
        icon = QIcon()  # Return empty icon if file not found

    # Measure load time and record successful disk load
    load_time = time.time() - start_time
    metrics_record_disk_load(load_time)

    # Cache result with negative flag for missing files
    set_icon(cache_key, "__abs__", icon, negative=not exists)

    # Log slow operations
    if load_time > 0.1:  # If load took more than 100 ms, log at INFO level
        logger.info(
            "Slow disk load: absolute path icon '%s' took %.2fms",
            icon_path,
            load_time * 1000,
        )
    else:
        logger.debug(
            "Cached icon for absolute path: %s with TTL in %.2fms",
            icon_path,
            load_time * 1000,
        )
    return icon
