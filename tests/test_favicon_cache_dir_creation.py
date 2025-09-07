from pathlib import Path

import pytest

from app.utils.links.parser import favicon_cache as fc_module
from app.utils.links.parser.favicon_cache import favicon_cache


@pytest.mark.parametrize("use_invalidate_all_first", [True, False])
def test_favicon_cache_creates_dir_and_operates_when_missing(tmp_path, monkeypatch, use_invalidate_all_first):
    # Arrange: point user icons dir to a temporary non-existing directory
    user_icons_dir = tmp_path / "icons"
    assert not user_icons_dir.exists()

    # Monkeypatch icon_path_service to use our temp directory
    def _get_user_icons_dir():
        return user_icons_dir

    def _ensure_user_icons_dir():
        user_icons_dir.mkdir(parents=True, exist_ok=True)
        return user_icons_dir

    monkeypatch.setattr(fc_module.icon_path_service, "get_user_icons_dir", _get_user_icons_dir, raising=True)
    monkeypatch.setattr(fc_module.icon_path_service, "ensure_user_icons_dir", _ensure_user_icons_dir, raising=True)

    # Act + Assert: operations should auto-create the directory and not raise
    if use_invalidate_all_first:
        # invalidate all should work even if DB files don't exist yet
        favicon_cache.invalidate(None)

    # Directory should be created lazily before shelve open
    key = "http://example.com"
    value = {"icon": "favicon.png", "title": "Example"}

    favicon_cache.set(key, value)
    assert user_icons_dir.exists(), "User icons directory must be created automatically"

    loaded = favicon_cache.get(key)
    assert isinstance(loaded, dict) and loaded.get("icon") == "favicon.png"

    # Ensure shelve files were created inside our directory
    db_base = user_icons_dir / "favicon_cache.db"
    # Shelve can create a variety of files depending on backend
    possible = [db_base, db_base.with_suffix(".db"), Path(str(db_base) + ".dat"), Path(str(db_base) + ".dir"), Path(str(db_base) + ".bak")]
    assert any(p.exists() for p in possible), "Shelve database files should be present after write"

    # Invalidate single key and verify it's gone
    favicon_cache.invalidate(key)
    assert favicon_cache.get(key) is None
