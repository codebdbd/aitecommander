import sqlite3
from typing import Any


def migrate(conn: sqlite3.Connection, logger: Any) -> None:
    """
    Создаёт case-insensitive уникальные индексы для sphere/section/category.

    Важно: Если данные содержат дубликаты по регистру, создание индексов упадёт
    с OperationalError. В этом случае миграция прерывается исключением, версия
    схемы НЕ будет повышена. После устранения дубликатов повторный запуск пройдёт.
    """
    try:
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sphere_name_nocase
            ON sphere(name COLLATE NOCASE)
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_section_sphere_name_nocase
            ON section(sphere_id, name COLLATE NOCASE)
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_category_section_name_nocase
            ON category(section_id, name COLLATE NOCASE)
            """
        )
        logger.info(
            "Миграция 0004: NOCASE-индексы для sphere/section/category созданы (если отсутствовали)"
        )
    except sqlite3.OperationalError as e:
        logger.warning(
            "Миграция 0004: не удалось создать NOCASE-индексы (возможны дубликаты): %s",
            e,
        )
        raise
