"""Centralized database connection and schema management."""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.core.paths.path_manager import PathManager
from app.utils.db.migrations import MigrationRunner

logger = logging.getLogger(__name__)


def _ms(start: float, end: float) -> float:
    return (end - start) * 1000.0


class DatabaseManager:
    """Static API for managing database connections and schema."""

    DEFAULT_MMAP_SIZE = 268435456
    _db_path: Path | None = None
    _thread_local = threading.local()
    _active_connections: dict[int, sqlite3.Connection] = {}
    _connection_lock = threading.Lock()
    _global_pragmas_applied_path: Path | None = None

    @classmethod
    def configure(cls, db_path: Path | None = None) -> None:
        if db_path is None:
            cls._db_path = PathManager.db_path()
        else:
            cls._db_path = Path(db_path)
        cls._global_pragmas_applied_path = None

    @classmethod
    def get_db_path(cls) -> Path:
        if cls._db_path is None:
            cls.configure()
        return cls._db_path  # type: ignore[return-value]

    @classmethod
    def get_connection(cls) -> sqlite3.Connection:
        start_total = time.perf_counter()
        conn = getattr(cls._thread_local, "conn", None)
        if conn is not None:
            last_used = getattr(cls._thread_local, "last_used", 0)
            now = time.monotonic()
            if now - last_used < 30:
                thread_id = threading.get_ident()
                # Fast path is safe only when this exact connection is still registered
                # as active for current thread. After close_all() the registry is cleared
                # across threads, so stale thread-local references must be revalidated.
                if cls._active_connections.get(thread_id) is conn:
                    cls._thread_local.last_used = now
                    return conn
                try:
                    start_ping = time.perf_counter()
                    conn.execute("SELECT 1").fetchone()
                    ping_ms = _ms(start_ping, time.perf_counter())
                    with cls._connection_lock:
                        cls._active_connections[thread_id] = conn
                    cls._thread_local.last_used = now
                    total_ms = _ms(start_total, time.perf_counter())
                    if total_ms >= 100:
                        logger.info(
                            "[Perf] DatabaseManager.get_connection reuse-recover "
                            "thread=%s ping=%.2f ms total=%.2f ms",
                            thread_id,
                            ping_ms,
                            total_ms,
                        )
                    return conn
                except Exception:
                    cls._close_current_thread(conn)
            try:
                start_ping = time.perf_counter()
                conn.execute("SELECT 1").fetchone()
                ping_ms = _ms(start_ping, time.perf_counter())
                cls._thread_local.last_used = now
                total_ms = _ms(start_total, time.perf_counter())
                if total_ms >= 100:
                    logger.info(
                        "[Perf] DatabaseManager.get_connection reuse-stale-check "
                        "thread=%s ping=%.2f ms total=%.2f ms",
                        threading.get_ident(),
                        ping_ms,
                        total_ms,
                    )
                return conn
            except Exception:
                cls._close_current_thread(conn)

        lock_wait_start = time.perf_counter()
        with cls._connection_lock:
            lock_wait_ms = _ms(lock_wait_start, time.perf_counter())
            conn = getattr(cls._thread_local, "conn", None)
            if conn is not None:
                cls._thread_local.last_used = time.monotonic()
                total_ms = _ms(start_total, time.perf_counter())
                if total_ms >= 100:
                    logger.info(
                        "[Perf] DatabaseManager.get_connection double-checked-hit "
                        "thread=%s lock_wait=%.2f ms total=%.2f ms",
                        threading.get_ident(),
                        lock_wait_ms,
                        total_ms,
                    )
                return conn

            connect_start = time.perf_counter()
            db_path = cls.get_db_path()
            conn = sqlite3.connect(db_path, check_same_thread=False)
            connect_ms = _ms(connect_start, time.perf_counter())
            conn.row_factory = sqlite3.Row
            apply_global_pragmas = cls._global_pragmas_applied_path != db_path
            pragmas = cls._apply_pragmas(
                conn,
                apply_global_pragmas=apply_global_pragmas,
            )
            if apply_global_pragmas:
                cls._global_pragmas_applied_path = db_path
            cls._thread_local.conn = conn
            cls._thread_local.last_used = time.monotonic()
            thread_id = threading.get_ident()
            cls._active_connections[thread_id] = conn
            total_ms = _ms(start_total, time.perf_counter())
            if total_ms >= 100:
                logger.info(
                    "[Perf] DatabaseManager.get_connection new-connection "
                    "thread=%s lock_wait=%.2f ms connect=%.2f ms "
                    "pragmas=%.2f ms pragma_foreign_keys=%.2f ms "
                    "pragma_journal_mode=%.2f ms pragma_synchronous=%.2f ms "
                    "pragma_cache_size=%.2f ms pragma_temp_store=%.2f ms "
                    "pragma_mmap_size=%.2f ms pragma_busy_timeout=%.2f ms "
                    "global_pragmas=%s db_path=%s cache_size_kib=%s "
                    "total=%.2f ms",
                    thread_id,
                    lock_wait_ms,
                    connect_ms,
                    pragmas["total_ms"],
                    pragmas["foreign_keys_ms"],
                    pragmas["journal_mode_ms"],
                    pragmas["synchronous_ms"],
                    pragmas["cache_size_ms"],
                    pragmas["temp_store_ms"],
                    pragmas["mmap_size_ms"],
                    pragmas["busy_timeout_ms"],
                    apply_global_pragmas,
                    db_path,
                    pragmas["cache_size_kib"],
                    total_ms,
                )
            return conn

    @classmethod
    @contextmanager
    def transaction(cls) -> Iterator[sqlite3.Connection]:
        conn = cls.get_connection()
        try:
            conn.execute("BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    @classmethod
    def ensure_schema(cls) -> int:
        migrations_dir = PathManager.app_root() / "models" / "migrations"
        conn = cls.get_connection()
        runner = MigrationRunner(conn, migrations_dir)
        applied = runner.run_all_pending()
        logger.info("Migrations applied: %d", applied)
        return applied

    @classmethod
    def close(cls) -> None:
        conn = getattr(cls._thread_local, "conn", None)
        if conn is None:
            return
        try:
            conn.execute("PRAGMA wal_checkpoint(FULL)")
            conn.commit()
        except sqlite3.ProgrammingError as exc:
            # Expected during DB restore race when connection was already closed.
            if "closed database" in str(exc).lower():
                logger.debug("Skip WAL checkpoint on already closed connection")
            else:
                logger.warning("WAL checkpoint failed during close: %s", exc)
        except Exception as exc:
            logger.warning("WAL checkpoint failed during close: %s", exc)
        cls._close_current_thread(conn)

    @classmethod
    def close_all(cls) -> None:
        with cls._connection_lock:
            connections = list(cls._active_connections.items())
            cls._active_connections.clear()

        for thread_id, conn in connections:
            try:
                try:
                    conn.execute("PRAGMA mmap_size = 0")
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    conn.commit()
                except Exception as exc:
                    logger.warning(
                        "Checkpoint failed for thread %s: %s", thread_id, exc
                    )
                conn.close()
            except Exception as exc:
                logger.warning(
                    "Error closing connection for thread %s: %s", thread_id, exc
                )

        if hasattr(cls._thread_local, "conn"):
            try:
                del cls._thread_local.conn
            except Exception:
                pass
        if hasattr(cls._thread_local, "last_used"):
            try:
                del cls._thread_local.last_used
            except Exception:
                pass

    @classmethod
    def is_connected(cls) -> bool:
        conn = getattr(cls._thread_local, "conn", None)
        if conn is None:
            return False
        try:
            conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    @classmethod
    def _close_current_thread(cls, conn: sqlite3.Connection) -> None:
        try:
            conn.close()
        except Exception:
            pass
        if hasattr(cls._thread_local, "conn"):
            try:
                del cls._thread_local.conn
            except Exception:
                pass
        if hasattr(cls._thread_local, "last_used"):
            try:
                del cls._thread_local.last_used
            except Exception:
                pass
        with cls._connection_lock:
            cls._active_connections.pop(threading.get_ident(), None)

    @staticmethod
    def _apply_pragmas(
        conn: sqlite3.Connection,
        *,
        apply_global_pragmas: bool,
    ) -> dict[str, float | int | None]:
        timings: dict[str, float | int | None] = {}
        cache_size_kib = DatabaseManager._get_cache_size_kib()

        start = time.perf_counter()
        conn.execute("PRAGMA foreign_keys = ON")
        timings["foreign_keys_ms"] = _ms(start, time.perf_counter())

        timings["cache_size_kib"] = cache_size_kib
        if cache_size_kib is not None:
            start = time.perf_counter()
            conn.execute(f"PRAGMA cache_size = -{cache_size_kib}")
            timings["cache_size_ms"] = _ms(start, time.perf_counter())
        else:
            timings["cache_size_ms"] = 0.0

        start = time.perf_counter()
        conn.execute("PRAGMA temp_store = MEMORY")
        timings["temp_store_ms"] = _ms(start, time.perf_counter())

        start = time.perf_counter()
        conn.execute("PRAGMA busy_timeout = 5000")
        timings["busy_timeout_ms"] = _ms(start, time.perf_counter())

        if apply_global_pragmas:
            start = time.perf_counter()
            conn.execute("PRAGMA journal_mode = WAL")
            timings["journal_mode_ms"] = _ms(start, time.perf_counter())

            start = time.perf_counter()
            conn.execute("PRAGMA synchronous = NORMAL")
            timings["synchronous_ms"] = _ms(start, time.perf_counter())

            start = time.perf_counter()
            conn.execute(f"PRAGMA mmap_size = {DatabaseManager.DEFAULT_MMAP_SIZE}")
            timings["mmap_size_ms"] = _ms(start, time.perf_counter())
        else:
            timings["journal_mode_ms"] = 0.0
            timings["synchronous_ms"] = 0.0
            timings["mmap_size_ms"] = 0.0

        timings["total_ms"] = sum(
            value
            for key, value in timings.items()
            if key.endswith("_ms") and isinstance(value, int | float)
        )
        return timings

    @classmethod
    def _get_cache_size_kib(cls) -> int | None:
        raw_value = os.getenv("APP_DB_CACHE_SIZE_KIB", "").strip()
        if not raw_value:
            return None
        try:
            parsed = int(raw_value)
        except ValueError:
            logger.warning(
                "APP_DB_CACHE_SIZE_KIB=%s is invalid; skipping PRAGMA cache_size",
                raw_value,
            )
            return None
        if parsed <= 0:
            logger.warning(
                "APP_DB_CACHE_SIZE_KIB=%s must be positive; skipping PRAGMA cache_size",
                raw_value,
            )
            return None
        return parsed
