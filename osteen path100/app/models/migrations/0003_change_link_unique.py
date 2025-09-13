import sqlite3
from typing import Any


def migrate(conn: sqlite3.Connection, logger: Any) -> None:
    """
    Пересоздание таблицы link с UNIQUE(category_id, name, url, args),
    если обнаружен старый уникальный индекс по (category_id, url, args, type).
    """
    # Проверяем текущие уникальные индексы таблицы link
    idx_list = conn.execute("PRAGMA index_list('link')").fetchall()
    need_migrate = False
    for idx in idx_list:
        # row: seq, name, unique, origin, partial
        try:
            unique = int(dict(idx).get("unique", 0))
            name = dict(idx).get("name")
        except Exception:
            unique = idx[2]
            name = idx[1]
        if unique == 1:
            cols = conn.execute(f"PRAGMA index_info('{name}')").fetchall()
            col_names = []
            for c in cols:
                try:
                    col_names.append(dict(c).get("name"))
                except Exception:
                    col_names.append(c[2])
            if col_names == ["category_id", "url", "args", "type"]:
                need_migrate = True
                break

    if not need_migrate:
        logger.debug("Миграция 0003: пересоздание link не требуется — пропуск")
        return

    logger.info("Миграция 0003: пересоздание link с UNIQUE(category_id,name,url,args)")
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS link_new (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id  INTEGER NOT NULL REFERENCES category(id) ON DELETE CASCADE,
                name         TEXT    NOT NULL,
                url          TEXT    NOT NULL,
                type         TEXT    NOT NULL CHECK(type IN ('web','file','program','script','chromeapp','folder')),
                notes        TEXT    DEFAULT '',
                is_favorite  INTEGER NOT NULL CHECK(is_favorite IN (0,1)) DEFAULT 0,
                last_used    TEXT    DEFAULT NULL,
                icon_path    TEXT    NOT NULL DEFAULT 'default.ico',
                args         TEXT    DEFAULT '',
                browser_key  TEXT    DEFAULT NULL,
                position     INTEGER NOT NULL DEFAULT 0,
                UNIQUE(category_id, name, url, args)
            )
            """
        )

        conn.execute(
            """
            INSERT OR IGNORE INTO link_new 
                (id, category_id, name, url, type, notes, is_favorite, last_used, icon_path, args, browser_key, position)
            SELECT id, category_id, name, url, type, notes, is_favorite, last_used, icon_path, args, browser_key, position
            FROM link
            """
        )

        conn.execute("DROP TABLE link")
        conn.execute("ALTER TABLE link_new RENAME TO link")
        conn.commit()
        logger.info("Миграция 0003: таблица link успешно пересоздана")
    except Exception as e:
        conn.rollback()
        logger.exception("Ошибка миграции 0003 (пересоздание link): %s", e)
        raise
