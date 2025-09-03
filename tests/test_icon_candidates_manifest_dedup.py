import json
import types
from bs4 import BeautifulSoup

from app.utils.links.parser import icon_candidates as ic


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_manifest_deduplicated_requests(monkeypatch):
    # Two identical manifest links should result in a single HTTP request
    html = """
    <html><head>
      <link rel="manifest" href="/app.webmanifest">
      <link rel="manifest" href="/app.webmanifest">
    </head></html>
    """
    soup = _soup(html)
    base_url = "https://example.com/page"

    calls = {"count": 0, "urls": []}

    def fake_http_request(url, config, allow_non_2xx=True):
        calls["count"] += 1
        calls["urls"].append(url)
        # Return minimal valid manifest
        return types.SimpleNamespace(ok=True, text=json.dumps({"icons": [{"src": "/icon.png"}]}))

    monkeypatch.setattr(ic, "http_request", fake_http_request)

    # Use sync path (on_manifest_icons=None) to avoid executor/threading complexity
    ic.find_favicon_candidates(
        soup,
        base_url,
        config=types.SimpleNamespace(),
        on_manifest_icons=None,
        use_external=False,
    )

    assert calls["count"] == 1
    assert calls["urls"] == ["https://example.com/app.webmanifest"]
