# converters.py
"""Icon conversion functions with async support for I/O operations."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import threading
from pathlib import Path

from PIL import Image
from PIL.Image import Resampling
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSize
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

from ..validation import InvalidIconError, is_valid_icon_file

logger = logging.getLogger(__name__)

_ICON_HASH_CACHE: dict[Path, dict[str, str]] = {}
_ICON_HASH_LOCK = threading.Lock()
_ICON_HASH_CACHE_FILE = ".icon_hash_cache.json"


def _load_icon_hash_cache(dest_dir: Path) -> dict[str, str]:
    dest_path = dest_dir.resolve()
    with _ICON_HASH_LOCK:
        cache = _ICON_HASH_CACHE.get(dest_path)
        if cache is not None:
            return cache
        cache_file = dest_path / _ICON_HASH_CACHE_FILE
        try:
            if cache_file.is_file():
                raw = cache_file.read_text(encoding="utf-8")
                data = json.loads(raw) if raw else {}
                cache = (
                    {str(k): str(v) for k, v in data.items()}
                    if isinstance(data, dict)
                    else {}
                )
            else:
                cache = {}
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug(
                "Failed to load icon hash cache from %s: %s",
                cache_file,
                exc,
                exc_info=True,
            )
            cache = {}
        _ICON_HASH_CACHE[dest_path] = cache
        return cache


def _save_icon_hash_cache(dest_dir: Path, cache: dict[str, str]) -> None:
    dest_path = dest_dir.resolve()
    cache_file = dest_path / _ICON_HASH_CACHE_FILE
    try:
        cache_file.write_text(json.dumps(cache), encoding="utf-8")
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.debug(
            "Failed to persist icon hash cache to %s: %s",
            cache_file,
            exc,
            exc_info=True,
        )


def _update_icon_hash_cache(dest_dir: Path, hash_value: str, filename: str) -> None:
    if not hash_value:
        return
    with _ICON_HASH_LOCK:
        _load_icon_hash_cache(dest_dir)

def _remove_icon_hash_cache_entry(dest_dir: Path, hash_value: str) -> None:
    if not hash_value:
        return
    with _ICON_HASH_LOCK:
        cache = _load_icon_hash_cache(dest_dir)
        if hash_value in cache:
            cache.pop(hash_value, None)
            _save_icon_hash_cache(dest_dir, cache)


def _resize_image(img: Image.Image, size: int) -> Image.Image:
    """Helper function for high-quality image resizing."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img.resize((size, size), Resampling.LANCZOS)


# === SYNCHRONOUS COPY FUNCTIONS ===


def _calculate_file_hash(file_path: Path) -> str:
    """Calculates SHA-256 file hash for duplicate checking."""
    import hashlib

    hash_sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()[
            :16
        ]  # Use first 16 characters for brevity
    except OSError as exc:
        logger.warning("Failed to calculate hash for %s: %s", file_path, exc)
        return ""


def _find_existing_icon_by_content(
    src_path: Path, dest_dir: Path, hash_hint: str | None = None
) -> str | None:
    """Finds existing icon with same content in target directory."""
    if not dest_dir.exists():
        return None

    src_hash = hash_hint or _calculate_file_hash(src_path)
    if not src_hash:
        return None

    cache = _load_icon_hash_cache(dest_dir)
    cached_name = cache.get(src_hash)
    if cached_name:
        candidate = dest_dir / cached_name
        if candidate.is_file():
            return candidate.name
        _remove_icon_hash_cache_entry(dest_dir, src_hash)

    known_filenames = set(cache.values())
    for existing_file in dest_dir.iterdir():
        if not (
            existing_file.is_file()
            and existing_file.suffix.lower()
            in {".png", ".ico", ".svg", ".jpg", ".jpeg"}
        ):
            continue
        if existing_file.name in known_filenames:
            continue
        existing_hash = _calculate_file_hash(existing_file)
        if not existing_hash:
            continue
        _update_icon_hash_cache(dest_dir, existing_hash, existing_file.name)
        if existing_hash == src_hash:
            logger.debug(
                "Found existing icon with same content: %s", existing_file.name
            )
            return existing_file.name

    return None


