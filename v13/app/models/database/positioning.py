"""
positioning.py — массовое обновление позиций и валидация входных ID.

Организационный перенос из app/models/db.py без изменения логики.
"""

from __future__ import annotations

import logging
import time
import sqlite3
from typing import List

from app.models.db_base import VALID_POSITION_TABLES, ValidationError, DatabaseError

logger = logging.getLogger(__name__)


# Исключения импортируются из общего модуля, чтобы типы совпадали с ожидаемыми тестами


def _validate_ids(ids_in_order: List[int]) -> List[int]:
    """Проверяет и нормализует входные ID: типы, значения, уникальность.

    Возвращает список int ID. Бросает ValidationError при несоответствиях.
    """
    ids = list(ids_in_order or [])
    if not ids:
        return []

    for v in ids:
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValidationError(f"Некорректный ID в списке позиций: {v}")

    if len(set(ids)) != len(ids):
        raise ValidationError("Список ID содержит дубликаты")

    return ids


def _ensure_ids_exist(connection: sqlite3.Connection, lock, table_name: str, ids: List[int]) -> None:
    """Проверяет существование всех указанных ID в таблице. Бросает ValidationError при отсутствии."""
    with lock:
        existing_ids = set()
        SELECT_CHUNK = 900
        for s in range(0, len(ids), SELECT_CHUNK):
            part = ids[s : s + SELECT_CHUNK]
            placeholders = ",".join(["?"] * len(part))
            rows = connection.execute(
                f"SELECT id FROM {table_name} WHERE id IN ({placeholders})",
                tuple(part),
            ).fetchall()
            existing_ids.update(int(dict(row)["id"]) for row in rows)
    missing = [i for i in ids if i not in existing_ids]
    if missing:
        raise ValidationError(
            f"Не найдены записи с ID: {missing} в таблице {table_name}"
        )


def update_item_positions(connection: sqlite3.Connection, lock, table_name: str, ids_in_order: List[int]) -> None:
    """Обновляет поле 'position' для списка элементов в указанной таблице."""
    if table_name not in VALID_POSITION_TABLES:
        raise ValidationError(
            f"Недопустимое имя таблицы для обновления позиций: {table_name}"
        )

    try:
        ids = _validate_ids(ids_in_order)
        if not ids:
            logger.debug(
                "update_item_positions: пустой список ID для таблицы %s",
                table_name,
            )
            return

        _ensure_ids_exist(connection, lock, table_name, ids)

        # Проверка существования и обновление выполняются под ЕДИНЫМ lock
        with lock:
            _t0 = time.perf_counter()
            # Формируем пары (id, position) согласно порядку в ids
            id_pos_pairs = [(item_id, i) for i, item_id in enumerate(ids)]
            # Ограничение SQLite ~999 параметров — по 2 параметра на запись
            CHUNK_SIZE = 400
            with connection:
                batches = 0
                for start in range(0, len(id_pos_pairs), CHUNK_SIZE):
                    chunk = id_pos_pairs[start : start + CHUNK_SIZE]
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
                    connection.execute(sql, tuple(params))
                    batches += 1
            _t1 = time.perf_counter()
            logger.debug(
                "update_item_positions: table=%s, count=%d, batches=%d, chunk=%d, duration_ms=%.2f",
                table_name,
                len(ids),
                batches,
                CHUNK_SIZE,
                ((_t1 - _t0) * 1000.0),
            )
        logger.debug(
            "Обновлены позиции (%s шт.) в таблице %s",
            len(ids),
            table_name,
        )
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "Ошибка обновления позиций в таблице %s: %s",
            table_name,
            e,
            exc_info=True,
        )
        raise DatabaseError(f"Не удалось обновить позиции: {e}")
