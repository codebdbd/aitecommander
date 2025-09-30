"""Модуль для обнаружения и разрешения дубликатов в базе данных."""
import logging

from ..base.db_base import db_lock

logger = logging.getLogger(__name__)


class DuplicateResolver:
    """Управление обнаружением и разрешением дубликатов записей."""

    def __init__(self, db):
        """
        Args:
            db: Экземпляр Database для доступа к соединению
        """
        self.db = db

    def detect_case_insensitive_duplicates(self) -> dict:
        """Ищет case-insensitive дубликаты имён.

        Возвращает dict с ключами 'sphere', 'section', 'category'. Значения — список групп,
        где каждая группа описана как dict с полями:
          - scope: None | sphere_id | section_id
          - lname: нижний регистр имени
          - ids: список int ID записей в конфликте (в произвольном порядке)
        """
        result = {"sphere": [], "section": [], "category": []}
        with db_lock:
            # Сферы: глобальная область
            rows = self.db.connection.execute(
                """
                SELECT LOWER(name) AS lname, GROUP_CONCAT(id) AS ids, COUNT(*) AS cnt
                FROM sphere
                GROUP BY LOWER(name)
                HAVING cnt > 1
                """
            ).fetchall()
            for r in rows or []:
                ids = [int(x) for x in (r["ids"] or "").split(",") if x]
                result["sphere"].append(
                    {"scope": None, "lname": r["lname"], "ids": ids}
                )

            # Разделы: внутри одной сферы
            rows = self.db.connection.execute(
                """
                SELECT sphere_id AS scope, LOWER(name) AS lname, GROUP_CONCAT(id) AS ids, COUNT(*) AS cnt
                FROM section
                GROUP BY sphere_id, LOWER(name)
                HAVING cnt > 1
                """
            ).fetchall()
            for r in rows or []:
                ids = [int(x) for x in (r["ids"] or "").split(",") if x]
                result["section"].append(
                    {"scope": int(r["scope"]), "lname": r["lname"], "ids": ids}
                )

            # Категории: внутри одного раздела
            rows = self.db.connection.execute(
                """
                SELECT section_id AS scope, LOWER(name) AS lname, GROUP_CONCAT(id) AS ids, COUNT(*) AS cnt
                FROM category
                GROUP BY section_id, LOWER(name)
                HAVING cnt > 1
                """
            ).fetchall()
            for r in rows or []:
                ids = [int(x) for x in (r["ids"] or "").split(",") if x]
                result["category"].append(
                    {"scope": int(r["scope"]), "lname": r["lname"], "ids": ids}
                )

        return result

    def resolve_case_insensitive_duplicates(self, strategy: str = "rename") -> dict:
        """Разрешает case-insensitive дубликаты.

        strategy:
          - 'rename': оставить запись с минимальным id, остальные переименовать, добавив ' (#{id})'.
          - 'remove': удалить все кроме записи с минимальным id.

        Возвращает отчёт: dict с количеством обработанных записей по таблицам.
        """
        if strategy not in {"rename", "remove"}:
            raise ValueError("Недопустимая стратегия: 'rename' или 'remove'")

        report = {"sphere": 0, "section": 0, "category": 0}
        dups = self.detect_case_insensitive_duplicates()

        with db_lock:
            with self.db.connection:
                # Вспомогательная функция получить текущее имя по id/таблице
                def get_name(table: str, rec_id: int) -> str:
                    row = self.db.connection.execute(
                        f"SELECT name FROM {table} WHERE id=?", (rec_id,)
                    ).fetchone()
                    return (dict(row)["name"] if row else "")

                # Обработчик группы
                def process_group(table: str, ids: list[int]):
                    ids_sorted = sorted(int(i) for i in ids)
                    _keep = ids_sorted[0]
                    to_change = ids_sorted[1:]
                    affected = 0
                    if strategy == "rename":
                        for rid in to_change:
                            base_name = get_name(table, rid)
                            new_name = f"{base_name} (#{rid})"
                            self.db.connection.execute(
                                f"UPDATE {table} SET name=? WHERE id=?", (new_name, rid)
                            )
                            affected += 1
                    else:  # remove
                        for rid in to_change:
                            self.db.connection.execute(
                                f"DELETE FROM {table} WHERE id=?", (rid,)
                            )
                            affected += 1
                    return affected

                for grp in dups.get("sphere", []):
                    report["sphere"] += process_group("sphere", grp["ids"])
                for grp in dups.get("section", []):
                    report["section"] += process_group("section", grp["ids"])
                for grp in dups.get("category", []):
                    report["category"] += process_group("category", grp["ids"])

        return report

    def create_nocase_unique_indexes(self) -> None:
        """Пере-создаёт case-insensitive уникальные индексы для sphere/section/category.

        Полезно вызвать после устранения дубликатов, если индексы ранее не удалось создать.
        """
        with db_lock:
            self.db.connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sphere_name_nocase
                ON sphere(name COLLATE NOCASE)
                """
            )
            self.db.connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_section_sphere_name_nocase
                ON section(sphere_id, name COLLATE NOCASE)
                """
            )
            self.db.connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_category_section_name_nocase
                ON category(section_id, name COLLATE NOCASE)
                """
            )
            self.db.commit()
