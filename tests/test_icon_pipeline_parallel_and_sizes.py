import time

from app.utils.links.parser import icon_downloader as icon_dl
from app.utils.links.parser.icon_candidates import parse_icon_size


def test_parse_icon_size_multiple_and_any():
    # multiple sizes -> max by larger side
    assert parse_icon_size("16x16 32x32 180x180") == 180
    assert parse_icon_size("72x36 36x72") == 72
    # any -> 0
    assert parse_icon_size("any") == 0
    # weird formats -> fallback to first int
    assert parse_icon_size("size-64 something") == 64
    # empty/None -> 0
    assert parse_icon_size("") == 0


def test_pil_max_pixels_context_restores(monkeypatch):
    # Access private context manager
    ctx = getattr(icon_dl, "_pil_max_pixels")
    from PIL import Image

    # Capture original
    had_attr = hasattr(Image, "MAX_IMAGE_PIXELS")

    # Ensure deterministic start
    orig = getattr(Image, "MAX_IMAGE_PIXELS", None)

    # Enter context with a custom limit
    with ctx(123456):
        assert getattr(Image, "MAX_IMAGE_PIXELS", None) == 123456
    # After exit, restored
    if had_attr:
        assert getattr(Image, "MAX_IMAGE_PIXELS", None) == orig
    else:
        assert not hasattr(Image, "MAX_IMAGE_PIXELS")


def test_pick_icon_parallel_timeout_quick_return(monkeypatch):
    # Prepare: small timeout and multiple slow tasks
    class Cfg:
        ICON_PICK_MAX_SECONDS = 0.2
        ICON_MAX_WORKERS = 8
        ICON_USE_EXTERNAL = False

    # Candidates to trigger parallel executor
    candidates = [f"https://example.com/icon{i}.png" for i in range(8)]

    # Monkeypatch find_favicon_candidates to return our candidates only one time
    monkeypatch.setattr(icon_dl, "find_favicon_candidates", lambda *args, **kwargs: candidates)

    # Monkeypatch save_icon to be slow and return None (simulate slow network)
    def slow_save_icon(*args, **kwargs):
        time.sleep(1.0)
        return None

    monkeypatch.setattr(icon_dl, "save_icon", slow_save_icon)

    start = time.monotonic()
    res = icon_dl.pick_icon_parallel(soup=None, page_url="https://example.com", domain="example.com", config=Cfg())
    elapsed = time.monotonic() - start

    assert res is None
    # Should return much earlier than sum of task durations due to timeout cancellation
    assert elapsed < 0.8, f"pick_icon_parallel took too long: {elapsed:.3f}s"
