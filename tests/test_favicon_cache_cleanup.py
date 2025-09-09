import os
import shelve
import time
from contextlib import closing
from pathlib import Path

import pytest

from app.utils.links.parser.favicon_cache import favicon_cache
from app.utils.ui.icon.path_service import icon_path_service


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    # Redirect user icons dir to a temporary location
    icons_dir = tmp_path / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        icon_path_service, "get_user_icons_dir", lambda: icons_dir, raising=True
    )
    # Ensure clean state before/after
    favicon_cache.invalidate(None)
    yield
    favicon_cache.invalidate(None)


def _db_files(base: Path):
    base = base / "favicon_cache.db"
    return [str(base) + s for s in ("", ".bak", ".dat", ".dir")]


def test_get_deletes_expired_record(tmp_path):
    key = "https://example.com/favicon.ico"

    # Put a short-lived record
    favicon_cache.set(key, {"icon": "path/to/icon.png"}, ttl=0.1)

    # Ensure it exists on disk
    db_path = icon_path_service.get_user_icons_dir() / "favicon_cache.db"
    with closing(shelve.open(str(db_path))) as db:
        assert key in db

    # Let it expire
    time.sleep(0.2)

    # First get should detect expiration and delete from DB
    assert favicon_cache.get(key) is None

    # Confirm deletion from shelve
    with closing(shelve.open(str(db_path))) as db:
        assert key not in db


def test_set_and_get_without_writeback(tmp_path):
    key = "https://example.com/icon2.ico"
    data = {"icon": "p.png", "title": "Example"}

    favicon_cache.set(key, data, ttl=10)

    item = favicon_cache.get(key)
    assert item is not None
    assert item.get("icon") == "p.png"
    assert item.get("title") == "Example"


def test_invalidate_key_and_clear_db(tmp_path):
    k1 = "https://a"
    k2 = "https://b"

    favicon_cache.set(k1, {"icon": "a.png"}, ttl=10)
    favicon_cache.set(k2, {"icon": "b.png"}, ttl=10)

    # Invalidate single key
    favicon_cache.invalidate(k1)
    db_path = icon_path_service.get_user_icons_dir() / "favicon_cache.db"
    with closing(shelve.open(str(db_path))) as db:
        assert k1 not in db
        assert k2 in db

    # Clear all
    favicon_cache.invalidate(None)
    # All files should be removed
    for p in _db_files(icon_path_service.get_user_icons_dir()):
        assert not os.path.exists(p)
