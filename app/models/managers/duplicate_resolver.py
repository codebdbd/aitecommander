"""Module for detecting and resolving duplicates in database."""

import logging

from ..base.db_base import db_lock

logger = logging.getLogger(__name__)


class DuplicateResolver:
    """Management of duplicate record detection and resolution."""

    def __init__(self, db):
        """
        Args:
            db: Database instance for accessing connection
        """
        self.db = db

    def detect_case_insensitive_duplicates(self) -> dict:
        """Searches for case-insensitive name duplicates.

        Returns dict with keys 'sphere', 'section', 'category'. Values — list of groups,
        where each group is described as dict with fields:
          - scope: None | sphere_id | section_id
          - lname: name in lower case
          - ids: list of int IDs of conflicting records (in arbitrary order)
        """
        result = {"sphere": [], "section": [], "category": []}
        with db_lock:
            # Spheres: global scope
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

            # Sections: within one sphere
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

            # Categories: within one section
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
        """Resolves case-insensitive duplicates.

        strategy:
          - 'rename': keep record with minimum id, rename others by adding ' (#{id})'.
          - 'remove': delete all except record with minimum id.

        Returns report: dict with number of processed records per table.
        """
        if strategy not in {"rename", "remove"}:
            raise ValueError("Invalid strategy: 'rename' or 'remove'")

        report = {"sphere": 0, "section": 0, "category": 0}
        dups = self.detect_case_insensitive_duplicates()

        with db_lock:
            with self.db.connection:
                # Helper function to get current name by id/table
                def get_name(table: str, rec_id: int) -> str:
                    row = self.db.connection.execute(
                        f"SELECT name FROM {table} WHERE id=?", (rec_id,)
                    ).fetchone()
                    return dict(row)["name"] if row else ""

                # Group handler
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
        """Re-creates case-insensitive unique indexes for sphere/section/category.

        Useful to call after eliminating duplicates if indexes couldn't be created earlier.
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
