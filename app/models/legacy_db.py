import logging
import sqlite3
from pathlib import Path

from app.utils.db.migrations import MigrationRunner
from app.utils.db.synchronization import db_lock

from .db_base import DatabaseError

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def init_schema(db) -> None:
    """[DEPRECATED] Инициализация схемы напрямую из schema.sql.

    Оставлено для обратной совместимости; используйте систему миграций.
    """
    try:
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        with db_lock:
            db.connection.executescript(sql)
            db.commit()
        logger.info("Схема базы данных инициализирована через legacy_db.init_schema (deprecated)")
    except Exception as e:
        logger.error("Ошибка инициализации схемы (legacy): %s", e, exc_info=True)
        raise DatabaseError(f"Не удалось инициализировать схему базы данных: {e}")


def run_migrations(db) -> None:
    """[DEPRECATED] Ручной запуск миграций. Оставлено для совместимости."""
    try:
        runner = MigrationRunner(db.connection, MIGRATIONS_DIR)
        runner.run_all_pending()
    except Exception as e:
        logger.error("Ошибка выполнения миграций (legacy): %s", e, exc_info=True)
