from __future__ import annotations

import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from app.utils.links.parser.icon_candidates import find_favicon_candidates
from app.utils.links.parser.icon_downloader import pick_icon_parallel
from app.utils.links.parser.svg_convert import convert_svg


class _DummyConfig:
    HTTP_RETRIES = 0
    ICON_PICK_MAX_SECONDS = 2.0


class _ManifestResponse:
    ok = True
    text = (
        '{"icons": [{"src": "/assets/icon-192.png", "sizes": "192x192", '
        '"type": "image/png"}]}'
    )


class _HtmlResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def close(self) -> None:
        return None


class TestIconCandidateDiscovery(unittest.TestCase):
    def test_declared_external_svg_icon_is_ranked_before_fallbacks(self) -> None:
        soup = BeautifulSoup(
            """
            <html>
              <head>
                <link rel="icon" type="image/svg+xml" href="https://cdn.example.com/icon.svg">
              </head>
            </html>
            """,
            "html.parser",
        )

        urls = find_favicon_candidates(
            soup,
            "https://gemini.example.com/chat",
            _DummyConfig(),
        )

        self.assertGreater(len(urls), 1)
        self.assertEqual("https://cdn.example.com/icon.svg", urls[0])
        self.assertIn("https://gemini.example.com/favicon.svg", urls)

    def test_common_root_manifest_locations_are_used(self) -> None:
        soup = BeautifulSoup("<html><head></head></html>", "html.parser")

        def _fake_http_request(url, *_args, **_kwargs):
            if url == "https://example.com/site.webmanifest":
                return _ManifestResponse()
            return None

        with patch(
            "app.utils.links.parser.icon_candidates.http_request",
            side_effect=_fake_http_request,
        ):
            urls = find_favicon_candidates(
                soup,
                "https://example.com/deep/page",
                _DummyConfig(),
            )

        self.assertIn("https://example.com/assets/icon-192.png", urls)

    def test_pick_icon_parallel_retries_homepage_root_after_empty_page_candidates(self) -> None:
        soup = BeautifulSoup("<html><head></head><body></body></html>", "html.parser")
        config = _DummyConfig()

        homepage_html = """
        <html>
          <head>
            <link rel="icon" type="image/svg+xml" href="/static/home-icon.svg">
          </head>
        </html>
        """

        def _fake_try_candidates(candidates, *_args, **_kwargs):
            if "https://example.com/static/home-icon.svg" in candidates:
                return "/tmp/home-icon.png"
            return None

        with (
            patch(
                "app.utils.links.parser.icon_downloader.find_favicon_candidates",
                side_effect=[
                    [],
                    ["https://example.com/static/home-icon.svg"],
                ],
            ) as candidates_mock,
            patch(
                "app.utils.links.parser.icon_downloader.http_request",
                return_value=_HtmlResponse(homepage_html),
            ) as http_request_mock,
            patch(
                "app.utils.links.parser.icon_downloader._try_candidates_parallel_impl",
                side_effect=_fake_try_candidates,
            ),
            patch(
                "app.utils.links.parser.icon_downloader._try_external_candidates",
                return_value=None,
            ),
            patch(
                "app.utils.links.parser.icon_downloader._phase3_try_www_variant",
                return_value=None,
            ),
            patch(
                "app.utils.links.parser.icon_downloader._phase4_google_api",
                return_value=None,
            ),
        ):
            saved = pick_icon_parallel(
                soup,
                "https://example.com/app/chat",
                "example.com",
                config,
            )

        self.assertEqual("/tmp/home-icon.png", saved)
        self.assertEqual(2, candidates_mock.call_count)
        http_request_mock.assert_called_once_with(
            "https://example.com/",
            config,
            allow_non_2xx=True,
            timeout_override=(5, 8),
            retries=2,
            method="GET",
            stream=False,
            allow_redirects=True,
        )

    def test_embedded_raster_svg_can_be_converted(self) -> None:
        svg_with_embedded_raster = b"""
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">
          <image href="data:image/jpeg;base64,AAAA" width="192" height="192"/>
        </svg>
        """

        result = convert_svg(svg_with_embedded_raster, target_size=64)
        self.assertIsNotNone(result)
        self.assertGreater(len(result), 0)


if __name__ == "__main__":
    unittest.main()
