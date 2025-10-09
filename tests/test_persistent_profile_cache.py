from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.utils.browser.browser_profiles.persistent_cache import PersistentProfileCache


@pytest.fixture()
def temp_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Перенаправим config dir в tmp
    from app.config_data import app_config

    class PathsProxy:
        def __init__(self, base: Path):
            self._base = base

        def ensure_user_data_dirs(self):
            (self._base).mkdir(parents=True, exist_ok=True)

        def get_config_dir(self) -> Path:
            return self._base

    monkeypatch.setattr(app_config, "paths", PathsProxy(tmp_path), raising=True)
    return tmp_path


def test_persistent_profile_cache_basic(temp_config_dir: Path):
    cache = PersistentProfileCache(default_ttl=60)

    browser = "chrome"
    profiles = [{"name": "Default"}, {"name": "Work"}]

    assert cache.get(browser) is None
    cache.set(browser, profiles)
    cache.flush()
    assert cache.get(browser) == profiles

    # Проверим, что записалось на диск
    cache_path = temp_config_dir / "browser_profiles.json"
    assert cache_path.exists()
    data = json.loads(cache_path.read_text("utf-8"))
    assert browser in data

    # invalidate одного ключа
    cache.invalidate(browser)
    cache.flush()
    assert cache.get(browser) is None

    # set снова и invalidate all
    cache.set(browser, profiles)
    cache.flush()
    cache.invalidate()
    cache.flush()
    assert cache.get(browser) is None


def test_persistent_profile_cache_keys_method(temp_config_dir: Path):
    """Test keys() method returns valid keys."""
    cache = PersistentProfileCache(default_ttl=60)

    # Set multiple browser profiles
    cache.set("chrome", [{"name": "Default"}])
    cache.set("firefox", [{"name": "Personal"}])
    cache.set("edge", [{"name": "Work"}])

    # Test keys() method
    keys = cache.keys()
    assert len(keys) == 3
    assert "chrome" in keys
    assert "firefox" in keys
    assert "edge" in keys

    # Test __iter__ method
    keys_from_iter = list(cache)
    assert len(keys_from_iter) == 3
    assert "chrome" in keys_from_iter
    assert "firefox" in keys_from_iter
    assert "edge" in keys_from_iter

    # Test __len__ method
    assert len(cache) == 3

    # Test with expired entry
    cache.set("opera", [{"name": "Temp"}], ttl=0.1)
    assert len(cache) == 4  # Still 4, not yet expired

    time.sleep(0.2)  # Wait for expiration
    assert len(cache) == 3  # Should be 3 now (opera expired)
    keys_after_expiry = cache.keys()
    assert "opera" not in keys_after_expiry

    # Test empty cache
    cache.invalidate()  # Clear all
    assert len(cache) == 0
    assert list(cache.keys()) == []
    assert list(cache) == []


def test_persistent_profile_cache_keys_persistence(temp_config_dir: Path):
    """Test that keys() works correctly with persisted data."""
    # Create cache and add data
    cache1 = PersistentProfileCache(default_ttl=60)
    cache1.set("chrome", [{"name": "Default"}])
    cache1.set("firefox", [{"name": "Personal"}])
    cache1.flush()

    # Create new cache instance (simulates app restart)
    cache2 = PersistentProfileCache(default_ttl=60)

    # Test that keys are loaded correctly
    keys = cache2.keys()
    assert len(keys) == 2
    assert "chrome" in keys
    assert "firefox" in keys

    # Test iteration
    for key in cache2:
        assert key in ["chrome", "firefox"]
        profiles = cache2.get(key)
        assert profiles is not None
