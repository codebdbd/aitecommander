from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.utils.links.parser.favicon_cache import favicon_cache
from app.config_data import app_config


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


def _db_path(tmp_dir: Path) -> Path:
    return tmp_dir / "favicon_cache.db"


def _db_items_count(db_path: Path) -> int:
    import shelve
    from contextlib import closing

    with closing(shelve.open(str(db_path))) as db:
        return sum(1 for k in db.keys() if not str(k).startswith("__"))


def test_max_size_enforced_on_set(temp_icons_dir: Path, monkeypatch: pytest.MonkeyPatch):
    # Установим маленький лимит
    monkeypatch.setattr(app_config, "favicon_cache_max_size", 3, raising=False)
    # Вставим 10 ключей с возрастающими timestamp — должны остаться 3 самых новых
    base = time.time() - 1000
    for i in range(10):
        favicon_cache.set(f"url-{i}", {"icon": f"i{i}.png", "timestamp": base + i})
    # Проверим через наружный доступ (DB напрямую), что размер ограничен
    assert _db_items_count(_db_path(temp_icons_dir)) <= 3
    # И доступность только последних
    for i in range(7):
        assert favicon_cache.get(f"url-{i}") is None
    for i in range(7, 10):
        assert favicon_cache.get(f"url-{i}") is not None


def test_cleanup_removes_expired_entries(temp_icons_dir: Path, monkeypatch: pytest.MonkeyPatch):
    # Сделаем лимит больше, чтобы проверить именно очистку по TTL
    monkeypatch.setattr(app_config, "favicon_cache_max_size", 100, raising=False)
    old_ts = time.time() - (5 * 3600)
    # Вставим запись с ttl=1 час, но timestamp 5 часов назад — явно протухшая
    favicon_cache.set("expired-url", {"icon": "x.png", "timestamp": old_ts}, ttl=3600)
    # Вставка любой новой записи должна запустить _maybe_cleanup и удалить expired-url
    favicon_cache.set("fresh-url", {"icon": "y.png"})
    assert favicon_cache.get("expired-url") is None
    assert favicon_cache.get("fresh-url") is not None


def test_cleanup_interval_marker_set(temp_icons_dir: Path):
    # При первой вставке должна выставиться метка последней очистки
    favicon_cache.set("a", {"icon": "a.png"})
    # Проверим наличие служебного ключа
    import shelve
    from contextlib import closing

    dbp = _db_path(temp_icons_dir)
    with closing(shelve.open(str(dbp))) as db:
        assert "__last_cleanup_ts__" in db
