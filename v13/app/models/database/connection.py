"""
connection.py — управление соединением с базой данных (ленивое подключение,
PRAGMA, корректное закрытие с WAL checkpoint). Перенос из app/models/db.py
без изменения поведения.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace


def get_connection(thread_local: SimpleNamespace, db_path: str) -> sqlite3.Connection:
    """Лениво создаёт соединение и возвращает его. Повторно использует
    соединение в пределах потока, если оно валидное. Поведение идентично
    Database.connection из app/models/db.py.
    """
    conn = getattr(thread_local, "conn", None)
    if conn is not None:
        try:
            conn.execute("SELECT 1").fetchone()
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            try:
                del thread_local.conn
            except Exception:
                pass

    thread_local.conn = sqlite3.connect(db_path, check_same_thread=False)
    thread_local.conn.row_factory = sqlite3.Row
    thread_local.conn.execute("PRAGMA foreign_keys = ON")
    thread_local.conn.execute("PRAGMA journal_mode=WAL")
    return thread_local.conn


def close_connection(thread_local: SimpleNamespace, logger, db_lock) -> None:
    """Закрывает соединение текущего потока. Выполняет WAL checkpoint(FULL)
    под db_lock перед закрытием, как в исходной реализации.
    """
    try:
        if hasattr(thread_local, "conn"):
            try:
                with db_lock:
                    thread_local.conn.execute("PRAGMA wal_checkpoint(FULL)")
                    thread_local.conn.commit()
                logger.debug("WAL checkpoint выполнен перед закрытием")
            except Exception as checkpoint_err:
                logger.warning(
                    "Ошибка WAL checkpoint при закрытии: %s",
                    checkpoint_err,
                    exc_info=True,
                )

            thread_local.conn.close()
            del thread_local.conn
            logger.debug("Соединение с базой данных закрыто")
    except Exception as e:
        logger.error("Ошибка закрытия соединения: %s", e, exc_info=True)