def copy_icon_smart(  # noqa: C901
    src_path: str, dest_dir: Path, avoid_duplicates: bool = True
) -> str:
    """Smart icon copying with content-based duplicate checking.

    Args:
        src_path: Source icon path
        dest_dir: Destination directory
        avoid_duplicates: If True, checks existing files by content

    Returns:
        str: File name in destination directory
    """
    if not is_valid_icon_file(src_path):
        raise InvalidIconError(
            f"Cannot copy invalid icon file: {src_path}"
        )

    # Create directory if it doesn't exist
    dest_dir.mkdir(parents=True, exist_ok=True)

    src_path_obj = Path(src_path)
    src_hash = _calculate_file_hash(src_path_obj)

    # Check for content-based duplication
    if avoid_duplicates:
        existing_icon = _find_existing_icon_by_content(src_path_obj, dest_dir, src_hash)
        if existing_icon:
            logger.debug("Reusing existing icon: %s", existing_icon)
            return existing_icon

    # If file with this name exists, generate unique name
    dst = dest_dir / src_path_obj.name
    if dst.exists():
        # Generate unique name with suffix
        base_name = src_path_obj.stem
        extension = src_path_obj.suffix
        counter = 1
        while dst.exists():
            dst = dest_dir / f"{base_name}_{counter}{extension}"
            counter += 1

    try:
        shutil.copyfile(src_path_obj, dst)
        logger.debug("Copied icon to: %s", dst.name)
        if src_hash:
            _update_icon_hash_cache(dest_dir, src_hash, dst.name)
    except OSError as exc:
        raise InvalidIconError(f"Error copying file: {exc}") from exc

    # Automatic SVG to PNG conversion when copying
    if src_path_obj.suffix.lower() == ".svg":
        png_dst = dest_dir / (dst.stem + ".png")
        if not png_dst.exists():
            # Convert SVG to PNG 128x128
            if not convert_icon_to_png_128(str(dst), str(png_dst)):
                logger.warning("Failed to convert SVG to PNG: %s -> %s", dst, png_dst)
                # If conversion failed, return original SVG file
                return dst.name
        # Return PNG file name for SVG
        return png_dst.name

    # Auto-convert common rasters to PNG (for unification and plugin independence)
    ext = src_path_obj.suffix.lower()
    if ext in {".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
        png_dst = dest_dir / (dst.stem + ".png")
        if png_dst.exists():
            # If PNG already exists (e.g., previously converted) — use it
            try:
                # Remove just copied source to avoid duplicate storage
                dst.unlink(missing_ok=True)
            except Exception:
                logger.debug("Failed to remove temp copied raster: %s", dst, exc_info=True)
            return png_dst.name

        # Convert raster icon to PNG
        if convert_raster_icon_to_png(str(dst), str(png_dst), size=128):
            try:
                # Remove source after successful conversion
                dst.unlink(missing_ok=True)
            except Exception:
                logger.debug("Failed to remove source raster after conversion: %s", dst, exc_info=True)
            return png_dst.name
        else:
            logger.warning("Failed to convert raster icon to PNG: %s -> %s", dst, png_dst)
            # Return original name if conversion failed
            return dst.name

    return dst.name


def copy_icon(src_path: str, dest_dir: Path) -> str:
    """Copy icon to directory (backward compatibility).

    Uses smart copying with duplicate checking.
    """
    return copy_icon_smart(src_path, dest_dir, avoid_duplicates=True)


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


# === ASYNCHRONOUS COPY FUNCTIONS ===


async def copy_icon_async(src_path: str, dest_dir: Path) -> str:
    """Asynchronously copy icon to directory."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, copy_icon, src_path, dest_dir)


async def copy_icon_to_path_async(src_path: str, dst_path: str) -> bool:
    """Asynchronously copy icon from one path to another."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, copy_icon_to_path, src_path, dst_path)


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
                out.write(bytes(buffer.data()))
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


# === ASYNCHRONOUS CONVERSION FUNCTIONS ===


async def convert_icon_to_png_128_async(
    src_path: str, dst_path: str, size: int = 128
) -> bool:
    """Asynchronously convert icon to PNG of specified size."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, convert_icon_to_png_128, src_path, dst_path, size
    )


async def convert_icon_to_png_32_async(
    src_path: str, dst_path: str, size: int = 32
) -> bool:
    """Asynchronously convert icon to PNG 32x32."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, convert_icon_to_png_32, src_path, dst_path, size
    )


async def convert_raster_icon_to_png_async(
    src_path: str, dst_path: str, size: int = 32
) -> bool:
    """Asynchronously convert raster icon to PNG."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, convert_raster_icon_to_png, src_path, dst_path, size
    )


# === BATCH CONVERSION ===


async def batch_convert_icons_async(
    conversions: list[tuple[str, str, int]], max_concurrent: int = 5
) -> dict[str, bool]:
    """Batch asynchronous icon conversion.

    Args:
        conversions: List of tuples (src_path, dst_path, size)
        max_concurrent: Maximum number of simultaneous conversions

    Returns:
        dict: Dictionary {src_path: success_status}
    """
    # Task queue to avoid creating all coroutines at once
    queue: asyncio.Queue[tuple[str, str, int]] = asyncio.Queue()
    result_dict: dict[str, bool] = {}

    # Pre-fill queue with input tasks
    for item in conversions:
        try:
            src_path, dst_path, size = item
        except Exception:  # protect against invalid input
            logger.error("Invalid conversion tuple: %s", item)
            continue
        queue.put_nowait((src_path, dst_path, size))

    async def worker(worker_id: int) -> None:
        while True:
            try:
                src_path, dst_path, size = await queue.get()
            except asyncio.CancelledError:
                break
            try:
                success = await convert_icon_to_png_128_async(src_path, dst_path, size)
                result_dict[src_path] = success
            except Exception as e:
                logger.error("Batch conversion error for %s: %s", src_path, e)
                result_dict[src_path] = False
            finally:
                queue.task_done()

    # Start limited number of workers
    workers = [
        asyncio.create_task(worker(i)) for i in range(max(1, int(max_concurrent)))
    ]

    # Wait for all tasks in queue to complete
    await queue.join()

    # Stop workers
    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)

    successful = sum(1 for success in result_dict.values() if success)
    logger.info(
        f"Batch conversion completed: {successful}/{len(conversions)} successful"
    )

    return result_dict

