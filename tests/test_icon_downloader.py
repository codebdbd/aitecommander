from typing import Optional
import time

from app.utils.links.parser import icon_downloader as mod


class DummyConfig:
    pass


class DummyResp:
    def __init__(
        self, status: int = 200, headers: Optional[dict] = None, content: bytes = b""
    ):
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
    meta = {
        "etag": 'W/"123"',
        "last_modified": "Thu, 01 Jan 1970 00:00:00 GMT",
        "saved_at": 0.0,
    }

    mod.write_icon_meta(domain, meta)
    loaded = mod.read_icon_meta(domain)

    assert loaded.get("etag") == meta["etag"]
    assert loaded.get("last_modified") == meta["last_modified"]


def test_save_icon_rejects_non_image_head(monkeypatch, tmp_path):
    # Redirect user icons dir to tmp
    monkeypatch.setattr(mod.icon_path_service, "get_user_icons_dir", lambda: tmp_path)

    # Mock underlying GET to return non-image content-type via get_session().request
    class _DummySession:
        def request(self, method, url, headers=None, timeout=None, stream=None, allow_redirects=True):
            assert method == "GET"
            return DummyResp(
                200, {"Content-Type": "text/html; charset=utf-8"}, b"<html></html>"
            )

    monkeypatch.setattr(mod, "get_session", lambda: _DummySession())

    result = mod.save_icon("https://example.com/favicon", "example.com", DummyConfig())

    assert result is None


# === New tests for parallel picking and shared executor ===

def _reset_icon_executor():
    # Best-effort reset to avoid cross-test leakage
    try:
        ex = getattr(mod, "_ICON_EXECUTOR", None)
        if ex is not None:
            try:
                ex.shutdown(wait=False, cancel_futures=True)  # type: ignore[arg-type]
            except TypeError:
                ex.shutdown(wait=False)
    finally:
        setattr(mod, "_ICON_EXECUTOR", None)


def test_pick_icon_parallel_first_success(monkeypatch, tmp_path):
    _reset_icon_executor()
    # Redirect user icons dir to tmp
    monkeypatch.setattr(mod.icon_path_service, "get_user_icons_dir", lambda: tmp_path)

    # Prepare candidates: slow, fast, slow
    urls = [
        "https://a/slow1.png",
        "https://b/fast.png",
        "https://c/slow2.png",
    ]
    monkeypatch.setattr(mod, "find_favicon_candidates", lambda soup, page_url, config, use_external=False: urls)

    calls = {"slow1": 0, "fast": 0, "slow2": 0}

    def _fake_save_icon(u, domain, config, is_fallback, force_refresh):
        if "slow1" in u:
            calls["slow1"] += 1
            time.sleep(0.2)
            return None
        if "fast" in u:
            calls["fast"] += 1
            return str(tmp_path / "web_example_com.png")
        if "slow2" in u:
            calls["slow2"] += 1
            time.sleep(0.2)
            return None
        return None

    monkeypatch.setattr(mod, "save_icon", _fake_save_icon)

    class Cfg:
        ICON_PICK_MAX_SECONDS = 2.0
        ICON_MAX_WORKERS = 3

    start = time.monotonic()
    result = mod.pick_icon_parallel(None, "https://example/", "example.com", Cfg())
    elapsed = time.monotonic() - start

    assert result is not None
    # Должно завершиться быстро, без ожидания медленных задач
    assert elapsed < 0.5
    # Убедимся, что быстрый кандидат действительно вызывался
    assert calls["fast"] >= 1


def test_pick_icon_parallel_respects_deadline(monkeypatch, tmp_path):
    _reset_icon_executor()
    # Redirect user icons dir to tmp
    monkeypatch.setattr(mod.icon_path_service, "get_user_icons_dir", lambda: tmp_path)

    urls = [f"https://example/{i}.png" for i in range(5)]
    monkeypatch.setattr(mod, "find_favicon_candidates", lambda soup, page_url, config, use_external=False: urls)

    def _slow_save_icon(u, domain, config, is_fallback, force_refresh):
        time.sleep(0.3)
        return None

    monkeypatch.setattr(mod, "save_icon", _slow_save_icon)

    class Cfg:
        ICON_PICK_MAX_SECONDS = 0.25
        ICON_MAX_WORKERS = 5

    start = time.monotonic()
    result = mod.pick_icon_parallel(None, "https://example/", "example.com", Cfg())
    elapsed = time.monotonic() - start

    assert result is None
    # Дедлайн ~0.25с, допускаем небольшой перерасход на планирование, но не более 0.6с
    assert elapsed < 0.6


def test_shared_executor_singleton(monkeypatch):
    _reset_icon_executor()
    ex1 = mod._get_icon_executor(2)
    ex2 = mod._get_icon_executor(4)
    assert ex1 is ex2
