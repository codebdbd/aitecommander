import types

from bs4 import BeautifulSoup

from app.utils.links.parser import icon_candidates as ic


class DummyResp:
    def __init__(self, ok: bool, text: str):
        self.ok = ok
        self.text = text


def test_multiple_manifest_links_are_merged(monkeypatch):
    # HTML with two manifest links and no primary icon links
    html = """
    <html>
      <head>
        <link rel="manifest" href="/site.webmanifest">
        <link rel="manifest" href="/alt.webmanifest">
      </head>
      <body></body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    base_url = "https://example.com/page"

    # Prepare fake manifests with different icons
    m1_url = "https://example.com/site.webmanifest"
    m2_url = "https://example.com/alt.webmanifest"
    m1_json = {
        "icons": [
            {"src": "/icons/a-32.png", "sizes": "32x32", "type": "image/png"},
            {"src": "/icons/a-64.png", "sizes": "64x64", "type": "image/png"},
        ]
    }
    m2_json = {
        "icons": [
            {"src": "/icons/b-48.png", "sizes": "48x48", "type": "image/png"}
        ]
    }

    def fake_http_request(url, config=None, allow_non_2xx=False, **kwargs):
        if url == m1_url:
            import json
            return DummyResp(True, json.dumps(m1_json))
        if url == m2_url:
            import json
            return DummyResp(True, json.dumps(m2_json))
        return DummyResp(False, "{}")

    monkeypatch.setattr(ic, "http_request", fake_http_request)

    # Minimal config object
    config = types.SimpleNamespace()

    urls = ic.find_favicon_candidates(soup, base_url, config=config, on_manifest_icons=None, use_external=False)

    # Expect icons from BOTH manifests present
    expected_urls = {
        "https://example.com/icons/a-32.png",
        "https://example.com/icons/a-64.png",
        "https://example.com/icons/b-48.png",
    }
    assert expected_urls.issubset(set(urls)), f"Missing some manifest icons: {expected_urls - set(urls)}"

    # Ensure no duplication
    assert len(urls) == len(set(urls))
