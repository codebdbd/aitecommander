from __future__ import annotations

import pytest

from app.utils.cache.base import InMemoryCache


def test_max_size_negative_raises():
    with pytest.raises(ValueError):
        InMemoryCache(max_size=-1)


def test_max_size_zero_evicts_immediately():
    c = InMemoryCache(max_size=0)
    c.set("a", 1)
    # При max_size=0 любая вставка должна приводить к немедленному вытеснению
    assert c.get("a") is None


def test_max_size_none_no_evict():
    c = InMemoryCache(max_size=None)
    # Вставляем несколько значений — не должно быть вытеснения по размеру
    for i in range(5):
        c.set(f"k{i}", i)
    # Все доступны
    for i in range(5):
        assert c.get(f"k{i}") == i
