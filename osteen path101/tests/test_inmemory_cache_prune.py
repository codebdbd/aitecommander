import time

from app.utils.cache.base import InMemoryCache


def test_prune_expired_removes_all_expired():
    cache = InMemoryCache(default_ttl=0.05, max_size=10)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    # let them expire
    time.sleep(0.08)

    removed = cache.prune_expired()
    assert removed >= 3
    assert cache.get("a") is None
    assert cache.get("b") is None
    assert cache.get("c") is None


def test_opportunistic_prune_runs_on_set_when_interval_passed():
    cache = InMemoryCache(default_ttl=0.05, max_size=10)
    # force immediate pruning allowed
    cache._prune_interval_sec = 0.0  # type: ignore[attr-defined]

    cache.set("k1", 1)
    cache.set("k2", 2)
    time.sleep(0.08)

    # This set should trigger _maybe_prune_expired_locked and drop expired keys
    cache.set("k3", 3)

    assert cache.get("k1") is None
    assert cache.get("k2") is None
    assert cache.get("k3") == 3


def test_opportunistic_prune_runs_on_invalidate_when_interval_passed():
    cache = InMemoryCache(default_ttl=0.05, max_size=10)
    cache._prune_interval_sec = 0.0  # type: ignore[attr-defined]

    cache.set("x", 1)
    cache.set("y", 2)
    time.sleep(0.08)

    # touching unrelated key removal should also attempt prune
    cache.invalidate("nonexistent")

    assert cache.get("x") is None
    assert cache.get("y") is None
