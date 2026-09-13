from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.utils.links.parser.title_parser import _fetch_and_parse_html


class TestTitleParserSizeLimit(unittest.TestCase):
    @patch("app.utils.links.parser.title_parser.http_request")
    def test_non_html_content_type_skipped_and_closed(self, mock_http_request: MagicMock) -> None:
        resp = MagicMock()
        resp.headers = {"Content-Type": "application/octet-stream"}
        mock_http_request.return_value = resp

        soup, txt = _fetch_and_parse_html("https://example.com/file.bin", None, None, None)

        self.assertIsNone(soup)
        self.assertEqual(txt, "")
        resp.close.assert_called_once()
        resp.iter_content.assert_not_called()

    @patch("app.utils.links.parser.title_parser.http_request")
    def test_oversized_html_truncated(self, mock_http_request: MagicMock) -> None:
        resp = MagicMock()
        resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        # Generates chunks of 64KB up to 5MB
        chunk = b"A" * 65536
        resp.iter_content.return_value = [chunk for _ in range(80)]
        resp.encoding = "utf-8"
        resp.content = b"".join(resp.iter_content.return_value)
        resp.text = "<html><head><title>Huge Page</title></head><body>Large</body></html>"
        mock_http_request.return_value = resp

        soup, txt = _fetch_and_parse_html("https://example.com/huge.html", None, None, None)

        self.assertIsNotNone(soup)
        self.assertLessEqual(len(resp._content), 2097152 + 65536)
        resp.close.assert_called_once()
