from __future__ import annotations

import unittest
from unittest.mock import patch

from app.utils.links.parser.title_parser import get_title


class _DummyConfig:
    HTML_FETCH_TIMEOUT = 1.0
    HTML_FETCH_RETRIES = 5
    USE_PLAYWRIGHT_FOR_TITLE = False
    USE_SELENIUM_FOR_TITLE = False
    USER_AGENT = "test-agent"


class _FakeResponse:
    def __init__(self, text: str, content_type: str = "text/html; charset=utf-8") -> None:
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"Content-Type": content_type}
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"


class TestTitleParserNetworkPolicy(unittest.TestCase):
    def test_get_title_uses_single_get_without_head_preflight(self) -> None:
        calls = []

        def _fake_http_request(url, config, **kwargs):
            calls.append((url, kwargs))
            return _FakeResponse("<html><title>Example Title</title></html>")

        with (
            self.assertLogs("favicon_parser", level="INFO") as logs_cm,
            patch(
                "app.utils.links.parser.title_parser.http_request",
                side_effect=_fake_http_request,
            ),
        ):
            title = get_title("https://example.com", _DummyConfig())

        self.assertEqual("Example Title", title)
        self.assertEqual(1, len(calls))
        self.assertEqual("GET", calls[0][1].get("method", "GET"))
        self.assertEqual(1, calls[0][1].get("retries"))
        self.assertTrue(
            any("[title] done url=https://example.com extracted='Example Title' mode=http_get" in msg for msg in logs_cm.output)
        )

    def test_get_title_honors_zero_retry_configuration(self) -> None:
        calls = []
        config = _DummyConfig()
        config.HTML_FETCH_RETRIES = 0

        def _fake_http_request(url, config, **kwargs):
            calls.append(kwargs)
            return _FakeResponse("<html><title>Zero Retry</title></html>")

        with patch(
            "app.utils.links.parser.title_parser.http_request",
            side_effect=_fake_http_request,
        ):
            title = get_title("https://example.com", config)

        self.assertEqual("Zero Retry", title)
        self.assertEqual(0, calls[0]["retries"])

    def test_get_title_skips_non_html_get_response(self) -> None:
        with (
            self.assertLogs("favicon_parser", level="INFO") as logs_cm,
            patch(
                "app.utils.links.parser.title_parser.http_request",
                return_value=_FakeResponse("binary", content_type="image/png"),
            ),
        ):
            title = get_title("https://example.com/file.png", _DummyConfig())

        self.assertEqual("example.com", title)
        self.assertTrue(
            any("[title][fetch] result=non_html url=https://example.com/file.png type=image/png" in msg for msg in logs_cm.output)
        )


if __name__ == "__main__":
    unittest.main()
