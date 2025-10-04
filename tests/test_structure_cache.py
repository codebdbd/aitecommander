from __future__ import annotations

import time

from app.controllers.structure_modules import CacheManager


def test_structure_cache_ttl():
    cm = CacheManager(ttl=0.1)
    cm.set("k1", 123)
    assert cm.get("k1") == 123
    time.sleep(0.15)
    assert cm.get("k1") is None


def test_structure_cache_lru_eviction():
    cm = CacheManager(ttl=5, max_size=2)
    cm.set("a", 1)
    cm.set("b", 2)
    # touch a to make b the oldest
    _ = cm.get("a")
    cm.set("c", 3)  # должно вытеснить b

    assert cm.get("a") == 1
    assert cm.get("c") == 3
    assert cm.get("b") is None


def test_structure_cache_invalidate_and_clear_all():
    cm = CacheManager(ttl=5)
    cm.set("x", 10)
    cm.set("y", 20)

    cm.invalidate("x")
    assert cm.get("x") is None
    assert cm.get("y") == 20

    cm.clear_all()
    assert cm.get("y") is None


def test_first_category_cache_methods():
    cm = CacheManager()
    assert cm.get_first_category_id() is None
    cm.set_first_category_id(42)
    assert cm.get_first_category_id() == 42
    cm.invalidate_first_category_cache()
    assert cm.get_first_category_id() is None
