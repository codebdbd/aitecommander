import types

from bs4 import BeautifulSoup

from app.utils.links.parser import icon_candidates as ic


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_link_icons_have_higher_priority_than_manifest_and_fallbacks(monkeypatch):
    html = """
    <html><head>
      <link rel="icon" href="/favicon-32.png" sizes="32x32" type="image/png">
      <link rel="manifest" href="/site.webmanifest">
    </head></html>
    """
    soup = _soup(html)

    # manifest with some icon
    m_url = "https://example.com/site.webmanifest"
    m_json = {
        "icons": [{"src": "/icons/m-192.png", "sizes": "192x192", "type": "image/png"}]
    }

    def fake_http_request(url, *a, **kw):
        if url == m_url:
            import json

            return types.SimpleNamespace(ok=True, text=json.dumps(m_json))
        return types.SimpleNamespace(ok=False, text="{}")

    base_url = "https://example.com/page"
    config = types.SimpleNamespace()
    # ensure sync path can fetch manifest without real network
    monkeypatch.setattr(ic, "http_request", fake_http_request)
    urls = ic.find_favicon_candidates(
        soup, base_url, config=config, on_manifest_icons=None, use_external=False
    )

    # First should be the link-icon from HTML, not manifest or fallbacks
    assert urls[0].endswith("/favicon-32.png"), urls


def test_manifest_used_only_when_no_primary_link_icons(monkeypatch):
    html = """
    <html><head>
      <link rel="manifest" href="/site.webmanifest">
    </head></html>
    """
    soup = _soup(html)

    m_url = "https://example.com/site.webmanifest"
    m_json = {
        "icons": [{"src": "/icons/m-48.png", "sizes": "48x48", "type": "image/png"}]
    }

    def fake_http_request(url, *a, **kw):
        if url == m_url:
            import json

            return types.SimpleNamespace(ok=True, text=json.dumps(m_json))
        return types.SimpleNamespace(ok=False, text="{}")

    base_url = "https://example.com/page"
    config = types.SimpleNamespace()
    # ensure sync path can fetch manifest without real network
    monkeypatch.setattr(ic, "http_request", fake_http_request)
    urls = ic.find_favicon_candidates(
        soup, base_url, config=config, on_manifest_icons=None, use_external=False
    )

    assert any(u.endswith("/icons/m-48.png") for u in urls)


def test_fallback_paths_are_added_for_www_and_bare_host():
    soup = _soup("<html><head></head></html>")
    base_url = "https://www.example.com/index"
    urls = ic.find_favicon_candidates(
        soup, base_url, config=None, on_manifest_icons=None, use_external=False
    )

    hosts = {"https://www.example.com/favicon.ico", "https://example.com/favicon.ico"}
    assert hosts.issubset(set(urls))


def test_external_services_added_only_when_flag_true():
    soup = _soup("<html><head></head></html>")
    base_url = "https://example.com/page"

    urls_no = ic.find_favicon_candidates(
        soup, base_url, config=None, on_manifest_icons=None, use_external=False
    )
    assert not any("google.com/s2/favicons" in u for u in urls_no)

    urls_yes = ic.find_favicon_candidates(
        soup, base_url, config=None, on_manifest_icons=None, use_external=True
    )
    assert any("google.com/s2/favicons" in u for u in urls_yes)
    assert any("icons.duckduckgo.com" in u for u in urls_yes)


def test_sorting_prefers_lower_base_priority_then_better_format_then_size_desc():
    html = """
    <html><head>
      <link rel="icon" href="/a.svg" type="image/svg+xml">
      <link rel="icon" href="/b.png" sizes="64x64" type="image/png">
      <link rel="icon" href="/c.png" sizes="32x32" type="image/png">
    </head></html>
    """
    soup = _soup(html)
    base_url = "https://example.com/"
    urls = ic.find_favicon_candidates(
        soup, base_url, config=None, on_manifest_icons=None, use_external=False
    )

    # base_priority equal (0), SVG has better format_rank than PNG, so /a.svg before PNGs
    assert urls[0].endswith("/a.svg"), urls
    # Among PNGs with same base_priority and format_rank, larger size first
    pngs = [u for u in urls if u.endswith(".png")]
    assert pngs[0].endswith("/b.png") and pngs[1].endswith("/c.png"), pngs


def test_og_image_appended_only_when_no_primary_icons():
    html = """
    <html><head>
      <meta property="og:image" content="/images/app-icon-256.png">
    </head></html>
    """
    soup = _soup(html)
    base_url = "https://example.com/"

    # With primary icon present -> og should not be appended
    html2 = """
    <html><head>
      <link rel="icon" href="/favicon.png">
      <meta property="og:image" content="/images/app-icon-256.png">
    </head></html>
    """
    soup2 = _soup(html2)

    urls1 = ic.find_favicon_candidates(
        soup, base_url, config=None, on_manifest_icons=None, use_external=False
    )
    urls2 = ic.find_favicon_candidates(
        soup2, base_url, config=None, on_manifest_icons=None, use_external=False
    )

    assert any("/images/app-icon-256.png" in u for u in urls1)
    assert not any("/images/app-icon-256.png" in u for u in urls2)
