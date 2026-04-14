from __future__ import annotations

import sqlite3
import threading

from app.core.database_manager import DatabaseManager


def test_close_ignores_already_closed_connection() -> None:
    conn = sqlite3.connect(":memory:")
    thread_id = threading.get_ident()
    DatabaseManager._thread_local.conn = conn
    DatabaseManager._thread_local.last_used = 0
    DatabaseManager._active_connections[thread_id] = conn

    conn.close()

    DatabaseManager.close()

    assert not hasattr(DatabaseManager._thread_local, "conn")
