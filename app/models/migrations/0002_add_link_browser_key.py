import sqlite3
from typing import Any


def migrate(conn: sqlite3.Connection, logger: Any) -> None:
    # Проверяем, есть ли уже колонка browser_key
    cols = conn.execute("PRAGMA table_info('link')").fetchall()
    names = {str(dict(r)["name"]) for r in cols}
    if "browser_key" in names:
        logger.debug("Миграция 0002: browser_key уже существует — пропуск")
        return
    conn.execute("ALTER TABLE link ADD COLUMN browser_key TEXT DEFAULT NULL")
    logger.info("Миграция 0002: добавлена колонка browser_key в link")
