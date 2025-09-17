from __future__ import annotations

import time

import pytest

from app.utils.ui.icon import cache_manager as ic


@pytest.fixture(autouse=True)
def clear_cache():
    ic.clear_icon_cache()
    yield
    ic.clear_icon_cache()


def test_icon_path_ttl(monkeypatch: pytest.MonkeyPatch):
    # TTL для путей делаем очень маленьким
    monkeypatch.setattr(ic.app_config, "get_icon_cache_ttl", lambda: 0.1, raising=True)

    icon, theme = "test-icon", "light"
    assert ic.get_path(icon, theme) is None
    ic.set_path(icon, theme, "/tmp/icon.svg")
    assert ic.get_path(icon, theme) == "/tmp/icon.svg"

    time.sleep(0.15)
    assert ic.get_path(icon, theme) is None


def test_icon_path_lru_eviction(monkeypatch: pytest.MonkeyPatch):
    # Вместимость кэша = 2
    monkeypatch.setattr(ic.app_config, "get_icon_cache_size", lambda: 2, raising=True)

    # Переинициализируем глобальный менеджер через очистку (внутренний кэш возьмет новое значение capacity)
    ic.clear_icon_cache()

    ic.set_path("a", "light", "A")
    ic.set_path("b", "light", "B")

    # Делаем "a" наиболее недавно использованным
    _ = ic.get_path("a", "light")

    # Добавляем "c" — должно вытеснить "b"
    ic.set_path("c", "light", "C")

    assert ic.get_path("a", "light") == "A"
    assert ic.get_path("c", "light") == "C"
    assert ic.get_path("b", "light") is None


def test_qicon_ttl_and_abs_ttl(monkeypatch: pytest.MonkeyPatch):
    # TTL обычных иконок и для абсолютных путей
    monkeypatch.setattr(ic.app_config, "get_icon_cache_ttl", lambda: 0.1, raising=True)
    monkeypatch.setattr(
        ic.app_config, "get_abs_icon_cache_ttl", lambda: 0.2, raising=True
    )

    from PyQt6.QtGui import QIcon

    # Обычная тема
    ic.set_icon("i1", "light", QIcon())
    assert isinstance(ic.get_icon("i1", "light"), QIcon)
    time.sleep(0.12)
    assert ic.get_icon("i1", "light") is None

    # Абсолютная тема __abs__ использует отдельный TTL
    ic.set_icon("/abs/icon.png", "__abs__", QIcon())
    assert isinstance(ic.get_icon("/abs/icon.png", "__abs__"), QIcon)
    time.sleep(0.12)
    # ещё не протух
    assert isinstance(ic.get_icon("/abs/icon.png", "__abs__"), QIcon)
    time.sleep(0.1)
    assert ic.get_icon("/abs/icon.png", "__abs__") is None
