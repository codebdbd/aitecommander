from typing import Optional

from app.utils.links.parser import icon_downloader as mod


class DummyConfig:
    pass


class DummyResp:
    def __init__(self, status: int = 200, headers: Optional[dict] = None, content: bytes = b""):
        self.status_code = status
        self.headers = headers or {}
        self.content = content

    def close(self):
        pass

    def iter_content(self, chunk_size=8192):
        if self.content:
            yield self.content


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

    # Mock underlying GET to return non-image content-type
    def fake_request(method, url, headers=None, timeout=None, stream=None, allow_redirects=True):
        assert method == "GET"
        return DummyResp(200, {"Content-Type": "text/html; charset=utf-8"}, b"<html></html>")

    monkeypatch.setattr(mod.http_session, "request", fake_request)

    result = mod.save_icon("https://example.com/favicon", "example.com", DummyConfig())

    assert result is None
