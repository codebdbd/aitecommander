import time
import pytest

from app.utils.browser.browser_profiles.runtime_cache import ProfileCache


def test_profile_cache_set_get_and_clear():
    cache = ProfileCache(timeout_seconds=10)
    assert cache.get("chrome") is None
    cache.set("chrome", [{"id": "Default"}])
    assert cache.get("chrome") == [{"id": "Default"}]
    assert cache.get_if_fresh("chrome") == [{"id": "Default"}]
    cache.clear()
    assert cache.get("chrome") is None


def test_profile_cache_timeout_expiration():
    cache = ProfileCache(timeout_seconds=0)
    cache.set("firefox", [{"id": "default"}])
    # При нулевом таймауте запись сразу не свежая
    assert cache.get_if_fresh("firefox") is None
    # Но прямой get возвращает устаревшее значение
    assert cache.get("firefox") == [{"id": "default"}]


def test_profile_cache_load_initial_and_is_fresh():
    cache = ProfileCache(timeout_seconds=1)
    cache.load_initial({"edge": [{"id": "Profile 1"}]})
    assert cache.get("edge") == [{"id": "Profile 1"}]
    assert cache.is_fresh("edge") is True
    time.sleep(1.1)
    assert cache.get_if_fresh("edge") is None
    assert cache.is_fresh("edge") is False
