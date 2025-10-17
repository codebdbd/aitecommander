
# converters.py
"""Icon conversion and copying functions (simplified)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from PIL import Image
from PIL.Image import Resampling
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSize
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

from ..validation import InvalidIconError, is_valid_icon_file

logger = logging.getLogger(__name__)


def _resize_image(img: Image.Image, size: int) -> Image.Image:
    """Helper function for high-quality image resizing."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img.resize((size, size), Resampling.LANCZOS)


# === COPY FUNCTIONS ===


def copy_icon_smart(
    src_path: str, dest_dir: Path, avoid_duplicates: bool = False
) -> str:
    """Simple icon copying without auto-conversion.
    
    Args:
        src_path: Source icon path
        dest_dir: Destination directory  
        avoid_duplicates: Ignored (kept for compatibility)
    
    Returns:
        str: File name in destination directory
    """
    if not is_valid_icon_file(src_path):
        raise InvalidIconError(f"Cannot copy invalid icon file: {src_path}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    src_path_obj = Path(src_path)
    
    # Generate unique name if file exists
    dst = dest_dir / src_path_obj.name
    if dst.exists():
        base_name = src_path_obj.stem
        extension = src_path_obj.suffix
        counter = 1
        while dst.exists():
            dst = dest_dir / f"{base_name}_{counter}{extension}"
            counter += 1

    try:
        shutil.copyfile(src_path_obj, dst)
        logger.debug("Copied icon to: %s", dst.name)
    except OSError as exc:
        raise InvalidIconError(f"Error copying file: {exc}") from exc

    return dst.name


def copy_icon(src_path: str, dest_dir: Path) -> str:
    """Copy icon to directory (backward compatibility).

    Simple copying without duplicate checking.
    """
    return copy_icon_smart(src_path, dest_dir, avoid_duplicates=False)


def copy_icon_to_path(src_path: str, dst_path: str) -> bool:
    """Copy icon from one path to another.

    Args:
        src_path: Source icon path
        dst_path: Destination icon path

    Returns:
        bool: True if copy successful, False otherwise.
    """
    try:
        # Create parent directory if it doesn't exist
        dst_path_obj = Path(dst_path)
        dst_path_obj.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(src_path, dst_path)
        logger.debug("Successfully copied icon from %s to %s", src_path, dst_path)
        return True
    except (OSError, shutil.Error) as exc:
        logger.error("Error copying icon from %s to %s: %s", src_path, dst_path, exc)
        return False
    except Exception as exc:
        logger.error(
            "Unexpected error copying icon from %s to %s: %s", src_path, dst_path, exc
        )
        return False




# === SYNCHRONOUS CONVERSION FUNCTIONS ===


def convert_icon_to_png_128(src_path: str, dst_path: str, size: int = 128) -> bool:
    """Convert icon to PNG of specified size (default 128x128).

    Note:
        This function works with QImage and QPainter outside GUI thread, which is acceptable
        for QImage rendering operations. This differs from creating QPixmap/QIcon,
        which must only be created in GUI thread.
    """
    try:
        src_path_obj = Path(src_path)
        ext = src_path_obj.suffix.lower()

        if ext == ".svg":
            # SVG → QImage → PNG (allowed outside GUI thread)
            with open(src_path, "rb") as f:
                svg_data = f.read()

            logger.debug("Creating QSvgRenderer for %s", src_path)
            renderer = QSvgRenderer(QByteArray(svg_data))
            logger.debug("QSvgRenderer isValid: %s", renderer.isValid())
            if not renderer.isValid():
                logger.error("Invalid SVG file: %s", src_path)
                return False

            # Create image with required size and high quality
            image = QImage(QSize(size, size), QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)

            logger.debug("Created QImage with size %dx%d", size, size)
            painter = QPainter()

            if not painter.begin(image):
                logger.error("Failed to initialize QPainter")
                return False

            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            try:
                # Render SVG to image of required size
                logger.debug("Rendering SVG to image with size %dx%d", size, size)
                result = renderer.render(painter, QRectF(0, 0, size, size))
                logger.debug("SVG rendering result: %s", result)
            finally:
                painter.end()

            # Save image to buffer with high quality
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)

            # Use maximum PNG quality
            logger.debug("Saving image to buffer")
            if not image.save(buffer, "PNG", 100):
                logger.error("Failed to save image to buffer")
                return False

            # Create parent directory if it doesn't exist
            dst_path_obj = Path(dst_path)
            dst_path_obj.parent.mkdir(parents=True, exist_ok=True)

            # Write data to file
            logger.debug("Writing image data to %s", dst_path)
            with open(dst_path, "wb") as out:
                out.write(buffer.data().data())
            logger.debug("Successfully converted SVG to PNG: %s", dst_path)
            return True

        # Any other format via PIL
        dst_path_obj = Path(dst_path)
        dst_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(src_path) as img:
            img = _resize_image(img, size)
            img.save(dst_path, format="PNG")
        return True

    except (OSError, ValueError) as exc:
        logger.error("Error converting icon %s: %s", src_path, exc)
        return False
    except Exception as exc:
        logger.error("Unexpected error converting icon %s: %s", src_path, exc)
        return False


def convert_icon_to_png_32(src_path: str, dst_path: str, size: int = 32) -> bool:
    """Convert icon to PNG of specified size (default 32x32).

    Note:
        This is deprecated function for backward compatibility.
        Use convert_icon_to_png_128.
    """
    return convert_icon_to_png_128(src_path, dst_path, size=size)


def convert_raster_icon_to_png(src_path: str, dst_path: str, size: int = 32) -> bool:
    """Convert raster icon to PNG of specified size (default 32x32).

    Args:
        src_path: Source icon path.
        dst_path: Destination icon path (must end with .png).
        size: Icon size (default 32).

    Returns:
        bool: True if conversion successful, False otherwise.
    """
    try:
        with Image.open(src_path) as img:
            # Resize image
            img = _resize_image(img, size)

            # Create parent directory if it doesn't exist
            dst_path_obj = Path(dst_path)
            dst_path_obj.parent.mkdir(parents=True, exist_ok=True)

            # Save as PNG
            img.save(dst_path, "PNG")

        logger.debug(
            "Successfully converted raster icon from %s to %s", src_path, dst_path
        )
        return True
    except (OSError, ValueError) as exc:
        logger.error(
            "Error converting raster icon from %s to %s: %s", src_path, dst_path, exc
        )
        return False
    except Exception as exc:
        logger.error(
            "Unexpected error converting raster icon from %s to %s: %s",
            src_path,
            dst_path,
            exc,
        )
        return False


