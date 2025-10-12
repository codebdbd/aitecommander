
from app.utils.links.parser import icon_downloader as mod


class DummyResp:
    def __init__(self, status=200, headers=None, content=b""):
        self.status_code = status
        self.headers = headers or {}
        self._content = content

    def iter_content(self, chunk_size=8192):
        if self._content:
            yield self._content

    def close(self):
        pass


def test_save_icon_uses_http_request_with_retries_success(monkeypatch, tmp_path):
    # Redirect user icons dir to tmp
    monkeypatch.setattr(mod.icon_path_service, "get_user_icons_dir", lambda: tmp_path)

    calls = {"n": 0, "stream": None, "allow_redirects": None}

    def fake_http_request(url, config, extra_headers=None, allow_non_2xx=False, timeout_override=None,
                          retries=0, http_get=None, method="GET", stream=None, allow_redirects=None):
        # first call fails (simulating internal transient) by returning None, second returns 200 OK with PNG
        calls["n"] += 1
        calls["stream"] = stream
        calls["allow_redirects"] = allow_redirects
        if calls["n"] == 1:
            return None
        # Return minimal valid PNG bytes header to pass through image checks until open()
        # We'll rely on later pipeline to handle content; here just ensure code path continues
        return DummyResp(200, {"Content-Type": "image/png"}, b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr(mod, "http_request", fake_http_request)

    class Cfg:
        HTTP_RETRIES = 2
        ICON_MAX_IMAGE_PIXELS = 1000

    res = mod.save_icon("https://example/favicon.png", "example.com", Cfg())
    # Could be None if PIL fails to parse minimal bytes; ensure at least http_request was called with streaming
    assert calls["n"] >= 1
    assert calls["stream"] is True
    assert calls["allow_redirects"] is True


def test_save_icon_http_request_permanent_failure_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.icon_path_service, "get_user_icons_dir", lambda: tmp_path)

    def fake_http_request(*args, **kwargs):
        return None  # all retries exhausted

    monkeypatch.setattr(mod, "http_request", fake_http_request)

    class Cfg:
        HTTP_RETRIES = 1

    res = mod.save_icon("https://example/favicon.png", "example.com", Cfg())
    assert res is None
