import json
import time

import app.utils.browser.browser_profiles.persistent_cache as pc_mod
from app.utils.browser.browser_profiles import PersistentProfileCache


def _patch_cache_path(monkeypatch, tmp_path):
    test_path = tmp_path / "profiles_cache.json"
    monkeypatch.setattr(pc_mod, "get_cache_path", lambda: test_path, raising=True)
    return test_path


def test_expired_entry_removed_from_memory_and_disk(monkeypatch, tmp_path):
    cache_path = _patch_cache_path(monkeypatch, tmp_path)

    cache = PersistentProfileCache(default_ttl=0.1)
    key = "chrome"
    val = [{"id": "Default"}]

    # Set and ensure persisted
    cache.set(key, val)
    cache.flush()
    assert cache.get(key) == val
    assert cache_path.exists()
    with cache_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert key in data

    # Let it expire
    time.sleep(0.2)

    # Access triggers cleanup: should return None and remove from disk
    assert cache.get(key) is None
    cache.flush()

    with cache_path.open("r", encoding="utf-8") as f:
        data_after = json.load(f)
    assert key not in data_after

    # New instance should not see the expired key either
    cache2 = PersistentProfileCache(default_ttl=5)
    assert cache2.get(key) is None
