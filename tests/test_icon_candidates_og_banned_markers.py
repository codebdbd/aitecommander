import types

from bs4 import BeautifulSoup

from app.utils.links.parser import icon_candidates as ic


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_og_image_banned_markers_filtering():
    html = """
    <html><head>
      <meta property="og:image" content="https://example.com/banner-icon.png">
      <meta property="og:image:secure_url" content="/site-icon.png">
    </head><body></body></html>
    """
    soup = _soup(html)

    base_url = "https://example.com/"

    # No primary link-icons in HTML; og should be considered.
    # Ensure no real HTTP or manifests are involved regardless of future changes.
    # Explicitly pass config=None and on_manifest_icons=None.
    urls = ic.find_favicon_candidates(
        soup,
        base_url,
        config=None,
        on_manifest_icons=None,
        use_external=False,
    )

    # '/banner-icon.png' contains banned marker 'banner' and must be filtered out
    assert "https://example.com/banner-icon.png" not in urls

    # '/site-icon.png' is allowed (contains 'icon' and no banned markers)
    assert "https://example.com/site-icon.png" in urls
