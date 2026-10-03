from __future__ import annotations

import importlib
from collections import Counter, OrderedDict
from concurrent.futures import CancelledError, ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.models.workers.icon_refresh_worker import IconRefreshWorker
from app.utils.links.parser import fetcher
from app.utils.links.parser.favicon_cache import FaviconCache, FaviconLockTimeoutError


@pytest.fixture(params=[False, True], ids=["open-per-write", "persistent"])
def storage(monkeypatch, request):
    module = importlib.import_module("app.utils.links.parser.favicon_cache")
    counts = Counter()

    class Shelf(dict):
        def __setitem__(self, key, value):
            counts[f"write:{key}"] += 1
            super().__setitem__(key, value)

        def sync(self):
            counts["sync"] += 1

        def close(self):
            counts["close"] += 1

    shelf = Shelf()

    def open_db(path):
        counts["open"] += 1
        return shelf

    @contextmanager
    def lock(path):
        counts["lock"] += 1
        yield

    monkeypatch.setattr(module, "_open_shelve_with_recovery", open_db)
    monkeypatch.setattr(module, "_ensure_cache_storage_ready_once", lambda: None)
    monkeypatch.setattr(module, "_file_lock", lock)
    cache = FaviconCache()
    cache._persistent_enabled = request.param
    cache._get_db_path = lambda: "unused-batch-cache"
    cache._now = lambda: 1000.0
    cache._get_max_size = lambda: 5000
    cache._cleanup_interval_sec = 30.0
    yield cache, shelf, counts
    cache.close()


def test_set_many_uses_one_open_index_write_and_sync(storage):
    cache, shelf, counts = storage
    cache.set_many({str(i): {"title": str(i), "ttl": 60} for i in range(50)})
    assert counts["open"] == counts["lock"] == counts["sync"] == 1
    assert counts["write:__ts_index__"] == 1
    assert len(shelf["__ts_index__"]) == 50
    assert shelf["49"]["title"] == "49"
    assert counts["close"] == (0 if cache._persistent_enabled else 1)


def test_empty_batch_does_not_access_storage(storage):
    cache, shelf, counts = storage
    cache.set_many({})
    with cache.batch():
        pass
    assert not counts


def test_batch_flushes_at_limit_and_on_exit(storage):
    cache, shelf, counts = storage
    with cache.batch(max_size=2) as writer:
        writer.write("a", {"ttl": 60})
        assert not counts
        writer.write("b", {"ttl": 60})
        assert counts["sync"] == 1
        writer.write("c", {"ttl": 60})
        assert "c" not in shelf
    assert counts["sync"] == 2
    assert set(shelf["__ts_index__"]) == {"a", "b", "c"}


def test_batch_preserves_timestamps_ttl_and_latest_value(storage):
    cache, shelf, counts = storage
    with cache.batch() as writer:
        writer.write("a", {"title": "old", "ttl": 60})
        cache._now = lambda: 1005.0
        writer.write("a", {"title": "latest", "ttl": 15})
        data = {"title": "copy", "timestamp": 1003.0, "ttl": 60}
        writer.write("b", data)
        data["title"] = "mutated"
        cache._now = lambda: 1010.0
    assert shelf["a"] == {"title": "latest", "timestamp": 1005.0, "ttl": 15.0}
    assert shelf["b"]["title"] == "copy"
    assert shelf["b"]["timestamp"] == 1003.0
    cache._now = lambda: 1021.0
    assert cache.get("a") is None
    assert cache.get("b")["title"] == "copy"


def test_set_many_cleans_expired_and_enforces_capacity(storage):
    cache, shelf, counts = storage
    cache._get_max_size = lambda: 2
    shelf["expired"] = {"timestamp": 1.0, "ttl": 10}
    shelf["__ts_index__"] = OrderedDict([("expired", 1.0)])
    cache.set_many({
        "old": {"timestamp": 990.0, "ttl": 60},
        "new": {"timestamp": 995.0, "ttl": 60},
        "newest": {"timestamp": 999.0, "ttl": 60},
    })
    assert set(shelf["__ts_index__"]) == {"new", "newest"}
    assert "expired" not in shelf and "old" not in shelf
    assert counts["sync"] == 1


def test_cancellation_flushes_completed_results_and_allows_late_writes(storage):
    cache, shelf, counts = storage
    with pytest.raises(CancelledError):
        with cache.batch() as writer:
            writer.write("completed", {"ttl": 60})
            raise CancelledError()
    assert "completed" in shelf
    writer.write("late", {"ttl": 60})
    assert "late" in shelf
    writer.close()
    assert counts["write:completed"] == counts["write:late"] == 1


def test_batch_is_thread_safe_and_does_not_capture_regular_writes(storage):
    cache, shelf, counts = storage
    with cache.batch(max_size=100) as writer:
        with ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(lambda i: writer.write(str(i), {"ttl": 60}), range(50)))
        assert not counts
        cache.set("direct", {"ttl": 60})
        assert "direct" in shelf and "0" not in shelf
        index_writes_before_flush = counts["write:__ts_index__"]
    assert len(shelf["__ts_index__"]) == 51
    assert counts["write:__ts_index__"] == index_writes_before_flush + 1


