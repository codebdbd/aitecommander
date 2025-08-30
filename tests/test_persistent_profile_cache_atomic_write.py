import json
from pathlib import Path

import pytest

from app.utils.browser.browser_profiles import persistent_cache as pc_module
from app.utils.browser.browser_profiles.persistent_cache import PersistentProfileCache


@pytest.fixture()
def tmp_cache_path(tmp_path, monkeypatch) -> Path:
    cache_file = tmp_path / "profiles_cache.json"

    # Redirect cache path resolution inside module to our temp file
    monkeypatch.setattr(pc_module, "get_cache_path", lambda: cache_file, raising=True)
    return cache_file


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def test_atomic_write_json_dump_failure(tmp_cache_path: Path, monkeypatch):
    # Arrange: create initial valid file
    tmp_cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_cache_path.write_text(json.dumps({"initial": [1, 2, 3]}, ensure_ascii=False, indent=2), encoding="utf-8")

    cache = PersistentProfileCache()

    # Force json.dump to fail
    def boom(*args, **kwargs):  # noqa: ANN001
        raise IOError("simulated write failure")

    monkeypatch.setattr(pc_module.json, "dump", boom, raising=True)

    # Act: call set() which swallows disk errors
    cache.set("k", {"v": 1})

    # Assert: main file unchanged, no .tmp leftovers
    assert json.loads(read_text(tmp_cache_path)) == {"initial": [1, 2, 3]}
    tmp_file = tmp_cache_path.with_suffix(tmp_cache_path.suffix + ".tmp")
    assert not tmp_file.exists(), "Temporary file must be cleaned up on failure"


def test_atomic_write_replace_failure(tmp_cache_path: Path, monkeypatch):
    # Arrange: initial file
    tmp_cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_cache_path.write_text(json.dumps({"a": 1}, ensure_ascii=False, indent=2), encoding="utf-8")

    cache = PersistentProfileCache()

    # Make os.replace fail after successful write of temp file
    def replace_boom(src, dst):  # noqa: ANN001
        raise OSError("simulated replace failure")

    monkeypatch.setattr(pc_module.os, "replace", replace_boom, raising=True)

    # Act
    cache.set("k", {"x": 2})

    # Assert: main file unchanged, temp cleaned
    assert json.loads(read_text(tmp_cache_path)) == {"a": 1}
    tmp_file = tmp_cache_path.with_suffix(tmp_cache_path.suffix + ".tmp")
    assert not tmp_file.exists(), "Temporary file must be removed even if replace fails"
