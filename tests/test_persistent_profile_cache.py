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
    assert cache.get(browser) == profiles

    # Проверим, что записалось на диск
    cache_path = temp_config_dir / "browser_profiles.json"
    assert cache_path.exists()
    data = json.loads(cache_path.read_text("utf-8"))
    assert browser in data

    # invalidate одного ключа
    cache.invalidate(browser)
    assert cache.get(browser) is None

    # set снова и invalidate all
    cache.set(browser, profiles)
    cache.invalidate()
    assert cache.get(browser) is None


def test_persistent_profile_cache_ttl(temp_config_dir: Path):
    cache = PersistentProfileCache(default_ttl=1.0)

    browser = "firefox"
    profiles = [{"name": "Personal"}]

    cache.set(browser, profiles)
    assert cache.get(browser) == profiles

    # Ждем протухания TTL
    time.sleep(1.1)
    assert cache.get(browser) is None
