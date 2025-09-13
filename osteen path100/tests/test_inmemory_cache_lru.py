import time

from app.utils.cache.base import InMemoryCache


def test_lru_eviction_order_on_set_and_get():
    cache = InMemoryCache(max_size=2)
    cache.set("a", 1)
    cache.set("b", 2)

    # Touch "a" so that "b" becomes the LRU (oldest)
    assert cache.get("a") == 1

    # Insert "c" -> should evict "b"
    cache.set("c", 3)

    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3


def test_overwrite_moves_key_to_mru():
    cache = InMemoryCache(max_size=2)
    cache.set("x", 1)
    cache.set("y", 2)

    # Overwrite x, it should become MRU
    cache.set("x", 10)

    # Next insert should evict "y" (now the LRU)
    cache.set("z", 3)

    assert cache.get("y") is None
    assert cache.get("x") == 10
    assert cache.get("z") == 3


def test_ttl_expiration_removes_entry():
    cache = InMemoryCache(default_ttl=0.1, max_size=3)
    cache.set("k", 42)
    time.sleep(0.2)

    # Expired -> removed on access
    assert cache.get("k") is None

    # Cache still usable after expiration cleanup
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1
    assert cache.get("b") == 2
