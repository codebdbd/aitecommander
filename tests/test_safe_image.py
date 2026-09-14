from __future__ import annotations

import io

import pytest
from PIL import Image, UnidentifiedImageError

from app.utils.images.safe_image import (
    SAFE_IMAGE_FORMATS,
    safe_image_open,
    verify_image_safe,
)


def _make_image_bytes(fmt: str, size: tuple[int, int] = (16, 16)) -> bytes:
    buf = io.BytesIO()
    mode = "RGB" if fmt in ("JPEG", "BMP") else "RGBA"
    img = Image.new(mode, size, color=(255, 0, 0) if mode == "RGB" else (255, 0, 0, 255))
    img.save(buf, format=fmt)
    return buf.getvalue()


def test_safe_formats_accepted() -> None:
    for fmt in ["PNG", "JPEG", "BMP", "GIF", "WEBP"]:
        blob = _make_image_bytes(fmt)
        with safe_image_open(io.BytesIO(blob)) as img:
            assert img.format.upper() in SAFE_IMAGE_FORMATS
        assert verify_image_safe(io.BytesIO(blob)) is True


def test_disallowed_formats_rejected() -> None:
    # TIFF is a valid Pillow format, but NOT in SAFE_IMAGE_FORMATS
    tiff_bytes = _make_image_bytes("TIFF")
    with pytest.raises(UnidentifiedImageError):
        safe_image_open(io.BytesIO(tiff_bytes))
    assert verify_image_safe(io.BytesIO(tiff_bytes)) is False


def test_max_pixels_enforced() -> None:
    # 20x20 = 400 pixels; with max_pixels=200 it should raise ValueError
    blob = _make_image_bytes("PNG", size=(20, 20))
    with pytest.raises(ValueError, match="exceed limit"):
        safe_image_open(io.BytesIO(blob), max_pixels=200)

    # Within limit should succeed
    with safe_image_open(io.BytesIO(blob), max_pixels=500) as img:
        assert img.size == (20, 20)


def test_corrupted_blob_rejected() -> None:
    corrupted = b"not an image at all"
    with pytest.raises(UnidentifiedImageError):
        safe_image_open(io.BytesIO(corrupted))
    assert verify_image_safe(io.BytesIO(corrupted)) is False
