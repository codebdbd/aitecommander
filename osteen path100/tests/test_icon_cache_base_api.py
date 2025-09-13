import time

import pytest

from app.config_data import app_config
from app.utils.ui.icon import cache_manager as ic


@pytest.mark.parametrize("prefix", ["path", "qicon"])
def test_base_api_ttl_override(prefix, monkeypatch: pytest.MonkeyPatch):
    # Базовые TTL делаем большими, чтобы не мешали per-entry override
    monkeypatch.setattr(app_config, "get_icon_cache_ttl", lambda: 10.0, raising=True)
    monkeypatch.setattr(
        app_config, "get_abs_icon_cache_ttl", lambda: 10.0, raising=True
    )
    monkeypatch.setattr(
        app_config, "get_negative_cache_ttl", lambda: 10.0, raising=True
    )

    key = f"{prefix}:ttl-test::light"

    # Перед установкой кэш пустой
    assert ic.get(key) is None

    if prefix == "path":
        ic.set(key, "/tmp/icon.svg", ttl=0.1)
    else:
        # Для qicon None интерпретируется как негативная запись, но TTL тоже должен работать
        from PyQt6.QtGui import QIcon

        ic.set(key, QIcon(), ttl=0.1)

    # Сразу после установки есть значение
    val = ic.get(key)
    assert val is not None

    # После истечения per-entry TTL запись должна протухнуть
    time.sleep(0.15)
    assert ic.get(key) is None


def test_base_api_lru_eviction_unified(monkeypatch: pytest.MonkeyPatch):
    # Размер кэша путей = 2
    monkeypatch.setattr(app_config, "get_icon_cache_size", lambda: 2, raising=True)

    # Полная очистка кэша перед тестом
    ic.clear()

    # Три PATH-ключа для проверки LRU вытеснения
    k1 = "path:p1::light"
    k2 = "path:p2::light"
    k3 = "path:p3::light"

    ic.set(k1, "/tmp/1.svg")
    ic.set(k2, "/tmp/2.svg")
    # Обращаемся к k1, чтобы сделать его самым свежим
    assert ic.get(k1) == "/tmp/1.svg"

    # Вставка третьего должна вытеснить наименее использованный — k2
    ic.set(k3, "/tmp/3.svg")

    assert ic.get(k2) is None  # вытеснен
    assert ic.get(k1) == "/tmp/1.svg"  # остался
    assert ic.get(k3) == "/tmp/3.svg"  # добавлен
