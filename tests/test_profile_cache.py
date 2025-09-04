import app.utils.browser.browser_profiles.persistent_cache as pc_mod
from app.utils.browser.browser_profiles import PersistentProfileCache


def _patch_cache_path(monkeypatch, tmp_path):
    test_path = tmp_path / "profiles_cache.json"
    monkeypatch.setattr(pc_mod, "get_cache_path", lambda: test_path, raising=True)
    return test_path


def test_persistent_profile_cache_set_get_and_invalidate(monkeypatch, tmp_path):
    _patch_cache_path(monkeypatch, tmp_path)
    cache = PersistentProfileCache(default_ttl=10)
    assert cache.get("chrome") is None
    cache.set("chrome", [{"id": "Default"}])
    assert cache.get("chrome") == [{"id": "Default"}]
    cache.invalidate()
    assert cache.get("chrome") is None


def test_persistent_profile_cache_ttl_expiration(monkeypatch, tmp_path):
    _patch_cache_path(monkeypatch, tmp_path)
    cache = PersistentProfileCache(default_ttl=0)
    cache.set("firefox", [{"id": "default"}])
    # При нулевом TTL запись сразу невалидна
    assert cache.get("firefox") is None


def test_persistent_profile_cache_persistence_on_disk(monkeypatch, tmp_path):
    cache_path = _patch_cache_path(monkeypatch, tmp_path)
    # Первый инстанс пишет на диск
    cache1 = PersistentProfileCache(default_ttl=5)
    cache1.set("edge", [{"id": "Profile 1"}])
    # При отложенной записи нужно явно сбросить на диск
    cache1.flush()
    assert cache_path.exists()
    # Новый инстанс читает с диска и считает свежим
    cache2 = PersistentProfileCache(default_ttl=5)
    assert cache2.get("edge") == [{"id": "Profile 1"}]