def test_batch_timeout_never_opens_storage(storage, monkeypatch):
    cache, shelf, counts = storage
    module = importlib.import_module("app.utils.links.parser.favicon_cache")

    @contextmanager
    def lock(path):
        raise FaviconLockTimeoutError()
        yield

    monkeypatch.setattr(module, "_file_lock", lock)
    with cache.batch() as writer:
        writer.write("a", {"ttl": 60})
    assert not shelf and not counts


def test_flush_failure_does_not_mask_original_exception(storage, monkeypatch):
    cache, shelf, counts = storage
    monkeypatch.setattr(cache, "set_many", Mock(side_effect=OSError("disk full")))
    with pytest.raises(ValueError, match="original"):
        with cache.batch(max_size=2) as writer:
            writer.write("a", {"ttl": 60})
            raise ValueError("original")
    assert not writer._pending


def test_partial_write_failure_preserves_index_for_completed_entries(storage, monkeypatch):
    cache, shelf, counts = storage
    original_set = type(shelf).__setitem__

    def failing_set(self, key, value):
        if key == "bad":
            raise OSError("disk full")
        original_set(self, key, value)

    monkeypatch.setattr(type(shelf), "__setitem__", failing_set)
    with pytest.raises(OSError, match="disk full"):
        cache.set_many({"good": {"ttl": 60}, "bad": {"ttl": 60}, "later": {"ttl": 60}})
    assert list(shelf["__ts_index__"]) == ["good"]
    assert "good" in shelf and "later" not in shelf
    assert counts["sync"] == 1


def test_set_many_explicit_ttl_overrides_entry_ttl(storage):
    cache, shelf, counts = storage
    cache.set_many({"a": {"ttl": 600}, "b": {"title": "B"}}, ttl=10)
    assert shelf["a"]["ttl"] == shelf["b"]["ttl"] == 10


def test_batches_are_independent(storage):
    cache, shelf, counts = storage
    with cache.batch() as outer:
        outer.write("outer", {"ttl": 60})
        with cache.batch() as inner:
            inner.write("inner", {"ttl": 60})
        assert "inner" in shelf and "outer" not in shelf
    assert "outer" in shelf


def test_set_many_real_shelve_roundtrip(tmp_path, monkeypatch):
    module = importlib.import_module("app.utils.links.parser.favicon_cache")
    monkeypatch.setattr(module, "_ensure_cache_storage_ready_once", lambda: None)
    cache = FaviconCache()
    cache._persistent_enabled = False
    cache._get_db_path = lambda: str(tmp_path / "batch.db")
    with cache.batch() as writer:
        writer.write("https://a.example", {"title": "A", "ttl": 60})
        writer.write("https://b.example", {"title": "B", "ttl": 60})
    assert cache.get("https://a.example")["title"] == "A"
    assert cache.get("https://b.example")["title"] == "B"


def test_fetcher_routes_result_to_batch_writer(monkeypatch):
    monkeypatch.setattr(fetcher, "_check_cache", lambda *args: None)
    monkeypatch.setattr(fetcher, "_get_existing_icon_path", lambda *args: "")
    monkeypatch.setattr(fetcher, "resolve_icon_for_link", lambda *args: "default.png")
    monkeypatch.setattr(fetcher, "get_provider_title_fast", lambda *args: "")
    monkeypatch.setattr(fetcher, "_is_host_temporarily_unreachable", lambda *args: True)
    immediate = Mock(side_effect=AssertionError("unexpected direct write"))
    monkeypatch.setattr(fetcher, "write_cache", immediate)
    writer = Mock()
    config = SimpleNamespace()
    result = fetcher.fetch_web_link_info("https://a.example/page", config, cache_writer=writer)
    writer.assert_called_once_with("https://a.example/page", result, config)
    immediate.assert_not_called()


def test_refresh_worker_batches_parallel_results(storage, monkeypatch):
    cache, shelf, counts = storage
    module = importlib.import_module("app.models.workers.icon_refresh_worker")
    monkeypatch.setattr(module, "favicon_cache", cache)
    links = [{"id": i + 1, "url": f"https://{i}.example", "type": "web"} for i in range(5)]
    worker = IconRefreshWorker(SimpleNamespace(), batch_size=3, delay_ms=0)
    monkeypatch.setattr(worker, "_get_default_icon_path", lambda: "default.png")
    monkeypatch.setattr(worker, "_find_links_with_default_icons", lambda path: links)
    monkeypatch.setattr(worker, "_is_default_icon", lambda *args: True)
    monkeypatch.setattr(worker, "_commit_updates", Mock())

    def fetch(url, config, **kwargs):
        result = {"icon": "downloaded.png", "ttl": 60}
        kwargs["cache_writer"](url, result, config)
        return result

    monkeypatch.setattr(module, "fetch_web_link_info", fetch)
    errors = []
    worker.signals.error.connect(errors.append)
    worker.run()
    assert not errors
    assert len(shelf["__ts_index__"]) == 5
    assert counts["sync"] == 2
    assert counts["write:__ts_index__"] == 2
