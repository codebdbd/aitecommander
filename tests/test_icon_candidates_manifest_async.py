import types
import threading
from bs4 import BeautifulSoup

from app.utils.links.parser import icon_candidates as ic


class DummyResp:
    def __init__(self, ok: bool, text: str):
        self.ok = ok
        self.text = text


class _ImmediateFuture:
    def __init__(self, result=None):
        self._result = result

    def result(self, *args, **kwargs):
        return self._result


class _DummySyncExecutor:
    def submit(self, fn, *args, **kwargs):
        # Execute task immediately for deterministic testing
        return _ImmediateFuture(fn(*args, **kwargs))

    def shutdown(self, *args, **kwargs):
        pass


def test_manifest_async_merges_urls_and_excludes_from_main_result(monkeypatch):
    # HTML with two manifest links and no primary icon links
    html = """
    <html>
      <head>
        <link rel="manifest" href="/site.webmanifest">
        <link rel="manifest" href="/alt.webmanifest">
      </head>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    base_url = "https://example.com/page"

    # Prepare fake manifests with different icons
    m1_url = "https://example.com/site.webmanifest"
    m2_url = "https://example.com/alt.webmanifest"
    # Include a duplicate icon across two manifests to ensure dedup works and order preserved
    m1_json = {
        "icons": [
            {"src": "/icons/a-32.png", "sizes": "32x32", "type": "image/png"},
            {"src": "/icons/common.png", "sizes": "64x64", "type": "image/png"},
        ]
    }
    m2_json = {
        "icons": [
            {"src": "/icons/common.png", "sizes": "64x64", "type": "image/png"},
            {"src": "/icons/b-48.png", "sizes": "48x48", "type": "image/png"}
        ]
    }

    def fake_http_request(url, *args, **kwargs):
        import json
        if url == m1_url:
            return DummyResp(True, json.dumps(m1_json))
        if url == m2_url:
            return DummyResp(True, json.dumps(m2_json))
        return DummyResp(False, "{}")

    # Patch http and make manifest executor synchronous
    monkeypatch.setattr(ic, "http_request", fake_http_request)
    monkeypatch.setattr(ic, "_get_manifest_executor", lambda: _DummySyncExecutor())

    # Prepare callback and synchronization
    done = threading.Event()
    received = {}

    def on_manifest_icons(urls):
        # Save received urls as a list to check order and deduplication
        received["urls"] = list(urls)
        done.set()

    config = types.SimpleNamespace()

    # Run function — should schedule async processing and return quickly
    main_urls = ic.find_favicon_candidates(
        soup,
        base_url,
        config=config,
        on_manifest_icons=on_manifest_icons,
        use_external=False,
    )

    # Wait for callback (immediate due to DummySyncExecutor)
    assert done.is_set(), "Callback was not called synchronously as expected in test"

    expected_ordered = [
        "https://example.com/icons/a-32.png",
        "https://example.com/icons/common.png",
        "https://example.com/icons/b-48.png",
    ]
    assert expected_ordered == received.get("urls", []), (
        f"Callback did not receive combined unique manifest icons in order: {received}"
    )

    # Ensure main result does NOT contain manifest icon URLs (async path only emits via callback)
    assert not set(expected_ordered).intersection(set(main_urls)), (
        f"Main result should not include async manifest icons: {main_urls}"
    )
