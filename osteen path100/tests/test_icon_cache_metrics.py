from __future__ import annotations

import time

import pytest

from app.utils.ui.icon import cache_manager as ic


@pytest.fixture(autouse=True)
def clear_and_reset():
    ic.clear_icon_cache()
    ic.reset_icon_cache_stats()
    yield
    ic.clear_icon_cache()
    ic.reset_icon_cache_stats()


def _stats():
    return ic.get_icon_cache_stats()


def test_path_metrics_hit_and_miss(monkeypatch: pytest.MonkeyPatch):
    # initial miss
    assert ic.get_path("p1", "light") is None
    s = _stats()
    assert s["misses"] == 1 and s["hits"] == 0

    ic.set_path("p1", "light", "/tmp/icon.svg")
    assert ic.get_path("p1", "light") == "/tmp/icon.svg"
    s = _stats()
    assert s["misses"] == 1 and s["hits"] == 1


def test_path_metrics_expired_counts_as_miss(monkeypatch: pytest.MonkeyPatch):
    # make path TTL very small
    monkeypatch.setattr(ic.app_config, "get_icon_cache_ttl", lambda: 0.05, raising=True)
    ic.clear_icon_cache()  # ensure TTL takes effect inside cache

    ic.set_path("p2", "light", "/tmp/icon2.svg")
    assert ic.get_path("p2", "light") == "/tmp/icon2.svg"
    time.sleep(0.06)
    assert ic.get_path("p2", "light") is None

    s = _stats()
    # 1 hit (first get), 1 miss (expired)
    assert s["hits"] == 1 and s["misses"] == 1


def test_qicon_metrics_hit_and_miss_and_expired(monkeypatch: pytest.MonkeyPatch):
    from PyQt6.QtGui import QIcon

    # initial miss
    assert ic.get_icon("qi1", "light") is None
    s = _stats()
    assert s["misses"] == 1 and s["hits"] == 0

    ic.set_icon("qi1", "light", QIcon())
    assert isinstance(ic.get_icon("qi1", "light"), QIcon)
    s = _stats()
    assert s["misses"] == 1 and s["hits"] == 1

    # expire fast and check miss
    monkeypatch.setattr(ic.app_config, "get_icon_cache_ttl", lambda: 0.05, raising=True)
    ic.clear_icon_cache()  # re-init with new TTL

    ic.set_icon("qi2", "light", QIcon())
    assert isinstance(ic.get_icon("qi2", "light"), QIcon)
    time.sleep(0.06)
    assert ic.get_icon("qi2", "light") is None

    s2 = _stats()
    # From second phase: 1 hit then 1 miss
    assert s2["hits"] == 1 and s2["misses"] == 1
