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
from app.utils.ui.icon.inflight import (
    enter_async,
    enter_sync,
    leave_async_error,
    leave_async_success,
    leave_sync,
)
from app.utils.ui.qt.gui_exec import is_gui_thread, run_in_gui_thread_async

from ..cache_manager import (
    get_icon,
    record_actual_miss,
    record_disk_load,
    record_not_found,
    set_icon,
)
from ..path_service import (
    get_icon_path,
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


def themed_icon(icon_name: str, theme: str = "light", source: str = "unknown") -> QIcon:
    """Create QIcon with caching and SVG support."""
    # Thread safety check: QIcon must be created only in the GUI thread
    if not _ensure_gui_thread(f"creating themed_icon ({icon_name})"):
        logger.warning(
            "themed_icon called from non-GUI thread for %s, returning empty icon",
            icon_name,
        )
        return QIcon()

    # Parameter validation
    if not _validate_icon_name(icon_name):
        logger.warning("Invalid icon name provided from %s", source)
        return QIcon()

    theme = validate_theme(theme)

    # Check cache
    cached_icon = get_icon(icon_name, theme)
    if cached_icon is not None:
        try:
            metrics_record_hit()
        finally:
            pass
        return cached_icon

    # Start measuring load time
    start_time = time.time()

    # In-flight deduplication (sync)
    key = (icon_name, theme)
    leader, ev = enter_sync(key)
    if not leader:
        ev.wait()
        cached_after = get_icon(icon_name, theme)
        return cached_after if cached_after is not None else QIcon()

    try:
        # Get icon path
        path = get_icon_path(icon_name, theme)
        if not path:
            # File not found - record miss and cache negative entry
            load_time = time.time() - start_time
            record_actual_miss(load_time)
            record_not_found()
            logger.debug(
                "Icon not found: %s (theme: %s, source: %s)", icon_name, theme, source
            )
            # Cache empty icon as negative to make repeated requests
            # quickly return result before short TTL expires
            set_icon(icon_name, theme, None, negative=True)
            return QIcon()

        # Use common icon creation function
        icon = _create_icon_from_file_path(path)

        # Measure load time and record successful disk load
        load_time = time.time() - start_time
        metrics_record_disk_load(load_time)
        # Cache the result
        set_icon(icon_name, theme, icon)
        if (
            load_time > 0.1
        ):  # If load took more than 100 ms, log at INFO level
            logger.info(
                "Slow disk load: icon '%s' for theme '%s' took %.2fms",
                icon_name,
                theme,
                load_time * 1000,
            )
        else:
            logger.debug(
                "Loaded and cached icon '%s' for theme '%s' in %.2fms",
                icon_name,
                theme,
                load_time * 1000,
            )
        return icon

    except InvalidIconError as exc:
        # Measure failed load time
        load_time = time.time() - start_time
        metrics_record_not_found(load_time)

        logger.error("Error creating icon '%s' from %s: %s", icon_name, source, exc)
        # Cache empty icon with negative=True flag and separate TTL
        set_icon(icon_name, theme, None, negative=True)
        return QIcon()
    except Exception as exc:
        # Measure failed load time
        load_time = time.time() - start_time
        metrics_record_miss(load_time)

        logger.error(
            "Unexpected error creating icon '%s' from %s: %s", icon_name, source, exc
        )
        # Cache empty icon with negative=True flag and separate TTL
        set_icon(icon_name, theme, None, negative=True)
        return QIcon()
    finally:
        leave_sync(key)


async def themed_icon_async(
    icon_name: str, theme: str = "light", source: str = "unknown"
) -> QIcon:
    """Asynchronously create QIcon with caching and SVG support."""
    # Parameter validation
    if not _validate_icon_name(icon_name):
        logger.warning("Invalid icon name provided from %s", source)
        return QIcon()

    theme = validate_theme(theme)

    # Check cache (synchronously, as this is a fast operation)
    cached_icon = get_icon(icon_name, theme)
    if cached_icon is not None:
        try:
            metrics_record_hit()
        finally:
            pass
        return cached_icon

    # Start measuring load time
    start_time = time.time()

    # In-flight deduplication (async)
    akey = (icon_name, theme)
    leader, fut = enter_async(akey)
    if not leader:
        try:
            icon_res = await fut
        except Exception:
            return QIcon()
        cached_after = get_icon(icon_name, theme)
        return (
            cached_after
            if cached_after is not None
            else (icon_res if icon_res is not None else QIcon())
        )

    try:
        # Asynchronously get icon path
        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(None, get_icon_path, icon_name, theme)
        if not path:
            load_time = time.time() - start_time
            metrics_record_not_found(load_time)
            logger.debug(
                "Icon not found: %s (theme: %s, source: %s)", icon_name, theme, source
            )
            leave_async_success(akey, None)
            return QIcon()

        # Use common asynchronous icon creation function
        icon = await _create_icon_from_file_path_async(path)

        # Measure load time and record successful disk load
        load_time = time.time() - start_time
        metrics_record_disk_load(load_time)

        # Cache the result
        set_icon(icon_name, theme, icon)
        if load_time > 0.1:
            logger.info(
                "Slow async disk load: icon '%s' for theme '%s' took %.2fms",
                icon_name,
                theme,
                load_time * 1000,
            )
        else:
            logger.debug(
                "Loaded and cached icon '%s' for theme '%s' async in %.2fms",
                icon_name,
                theme,
                load_time * 1000,
            )
        leave_async_success(akey, icon)
        return icon

    except InvalidIconError as exc:
        # Measure failed load time
        load_time = time.time() - start_time
        record_actual_miss(load_time)
        record_not_found()

        logger.error(
            "Error creating async icon '%s' from %s: %s", icon_name, source, exc
        )
        # Cache empty icon with negative=True flag and separate TTL
        set_icon(icon_name, theme, None, negative=True)
        leave_async_error(akey, exc)
        return QIcon()
    except Exception as exc:
        # Measure failed load time
        load_time = time.time() - start_time
        record_actual_miss(load_time)
        record_not_found()

        logger.error(
            "Unexpected error creating async icon '%s' from %s: %s",
            icon_name,
            source,
            exc,
        )
        # Cache empty icon with negative=True flag and separate TTL
        set_icon(icon_name, theme, None, negative=True)
        leave_async_error(akey, exc)
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
        icon = _create_icon_from_file_path(icon_path)
        logger.debug("Created high-quality icon from existing file: %s", icon_path)
    else:
        icon = QIcon()
        logger.debug("Created empty icon for non-existent file: %s", icon_path)

    # Measure load time and record successful disk load
    load_time = time.time() - start_time
    record_disk_load()

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
            return QIcon(icon_path)
        else:
            logger.debug("Created empty icon for non-existent file: %s", icon_path)
            return QIcon()

    icon = await loop.run_in_executor(None, create_icon)

    # Measure load time and record successful disk load
    load_time = time.time() - start_time
    record_disk_load()

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
        icon = QIcon(icon_path)
    else:
        logger.warning("Icon file not found: %s", icon_path)
        icon = QIcon()  # Return empty icon if file not found

    # Measure load time and record successful disk load
    load_time = time.time() - start_time
    record_disk_load()

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

