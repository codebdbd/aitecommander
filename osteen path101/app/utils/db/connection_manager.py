import sqlite3
import threading
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Потокобезопасный менеджер соединений SQLite.

    Создаёт ленивое соединение на поток и применяет необходимые PRAGMA.
    Предоставляет методы для проверки состояния и корректного закрытия.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._thread_local = threading.local()

    @property
    def connection(self) -> sqlite3.Connection:
        conn = getattr(self._thread_local, "conn", None)
        if conn is not None:
            return conn
        # Создание нового соединения без тестового запроса
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode=WAL")
        self._thread_local.conn = conn
        return conn

    def is_connected(self) -> bool:
        try:
            conn = getattr(self._thread_local, "conn", None)
            if conn is None:
                return False
            conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    def close(self) -> None:
        try:
            conn = getattr(self._thread_local, "conn", None)
            if conn is None:
                return
            try:
                # Выполним WAL checkpoint перед закрытием (кроме in-memory)
                if self.db_path != ":memory:" and not str(self.db_path).startswith("file::memory:"):
                    conn.execute("PRAGMA wal_checkpoint(FULL)")
                    conn.commit()
                    logger.debug("WAL checkpoint выполнен перед закрытием (manager)")
            except Exception as checkpoint_err:
                logger.warning(
                    "Ошибка WAL checkpoint при закрытии (manager): %s", checkpoint_err, exc_info=True
                )
            conn.close()
            del self._thread_local.conn
            logger.debug("Соединение с базой данных закрыто (manager)")
        except Exception as e:
            logger.error("Ошибка закрытия соединения (manager): %s", e, exc_info=True)
