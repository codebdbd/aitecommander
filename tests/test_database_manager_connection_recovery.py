from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path

from app.core.database_manager import DatabaseManager


def test_get_connection_recovers_from_stale_closed_thread_local_connection() -> None:
    old_db_path = DatabaseManager._db_path
    thread_id = threading.get_ident()
    temp_db = Path("tests") / ".tmp_pytest" / f"recovery_{uuid.uuid4().hex}.db"
    temp_db.parent.mkdir(parents=True, exist_ok=True)

    stale_conn = sqlite3.connect(temp_db, check_same_thread=False)
    stale_conn.row_factory = sqlite3.Row
    stale_conn.close()

    DatabaseManager.configure(temp_db)
    DatabaseManager._thread_local.conn = stale_conn
    DatabaseManager._thread_local.last_used = time.monotonic()
    DatabaseManager._active_connections.clear()

    try:
        conn = DatabaseManager.get_connection()
        assert conn is not stale_conn
        assert conn.execute("SELECT 1").fetchone()[0] == 1
        assert DatabaseManager._active_connections.get(thread_id) is conn
    finally:
        try:
            DatabaseManager.close_all()
        finally:
            DatabaseManager._db_path = old_db_path
