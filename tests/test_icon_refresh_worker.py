from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

from app.models.workers.icon_refresh_worker import IconRefreshWorker


def _build_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE link (id INTEGER PRIMARY KEY, url TEXT, icon_path TEXT, type TEXT)"
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
