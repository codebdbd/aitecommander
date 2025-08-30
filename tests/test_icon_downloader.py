from typing import Optional

from app.utils.links.parser import icon_downloader as mod


class DummyConfig:
    pass


class DummyResp:
    def __init__(self, status: int = 200, headers: Optional[dict] = None, content: bytes = b""):
        self.status_code = status
        self.headers = headers or {}
        self.content = content


def test_read_write_meta_roundtrip(tmp_path, monkeypatch):
    # Redirect user icons dir to tmp
    monkeypatch.setattr(mod.icon_path_service, "get_user_icons_dir", lambda: tmp_path)

    domain = "example.com"
    meta = {"etag": "W/\"123\"", "last_modified": "Thu, 01 Jan 1970 00:00:00 GMT", "saved_at": 0.0}

    mod.write_icon_meta(domain, meta)
    loaded = mod.read_icon_meta(domain)

    assert loaded.get("etag") == meta["etag"]
    assert loaded.get("last_modified") == meta["last_modified"]


def test_save_icon_rejects_non_image_head(monkeypatch, tmp_path):
    # Redirect user icons dir to tmp
    monkeypatch.setattr(mod.icon_path_service, "get_user_icons_dir", lambda: tmp_path)

    calls = {"n": 0}

    def fake_http_request(url, config, extra_headers=None, allow_non_2xx=False, timeout_override=None, retries=0, http_get=None, method="GET"):
        calls["n"] += 1
        if method == "HEAD":
            # Non-image content-type to trigger skip at HEAD
            return DummyResp(200, {"Content-Type": "text/html; charset=utf-8"})
        # Would not be reached for this test
        return DummyResp(200, {"Content-Type": "image/png"}, b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr(mod, "http_request", fake_http_request)

    result = mod.save_icon("https://example.com/favicon", "example.com", DummyConfig())

    assert result is None
    assert calls["n"] >= 1
