from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.utils.links.parser.favicon_cache import favicon_cache


@pytest.fixture()
def temp_icons_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Перенаправим user icons dir в temp
    from app.utils.ui.icon import path_service as ps

    monkeypatch.setattr(
        ps, "icon_path_service", ps.icon_path_service.__class__(), raising=True
    )
    # Переопределим метод на лету, чтобы возвращал tmp_path
    monkeypatch.setattr(
        ps.icon_path_service, "get_user_icons_dir", lambda: tmp_path, raising=True
    )
    return tmp_path


def test_favicon_cache_hit_and_expire_without_sleep(temp_icons_dir: Path):
    url = "https://example.com"
    past = time.time() - 100.0

    # Явный ttl=10s и прошедший timestamp => miss
    favicon_cache.set(url, {"icon": "ico.png", "timestamp": past}, ttl=10)
    assert favicon_cache.get(url) is None

    # ttl=200s и прошедший timestamp => hit
    favicon_cache.set(url, {"icon": "ico.png", "timestamp": past}, ttl=200)
    item = favicon_cache.get(url)
    assert item and item.get("icon") == "ico.png"


def test_favicon_cache_negative_ttl_via_default_icon(temp_icons_dir: Path, monkeypatch):
    url = "https://neg.example"

    # Подменим resolve_icon_for_link, чтобы default_icon был известен
    from app.utils.links.parser import favicon_cache as fc_mod

    monkeypatch.setattr(fc_mod, "resolve_icon_for_link", lambda _: "DEF", raising=True)

    past = time.time() - 100.0
    # Без явного ttl и с icon == default => используется SHORT_NEGATIVE_TTL (1 час по умолчанию)
    # При timestamp в прошлом на 100s запись должна быть свежей
    favicon_cache.set(url, {"icon": "DEF", "timestamp": past})
    assert favicon_cache.get(url) is not None

    # Сделаем timestamp в прошлом на 3 часа — должен протухнуть
    three_hours_ago = time.time() - (3 * 3600)
    favicon_cache.set(url, {"icon": "DEF", "timestamp": three_hours_ago})
    assert favicon_cache.get(url) is None
