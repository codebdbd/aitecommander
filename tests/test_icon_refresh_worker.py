from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

from app.models.workers.icon_refresh_worker import IconRefreshWorker


def _build_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE link (id INTEGER PRIMARY KEY, url TEXT, icon_path TEXT, type TEXT, category_id INTEGER, name TEXT)"
    )
    return conn


def test_commit_updates_skips_rows_that_changed_since_fetch() -> None:
    conn = _build_connection()
    conn.execute(
        "INSERT INTO link (id, url, icon_path, type) VALUES (1, 'https://new.example', 'user.png', 'web')"
    )
    worker = IconRefreshWorker(SimpleNamespace(connection=conn))

    with patch(
        "app.models.workers.icon_refresh_worker.clear_icon_cache"
    ) as clear_cache_mock:
        worker._commit_updates(
            {1: ("C:/icons/site.png", "https://old.example", "web")},
            default_icon_path="C:/icons/web_icon.png",
        )

    saved = conn.execute("SELECT icon_path FROM link WHERE id = 1").fetchone()["icon_path"]
    assert saved == "user.png"
    clear_cache_mock.assert_not_called()


def test_commit_updates_persists_basename_only_for_default_icons() -> None:
    conn = _build_connection()
    conn.execute(
        "INSERT INTO link (id, url, icon_path, type) VALUES (1, 'https://example.com', '', 'web')"
    )
    worker = IconRefreshWorker(SimpleNamespace(connection=conn))

    with patch(
        "app.models.workers.icon_refresh_worker.clear_icon_cache"
    ) as clear_cache_mock:
        worker._commit_updates(
            {1: ("C:/icons/site.png", "https://example.com", "web")},
            default_icon_path="C:/icons/web_icon.png",
        )

    saved = conn.execute("SELECT icon_path FROM link WHERE id = 1").fetchone()["icon_path"]
    assert saved == "site.png"
    clear_cache_mock.assert_called_once()


def test_is_file_icon_default(tmp_path) -> None:
    worker = IconRefreshWorker(SimpleNamespace(connection=None))

    # Empty path -> default
    assert worker._is_file_icon_default("") is True

    # Non-existent file -> default
    assert worker._is_file_icon_default(str(tmp_path / "non_existent.png")) is True

    # File smaller than 2048 bytes (e.g. broken Qt fallback icon) -> default
    small_file = tmp_path / "small.png"
    small_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)
    assert worker._is_file_icon_default(str(small_file)) is True

    # Real icon (>= 2048 bytes) -> not default
    real_file = tmp_path / "real.png"
    real_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 3000)
    assert worker._is_file_icon_default(str(real_file)) is False


def test_find_links_includes_file_type() -> None:
    conn = _build_connection()
    conn.execute(
        "INSERT INTO link (id, url, icon_path, type) VALUES (1, 'C:/doc.docx', '', 'file')"
    )
    conn.execute(
        "INSERT INTO link (id, url, icon_path, type) VALUES (2, 'https://example.com', '', 'web')"
    )
    conn.execute(
        "INSERT INTO link (id, url, icon_path, type) VALUES (3, 'C:/app.exe', '', 'program')"
    )
    worker = IconRefreshWorker(SimpleNamespace(connection=conn))

    links = worker._find_links_with_default_icons(default_icon_path="")
    assert len(links) == 3
    types = {link["type"] for link in links}
    assert types == {"file", "web", "program"}

