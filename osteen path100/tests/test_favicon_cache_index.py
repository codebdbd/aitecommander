import time as _time

import time
from app.utils.links.parser import favicon_cache as mod


def _set_tmp_icons_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.icon_path_service, "get_user_icons_dir", lambda: tmp_path)


def _read_index(db_path):
    import shelve

    with shelve.open(str(db_path)) as db:
        return db.get("__ts_index__") or {}


def test_index_updates_on_set_and_invalidate(monkeypatch, tmp_path):
    _set_tmp_icons_dir(monkeypatch, tmp_path)
    cache = mod.FaviconCache()

    # Ensure monotonic timestamps by monkeypatching time.time used in module
    base = _time.time()
    tvals = [base + i for i in range(3)]
    it = iter(tvals)
    monkeypatch.setattr(mod.time, "time", lambda: next(it))

    cache.set("k1", {"icon": "a.png"})
    cache.set("k2", {"icon": "b.png"})
    cache.set("k3", {"icon": "c.png"})

    db_path = tmp_path / "favicon_cache.db"
    idx = _read_index(db_path)
    # Order should be insertion order: k1, k2, k3
    assert list(idx.keys()) == ["k1", "k2", "k3"]

    # Invalidate k2 and ensure it disappears from index
    cache.invalidate("k2")
    idx2 = _read_index(db_path)
    assert "k2" not in idx2
    assert list(idx2.keys()) == ["k1", "k3"]


def test_cleanup_uses_index_to_evict_oldest(monkeypatch, tmp_path):
    _set_tmp_icons_dir(monkeypatch, tmp_path)
    cache = mod.FaviconCache()

    # Max size = 2 and allow immediate cleanup
    monkeypatch.setattr(mod.app_config, "get_favicon_cache_max_size", lambda: 2, raising=False)
    cache._cleanup_interval_sec = 0.0  # type: ignore[attr-defined]

    base = _time.time()
    times = [base + i for i in range(3)]
    it = iter(times)
    monkeypatch.setattr(mod.time, "time", lambda: next(it))

    cache.set("a", {"icon": "a.png"})
    cache.set("b", {"icon": "b.png"})
    cache.set("c", {"icon": "c.png"})  # should trigger cleanup and evict oldest 'a'

    db_path = tmp_path / "favicon_cache.db"
    idx = _read_index(db_path)
    assert list(idx.keys()) == ["b", "c"]


def test_get_removes_expired_updates_index(monkeypatch, tmp_path):
    _set_tmp_icons_dir(monkeypatch, tmp_path)
    cache = mod.FaviconCache(default_ttl=0.05)

    cache.set("x", {"icon": "x.png"})
    time.sleep(0.08)

    # Expired -> get should remove from DB and index
    assert cache.get("x") is None

    db_path = tmp_path / "favicon_cache.db"
    idx = _read_index(db_path)
    assert "x" not in idx


def test_index_recovers_from_inconsistencies(monkeypatch, tmp_path):
    _set_tmp_icons_dir(monkeypatch, tmp_path)
    cache = mod.FaviconCache()

    # Allow immediate cleanup
    cache._cleanup_interval_sec = 0.0  # type: ignore[attr-defined]

    # Deterministic time
    base = _time.time()
    times = [base + i for i in range(3)]
    it = iter(times)
    monkeypatch.setattr(mod.time, "time", lambda: next(it))

    cache.set("k1", {"icon": "a.png"})
    cache.set("k2", {"icon": "b.png"})

    # Corrupt the index: add ghost key and stale reference to deleted key
    import shelve
    db_path = tmp_path / "favicon_cache.db"
    with shelve.open(str(db_path)) as db:
        idx = db.get("__ts_index__") or {}
        # Remove k1 from DB to simulate stale index entry
        if "k1" in db:
            del db["k1"]
        # Add ghost and keep k1 in index
        idx["k1"] = base - 100
        idx["ghost"] = base - 200
        db["__ts_index__"] = idx

    # Next set should trigger cleanup and fix index
    cache.set("k3", {"icon": "c.png"})

    idx2 = _read_index(db_path)
    # Index must not contain non-existent keys
    assert "ghost" not in idx2
    assert "k1" not in idx2  # was removed from DB
    # Existing keys remain
    assert "k2" in idx2 and "k3" in idx2
