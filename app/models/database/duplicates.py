"""
duplicates.py — диагностика и устранение регистронезависимых дубликатов
и (пере)создание уникальных NOCASE индексов.

Организационный перенос из app/models/db.py без изменения логики.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List


def detect_case_insensitive_duplicates(
    connection: sqlite3.Connection, lock: Any
) -> Dict[str, List[Dict[str, Any]]]:
    """Ищет case-insensitive дубликаты имён для sphere/section/category.

    Возвращает dict с ключами 'sphere', 'section', 'category'. Значения — список групп.
    """
    result: Dict[str, List[Dict[str, Any]]] = {
        "sphere": [],
        "section": [],
        "category": [],
    }
    with lock:
        # Сферы: глобальная область
        rows = connection.execute(
            """
            SELECT LOWER(name) AS lname, GROUP_CONCAT(id) AS ids, COUNT(*) AS cnt
            FROM sphere
            GROUP BY LOWER(name)
            HAVING cnt > 1
            """
        ).fetchall()
        for r in rows or []:
            ids = [int(x) for x in (r["ids"] or "").split(",") if x]
            result["sphere"].append({"scope": None, "lname": r["lname"], "ids": ids})

        # Разделы: внутри одной сферы
        rows = connection.execute(
            """
            SELECT sphere_id AS scope, LOWER(name) AS lname, GROUP_CONCAT(id) AS ids, COUNT(*) AS cnt
            FROM section
            GROUP BY sphere_id, LOWER(name)
            HAVING cnt > 1
            """
        ).fetchall()
        for r in rows or []:
            ids = [int(x) for x in (r["ids"] or "").split(",") if x]
            result["section"].append({"scope": int(r["scope"]), "lname": r["lname"], "ids": ids})

        # Категории: внутри одного раздела
        rows = connection.execute(
            """
            SELECT section_id AS scope, LOWER(name) AS lname, GROUP_CONCAT(id) AS ids, COUNT(*) AS cnt
            FROM category
            GROUP BY section_id, LOWER(name)
            HAVING cnt > 1
            """
        ).fetchall()
        for r in rows or []:
            ids = [int(x) for x in (r["ids"] or "").split(",") if x]
            result["category"].append({"scope": int(r["scope"]), "lname": r["lname"], "ids": ids})

    return result


def resolve_case_insensitive_duplicates(
    connection: sqlite3.Connection,
    lock: Any,
    dups: Dict[str, Any],
    strategy: str = "rename",
) -> Dict[str, int]:
    """Разрешает case-insensitive дубликаты по заданной стратегии.

    strategy:
      - 'rename': оставить запись с минимальным id, остальные переименовать, добавив ' (#{id})'.
      - 'remove': удалить все кроме записи с минимальным id.

    Возвращает отчёт: dict с количеством обработанных записей по таблицам.
    """
    if strategy not in {"rename", "remove"}:
        raise ValueError("Недопустимая стратегия: 'rename' или 'remove'")

    report: Dict[str, int] = {"sphere": 0, "section": 0, "category": 0}

    with lock:
        with connection:
            # Вспомогательная функция получить текущее имя по id/таблице
            def get_name(table: str, rec_id: int) -> str:
                row = connection.execute(f"SELECT name FROM {table} WHERE id=?", (rec_id,)).fetchone()
                return (dict(row)["name"] if row else "")

            # Обработчик группы
            def process_group(table: str, ids: List[int]) -> int:
                ids_sorted = sorted(int(i) for i in ids)
                _keep = ids_sorted[0]
                to_change = ids_sorted[1:]
                affected = 0
                if strategy == "rename":
                    for rid in to_change:
                        base_name = get_name(table, rid)
                        new_name = f"{base_name} (#{rid})"
                        connection.execute(f"UPDATE {table} SET name=? WHERE id=?", (new_name, rid))
                        affected += 1
                else:  # remove
                    for rid in to_change:
                        connection.execute(f"DELETE FROM {table} WHERE id=?", (rid,))
                        affected += 1
                return affected

            for grp in dups.get("sphere", []):
                report["sphere"] += process_group("sphere", grp["ids"])
            for grp in dups.get("section", []):
                report["section"] += process_group("section", grp["ids"])
            for grp in dups.get("category", []):
                report["category"] += process_group("category", grp["ids"])

    return report


def create_nocase_unique_indexes(connection: sqlite3.Connection, lock: Any) -> None:
    """Создаёт (если отсутствуют) уникальные индексы с COLLATE NOCASE."""
    with lock:
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sphere_name_nocase
            ON sphere(name COLLATE NOCASE)
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_section_sphere_name_nocase
            ON section(sphere_id, name COLLATE NOCASE)
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_category_section_name_nocase
            ON category(section_id, name COLLATE NOCASE)
            """
        )
        connection.commit()
