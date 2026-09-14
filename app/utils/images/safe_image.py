from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import IO, Any

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

SAFE_IMAGE_FORMATS: tuple[str, ...] = ("PNG", "ICO", "JPEG", "BMP", "GIF", "WEBP")
DEFAULT_MAX_PIXELS: int = 10_000_000  # 10 Megapixels


def safe_image_open(
    fp: str | Path | IO[bytes],
    *,
    formats: Sequence[str] = SAFE_IMAGE_FORMATS,
    max_pixels: int = DEFAULT_MAX_PIXELS,
    **kwargs: Any,
) -> Image.Image:
    """Safely open an image file/stream using Pillow with strict format and size restrictions.

    Args:
        fp: File path or binary file-like stream.
        formats: Allowed Pillow format decoders (default: PNG, ICO, JPEG, BMP, GIF, WEBP).
                 Explicitly excludes unsafe/heavy formats (PSD, FITS, EPS, JPEG2000, TIFF, etc.).
        max_pixels: Maximum allowed pixel area (width * height).
        **kwargs: Extra arguments forwarded to PIL.Image.open.

    Returns:
        PIL.Image.Image instance.

    Raises:
        UnidentifiedImageError: If the image format is not recognized or not allowed.
        ValueError: If image dimensions exceed max_pixels.
    """
    img = Image.open(fp, formats=formats, **kwargs)
    width, height = img.size
    if max_pixels > 0 and (width * height) > max_pixels:
        img.close()
        raise ValueError(
            f"Image dimensions ({width}x{height} = {width * height} pixels) exceed limit of {max_pixels} pixels"
        )
    return img


def verify_image_safe(
    fp: str | Path | IO[bytes],
    *,
    formats: Sequence[str] = SAFE_IMAGE_FORMATS,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> bool:
    """Verify integrity of an image file/stream without loading full raster into memory."""
    try:
        with safe_image_open(fp, formats=formats, max_pixels=max_pixels) as img:
            img.verify()
        return True
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        logger.debug("Image verification failed for %s: %s", fp, exc)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error during image verification for %s: %s", fp, exc)
        return False
