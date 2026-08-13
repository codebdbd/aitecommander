from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from app.models.workers.bad_url_check_worker import BadUrlCheckWorker


def _worker() -> BadUrlCheckWorker:
    db = SimpleNamespace(connection=sqlite3.connect(":memory:"))
    return BadUrlCheckWorker(db, timeout=1, check_ssl=True)


def test_verify_404_with_get_returns_unreachable_for_connection_refused() -> None:
    worker = _worker()
    error = URLError(ConnectionRefusedError(10061, "refused"))

    with patch("urllib.request.urlopen", side_effect=[error, error]):
        reachable, reason = worker._verify_404_with_get("https://example.com/missing")

    assert reachable is False
    assert reason == worker.ERROR_UNREACHABLE


def test_verify_404_with_get_returns_404_for_http_404() -> None:
    worker = _worker()
    error = HTTPError(
        "https://example.com/missing",
        404,
        "Not Found",
        hdrs=None,
        fp=None,
    )

    with patch("urllib.request.urlopen", side_effect=error):
        reachable, reason = worker._verify_404_with_get("https://example.com/missing")

    assert reachable is False
    assert reason == worker.ERROR_404
