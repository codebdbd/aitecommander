from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.utils.links.parser.fetcher import (
    _fetch_and_parse_html,
    _refetch_html_for_icon,
)


class TestFaviconFetcherSizeLimit(unittest.TestCase):
    @patch("app.utils.links.parser.fetcher.http_request")
    def test_fetch_and_parse_html_skips_non_html_and_closes_stream(self, mock_http: MagicMock) -> None:
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "application/pdf"}
        mock_http.return_value = resp

        soup, status = _fetch_and_parse_html("https://example.com/doc.pdf", None, 5.0)

        self.assertIsNone(soup)
        self.assertEqual(status, 200)
        self.assertTrue(mock_http.call_args.kwargs.get("stream"))
        resp.close.assert_called_once()
        resp.iter_content.assert_not_called()

    @patch("app.utils.links.parser.fetcher.http_request")
    def test_fetch_and_parse_html_limits_oversized_body(self, mock_http: MagicMock) -> None:
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        chunk = b"<p>data</p>" * 5000
        resp.iter_content.return_value = [chunk for _ in range(60)]
        resp.encoding = "utf-8"
        mock_http.return_value = resp

        soup, status = _fetch_and_parse_html("https://example.com/huge.html", None, 5.0)

        self.assertIsNotNone(soup)
        self.assertEqual(status, 200)
        self.assertTrue(mock_http.call_args.kwargs.get("stream"))
        resp.close.assert_called_once()

    @patch("app.utils.links.parser.fetcher.http_request")
    def test_refetch_html_for_icon_uses_stream_and_closes(self, mock_http: MagicMock) -> None:
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "text/html"}
        resp.iter_content.return_value = [b"<html><link rel=\"icon\" href=\"/favicon.ico\"></html>"]
        resp.encoding = "utf-8"
        mock_http.return_value = resp

        soup = _refetch_html_for_icon("https://example.com/", None)

        self.assertIsNotNone(soup)
        self.assertTrue(mock_http.call_args.kwargs.get("stream"))
        resp.close.assert_called_once()
