from __future__ import annotations

import io
import unittest
from unittest.mock import MagicMock

from PIL import Image

from app.utils.links.parser.icon_downloader import IconDownloader


class TestIconFormatSecurity(unittest.TestCase):
    def test_disallowed_image_formats_are_rejected(self) -> None:
        """Verify that Image.open restricts formats and refuses PSD/TIFF/unallowed decoders."""
        config = MagicMock()
        downloader = IconDownloader(config=config)

        # Create a small TIFF in memory
        buf = io.BytesIO()
        img = Image.new("RGB", (32, 32), color="red")
        img.save(buf, format="TIFF")
        tiff_bytes = buf.getvalue()

        resp = MagicMock()
        resp.headers = {}
        resp.status_code = 200

        # Attempt to process TIFF via _process_and_save_image should fail / reject
        # because TIFF is not in _ALLOWED_IMAGE_FORMATS
        with self.assertRaises(Exception):
            downloader._process_and_save_image(
                tiff_bytes,
                "example.com",
                "https://example.com/icon.tiff",
                resp,
                "image/tiff",
                len(tiff_bytes),
                False,
                {},
            )
