import logging
import time
import sqlite3
from typing import List

logger = logging.getLogger(__name__)


def update_positions(conn: sqlite3.Connection, table_name: str, ids_in_order: List[int]) -> None:
    """Обновляет поле position для записей указанной таблицы в порядке ids_in_order.

    Предполагается, что валидация входных данных и наличие таблицы выполнены на уровне вызывающего кода.
    Здесь реализована только ядровая работа с БД (chunk'и и пакетные апдейты) для переиспользования.
    """
    t0 = time.perf_counter()

    # --- Проверка существования записей (чанками, чтобы не превысить лимит параметров SQLite ~999)
    existing_ids = set()
    SELECT_CHUNK = 900
    for s in range(0, len(ids_in_order), SELECT_CHUNK):
        part = ids_in_order[s : s + SELECT_CHUNK]
        placeholders = ",".join(["?"] * len(part))
        rows = conn.execute(
            f"SELECT id FROM {table_name} WHERE id IN ({placeholders})",
            tuple(part),
        ).fetchall()
        existing_ids.update(int(dict(row)["id"]) for row in rows)
    missing = [i for i in ids_in_order if i not in existing_ids]
    if missing:
        raise ValueError(f"Не найдены записи с ID: {missing} в таблице {table_name}")

    # --- Пакетное обновление позиций ---
    # Формируем пары (id, position) согласно порядку в ids
    id_pos_pairs = [(item_id, i) for i, item_id in enumerate(ids_in_order)]
    # Ограничение SQLite по количеству параметров по умолчанию ~999 — по 2 параметра на запись
    CHUNK_SIZE = 400
    with conn:
        batches = 0
        for start in range(0, len(id_pos_pairs), CHUNK_SIZE):
            chunk = id_pos_pairs[start : start + CHUNK_SIZE]
            # Подготавливаем VALUES плейсхолдеры и параметры (id, position)
            values_sql = ",".join(["(?,?)"] * len(chunk))
            params = []
            for _id, pos in chunk:
                params.extend([_id, pos])

            sql = f"""
                WITH newpos(id, position) AS (
                    VALUES {values_sql}
                )
                UPDATE {table_name}
                SET position = (
                    SELECT newpos.position FROM newpos WHERE newpos.id = {table_name}.id
                )
                WHERE id IN (SELECT id FROM newpos)
                """
            conn.execute(sql, tuple(params))
            batches += 1
    t1 = time.perf_counter()
    logger.debug(
        "update_positions(core): table=%s, count=%d, batches=%d, chunk=%d, duration_ms=%.2f",
        table_name,
        len(ids_in_order),
        batches,
        CHUNK_SIZE,
        (t1 - t0) * 1000.0,
    )
