import logging
import types

from bs4 import BeautifulSoup

from app.utils.links.parser import icon_candidates as ic


class DummyResp:
    def __init__(self, ok: bool, text: str):
        self.ok = ok
        self.text = text


def _make_html_with_manifest():
    return BeautifulSoup(
        """
        <html>
          <head>
            <link rel=\"manifest\" href=\"/site.webmanifest\">
          </head>
          <body></body>
        </html>
        """,
        "html.parser",
    )


def test_logs_warning_when_manifest_fetch_fails_sync(monkeypatch, caplog):
    soup = _make_html_with_manifest()
    base_url = "https://example.com/page"

    # http_request raises exception -> should log a warning "Failed to fetch manifest ... (sync)"
    def fake_http_request(url, *args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(ic, "http_request", fake_http_request)

    config = types.SimpleNamespace()

    caplog.set_level(logging.WARNING)
    ic.find_favicon_candidates(
        soup, base_url, config=config, on_manifest_icons=None, use_external=False
    )

    assert any(
        "Failed to fetch manifest" in rec.getMessage() and "(sync)" in rec.getMessage()
        for rec in caplog.records
    ), "Expected warning log about failing to fetch manifest (sync)"


def test_logs_warning_when_manifest_json_parse_fails_sync(monkeypatch, caplog):
    soup = _make_html_with_manifest()
    base_url = "https://example.com/page"

    # http_request returns ok=True but invalid JSON -> should log a warning "Failed to parse manifest JSON ... (sync)"
    def fake_http_request(url, *args, **kwargs):
        return DummyResp(True, "{not json}")

    monkeypatch.setattr(ic, "http_request", fake_http_request)

    config = types.SimpleNamespace()

    caplog.set_level(logging.WARNING)
    ic.find_favicon_candidates(
        soup, base_url, config=config, on_manifest_icons=None, use_external=False
    )

    assert any(
        "Failed to parse manifest JSON" in rec.getMessage()
        and "(sync)" in rec.getMessage()
        for rec in caplog.records
    ), "Expected warning log about failing to parse manifest JSON (sync)"


class _DummySyncExecutor:
    def submit(self, fn, *args, **kwargs):
        # Run immediately in the same thread to make logs visible in this test
        return _ImmediateFuture(fn(*args, **kwargs))

    def shutdown(self, *args, **kwargs):
        pass


class _ImmediateFuture:
    def __init__(self, result):
        self._result = result

    def result(self, *args, **kwargs):
        return self._result


def test_logs_warning_when_manifest_fetch_fails_async(monkeypatch, caplog):
    soup = _make_html_with_manifest()
    base_url = "https://example.com/page"

    def fake_http_request(url, *args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(ic, "http_request", fake_http_request)

    # Force async path by providing on_manifest_icons
    def on_manifest_icons(urls):
        return None

    # Make manifest executor run tasks synchronously
    monkeypatch.setattr(ic, "_get_manifest_executor", lambda: _DummySyncExecutor())

    caplog.set_level(logging.WARNING)
    ic.find_favicon_candidates(
        soup,
        base_url,
        config=types.SimpleNamespace(),
        on_manifest_icons=on_manifest_icons,
        use_external=False,
    )

    assert any(
        "Failed to fetch manifest" in rec.getMessage()
        and "(sync)" not in rec.getMessage()
        for rec in caplog.records
    ), "Expected warning log about failing to fetch manifest (async)"


def test_logs_warning_when_manifest_json_parse_fails_async(monkeypatch, caplog):
    soup = _make_html_with_manifest()
    base_url = "https://example.com/page"

    def fake_http_request(url, *args, **kwargs):
        return DummyResp(True, "{bad json}")

    monkeypatch.setattr(ic, "http_request", fake_http_request)

    def on_manifest_icons(urls):
        return None

    monkeypatch.setattr(ic, "_get_manifest_executor", lambda: _DummySyncExecutor())

    caplog.set_level(logging.WARNING)
    ic.find_favicon_candidates(
        soup,
        base_url,
        config=types.SimpleNamespace(),
        on_manifest_icons=on_manifest_icons,
        use_external=False,
    )

    assert any(
        "Failed to parse manifest JSON" in rec.getMessage()
        and "(sync)" not in rec.getMessage()
        for rec in caplog.records
    ), "Expected warning log about failing to parse manifest JSON (async)"
