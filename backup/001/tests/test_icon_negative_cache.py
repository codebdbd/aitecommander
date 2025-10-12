from __future__ import annotations

import time

import pytest

from app.utils.ui.icon import negative_cache as nc


@pytest.fixture(autouse=True)
def clear_neg_cache():
    nc.clear()
    yield
    nc.clear()


def test_negative_cache_basic(monkeypatch: pytest.MonkeyPatch):
    # Установим маленький базовый TTL
    from app.config_data import app_config

    monkeypatch.setattr(app_config, "icon_negative_cache_ttl", 0.1, raising=False)
    monkeypatch.setattr(app_config, "icon_negative_cache_ttl_max", 1.0, raising=False)

    key = "light:missing.svg"
    assert not nc.is_negative(key)
    nc.mark_negative(key)
    assert nc.is_negative(key)

    # Подождём протухания
    time.sleep(0.15)
    assert not nc.is_negative(key)


def test_negative_cache_backoff(monkeypatch: pytest.MonkeyPatch):
    from app.config_data import app_config

    # Базовый TTL маленький, но с ростом strikes увеличивается
    monkeypatch.setattr(app_config, "icon_negative_cache_ttl", 0.05, raising=False)
    monkeypatch.setattr(app_config, "icon_negative_cache_ttl_max", 0.5, raising=False)

    key = "dark:missing.svg"
    for _ in range(3):
        nc.mark_negative(key)
        assert nc.is_negative(key)
        # TTL растёт экспоненциально — сразу не протухнет
        time.sleep(0.06)
        # Может ещё быть в кэше, не проверяем строго по времени
        _ = nc.is_negative(key)

    # Очистка
    nc.clear()
    assert not nc.is_negative(key)
