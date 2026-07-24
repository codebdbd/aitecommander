"""Module for importing/exporting database structure."""

import logging
import time

from PyQt6.QtCore import QCoreApplication, QT_TRANSLATE_NOOP

from ..base.db_base import DatabaseError, db_lock
from ..types.constants import PERFORMANCE_WARNING_THRESHOLD_MS
from ..utils.link_validators import normalize_link_fields
from ...utils.db.sql_helpers import build_in_clause_placeholders

logger = logging.getLogger(__name__)
_IMPORT_EXPORT_CONTEXT = "ImportExportProgress"
_LOADING_SPHERES = QT_TRANSLATE_NOOP(
    _IMPORT_EXPORT_CONTEXT, "Loading spheres..."
)
_LOADING_SECTIONS = QT_TRANSLATE_NOOP(
    _IMPORT_EXPORT_CONTEXT, "Loading sections..."
)
_LOADING_CATEGORIES = QT_TRANSLATE_NOOP(
    _IMPORT_EXPORT_CONTEXT, "Loading categories..."
)
_LOADING_LINKS = QT_TRANSLATE_NOOP(
    _IMPORT_EXPORT_CONTEXT, "Loading links..."
)
_HIERARCHY_COMPLETED = QT_TRANSLATE_NOOP(
    _IMPORT_EXPORT_CONTEXT, "Hierarchy assembly completed"
)


def _tr_import_export(text: str) -> str:
    return QCoreApplication.translate(_IMPORT_EXPORT_CONTEXT, text)


class ImportExportManager:
    """Management of data structure import/export."""

    def __init__(self, db):
        """
        Args:
            db: Database instance for accessing connection, models and signals
        """
        self.db = db

    def export_full_structure(self) -> dict[str, list]:
        """Exports entire data structure from DB as dictionary."""
        operation = "export_full_structure"
        try:
            self.db.operation_started.emit(operation, 4)
            # Load all tables with single query each under unified lock
            t0 = time.perf_counter()
            with db_lock:
                self.db.operation_progress.emit(
                    operation, 0, 4, _tr_import_export(_LOADING_SPHERES)
                )
                spheres = self.db.connection.execute(
                    "SELECT * FROM sphere ORDER BY position"
                ).fetchall()
                self.db.operation_progress.emit(
                    operation, 1, 4, _tr_import_export(_LOADING_SECTIONS)
                )
                sections = self.db.connection.execute(
                    "SELECT * FROM section ORDER BY position"
                ).fetchall()
                self.db.operation_progress.emit(
                    operation, 2, 4, _tr_import_export(_LOADING_CATEGORIES)
                )
                categories = self.db.connection.execute(
                    "SELECT * FROM category ORDER BY position"
                ).fetchall()
                self.db.operation_progress.emit(
                    operation, 3, 4, _tr_import_export(_LOADING_LINKS)
                )
                links = self.db.connection.execute(
                    "SELECT * FROM link ORDER BY position"
                ).fetchall()
            t1 = time.perf_counter()

            # Prepare indexes for structure assembly
            spheres_by_id = {}
            sections_by_id = {}
            categories_by_id = {}

            sections_by_sphere: dict[int, list[dict]] = {}
            categories_by_section: dict[int, list[dict]] = {}

            # Convert rows to dict and initialize containers
            for s in spheres:
                sd = dict(s)
                sd["sections"] = []
                spheres_by_id[sd["id"]] = sd

            for sec in sections:
                sc = dict(sec)
                sc["categories"] = []
                sections_by_id[sc["id"]] = sc
                sections_by_sphere.setdefault(sc["sphere_id"], []).append(sc)

            for cat in categories:
                cd = dict(cat)
                cd["links"] = []
                categories_by_id[cd["id"]] = cd
                categories_by_section.setdefault(cd["section_id"], []).append(cd)

            # Links are simply added to categories
            for ln in links:
                ld = dict(ln)
                cat_id = ld.get("category_id")
                cat_obj = categories_by_id.get(cat_id)
                if cat_obj is not None:
                    cat_obj["links"].append(ld)

            # Assemble hierarchy
            spheres_data: list[dict] = []
            for s in spheres:
                s_obj = spheres_by_id[s["id"]]
                for sc in sections_by_sphere.get(s_obj["id"], []):
                    sc["categories"] = categories_by_section.get(sc["id"], [])
                    s_obj["sections"].append(sc)
                spheres_data.append(s_obj)

            t2 = time.perf_counter()
            total_ms = (t2 - t0) * 1000.0
            db_ms = (t1 - t0) * 1000.0
            build_ms = (t2 - t1) * 1000.0
            logger.debug(
                "export_full_structure: spheres=%d, sections=%d, categories=%d, links=%d, db_ms=%.2f, build_ms=%.2f, total_ms=%.2f",
                len(spheres),
                len(sections),
                len(categories),
                len(links),
                db_ms,
                build_ms,
                total_ms,
            )
            if total_ms > PERFORMANCE_WARNING_THRESHOLD_MS:
                logger.info(
                    "export_full_structure: completed, total_ms=%.2f (>%.0fms)",
                    total_ms,
                    PERFORMANCE_WARNING_THRESHOLD_MS,
                )

            self.db.operation_progress.emit(
                operation, 4, 4, _tr_import_export(_HIERARCHY_COMPLETED)
            )
            self.db.operation_finished.emit(operation, True)
            return {"spheres": spheres_data}
        except Exception as e:
            logger.error("Error exporting structure: %s", e, exc_info=True)
            self.db.operation_finished.emit(operation, False)
            try:
                self.db.error_occurred.emit("Export error", str(e))
            except Exception:
                pass
            raise DatabaseError(f"Failed to export structure: {e}") from e

    def export_section_tree(self, section_id: int) -> dict:
        """Exports section along with all categories and links."""
        section = self.db.sections.get_section_by_id(section_id) or {}
        categories = []
        for cat_row in self.db.categories.get_categories(section_id):
            cat = cat_row.copy()
            links = self.db.links.get_links(cat["id"])
            categories.append({"category": cat, "links": links})
        return {"section": section, "categories": categories}

    def export_category_tree(self, category_id: int) -> dict:
        """Exports category along with all links."""
        cat = self.db.categories.get_category_by_id(category_id) or {}
        links = self.db.links.get_links(category_id)
        return {"category": cat, "links": links}

    def import_section_tree(self, tree: dict):
        """Restores section, its categories and all links from backup structure."""
        section = (tree or {}).get("section") or {}
        categories = (tree or {}).get("categories") or []
        if not section:
            return

        with self.db.transaction():
            sec_id = section.get("id")
            name = section.get("name")
            sphere_id = section.get("sphere_id")
            icon_path = section.get("icon_path", "")
            position = section.get("position", 0)

            if sec_id:
                cur = self.db.connection.execute(
                    "UPDATE section SET name=?, sphere_id=?, icon_path=?, position=? WHERE id=?",
                    (name, sphere_id, icon_path, position, sec_id),
                )
                if cur.rowcount == 0:
                    self.db.connection.execute(
                        "INSERT INTO section (id, name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                        (sec_id, name, sphere_id, icon_path, position),
                    )
            else:
                cur = self.db.connection.execute(
                    "INSERT INTO section (name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?)",
                    (name, sphere_id, icon_path, position),
                )
                sec_id = cur.lastrowid

            for item in categories:
                cat = (item or {}).get("category") or {}
                if not cat:
                    continue
                links = (item or {}).get("links") or []

                cat_id = cat.get("id")
                c_name = cat.get("name")
                c_section_id = cat.get("section_id", sec_id)
                c_icon_path = cat.get("icon_path", "")
                c_position = cat.get("position", 0)

                if cat_id:
                    ccur = self.db.connection.execute(
                        "UPDATE category SET name=?, section_id=?, icon_path=?, position=? WHERE id=?",
                        (c_name, c_section_id, c_icon_path, c_position, cat_id),
                    )
                    if ccur.rowcount == 0:
                        self.db.connection.execute(
                            "INSERT INTO category (id, name, section_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                            (cat_id, c_name, c_section_id, c_icon_path, c_position),
                        )
                else:
                    ccur = self.db.connection.execute(
                        "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
                        (c_name, c_section_id, c_icon_path, c_position),
                    )
                    cat_id = ccur.lastrowid

                raw_links = []
                for link in links:
                    if not isinstance(link, dict):
                        continue
                    link_copy = dict(link)
                    link_copy["category_id"] = cat_id
                    raw_links.append(link_copy)
                if raw_links:
                    self.db.links._upsert_links_no_tx(raw_links)

    def import_section_trees_bulk(self, trees: list[dict]) -> None:
        """Imports multiple section subtrees in ONE transaction."""
        if not trees:
            return

        if self._import_section_trees_bulk_fast(trees):
            return

        with self.db.transaction():
            for tree in trees:
                if not tree:
                    continue
                section = (tree or {}).get("section") or {}
                categories = (tree or {}).get("categories") or []
                if not section:
                    continue

                sec_id = section.get("id")
                name = section.get("name")
                sphere_id = section.get("sphere_id")
                icon_path = section.get("icon_path", "")
                position = section.get("position", 0)

                if sec_id:
                    cur = self.db.connection.execute(
                        "UPDATE section SET name=?, sphere_id=?, icon_path=?, position=? WHERE id=?",
                        (name, sphere_id, icon_path, position, sec_id),
                    )
                    if cur.rowcount == 0:
                        self.db.connection.execute(
                            "INSERT INTO section (id, name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                            (sec_id, name, sphere_id, icon_path, position),
                        )
                else:
                    cur = self.db.connection.execute(
                        "INSERT INTO section (name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?)",
                        (name, sphere_id, icon_path, position),
                    )
                    sec_id = cur.lastrowid

                for item in categories:
                    cat = (item or {}).get("category") or {}
                    if not cat:
                        continue
                    links = (item or {}).get("links") or []

                    cat_id = cat.get("id")
                    c_name = cat.get("name")
                    c_section_id = cat.get("section_id", sec_id)
                    c_icon_path = cat.get("icon_path", "")
                    c_position = cat.get("position", 0)

                    if cat_id:
                        ccur = self.db.connection.execute(
                            "UPDATE category SET name=?, section_id=?, icon_path=?, position=? WHERE id=?",
                            (c_name, c_section_id, c_icon_path, c_position, cat_id),
                        )
                        if ccur.rowcount == 0:
                            self.db.connection.execute(
                                "INSERT INTO category (id, name, section_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                                (cat_id, c_name, c_section_id, c_icon_path, c_position),
                            )
                    else:
                        ccur = self.db.connection.execute(
                            "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
                            (c_name, c_section_id, c_icon_path, c_position),
                        )
                        cat_id = ccur.lastrowid

                    raw_links = []
                    for link in links:
                        if not isinstance(link, dict):
                            continue
                        link_copy = dict(link)
                        link_copy["category_id"] = cat_id
                        raw_links.append(link_copy)
                    if raw_links:
                        self.db.links._upsert_links_no_tx(raw_links)

    def import_links_bulk(
        self,
        link_rows: list[dict],
    ) -> None:
        """Import multiple links in one transaction using existing bulk upsert path."""
        if not link_rows:
            return
        started_ts = time.perf_counter()
        links_with_id: list[dict] = []
        links_without_id: list[dict] = []
        for row in link_rows:
            if not isinstance(row, dict):
                continue
            rec = dict(row)
            if isinstance(rec.get("id"), int) and int(rec["id"]) > 0:
                links_with_id.append(rec)
            else:
                links_without_id.append(rec)
        prepare_ms = (time.perf_counter() - started_ts) * 1000.0
        if not links_with_id and not links_without_id:
            return
        bulk_ms = 0.0
        tx_started_ts = time.perf_counter()
        with self.db.transaction():
            bulk_started_ts = time.perf_counter()
            self._bulk_upsert_link_rows(links_with_id, links_without_id)
            bulk_ms = (time.perf_counter() - bulk_started_ts) * 1000.0
        tx_ms = (time.perf_counter() - tx_started_ts) * 1000.0
        total_ms = (time.perf_counter() - started_ts) * 1000.0
        logger.info(
            "[Perf] import_links_bulk: rows=%s with_id=%s without_id=%s prepare=%.2f ms bulk_upsert=%.2f ms tx=%.2f ms total=%.2f ms",
            len(link_rows),
            len(links_with_id),
            len(links_without_id),
            prepare_ms,
            bulk_ms,
            tx_ms,
            total_ms,
        )

    def _import_section_trees_bulk_fast(self, trees: list[dict]) -> bool:
        """Fast path for undo-restore where section/category ids are already known."""
        prepared = self._prepare_section_tree_bulk_rows(trees)
        if prepared is None:
            return False

        sections_rows, category_rows, links_with_id, links_without_id = prepared

        with self.db.transaction():
            self._bulk_upsert_section_rows(sections_rows)
            self._bulk_upsert_category_rows(category_rows)
            self._bulk_upsert_link_rows(links_with_id, links_without_id)
        return True

    def _prepare_section_tree_bulk_rows(
        self, trees: list[dict]
    ) -> tuple[list[dict], list[dict], list[dict], list[dict]] | None:
        sections_rows: list[dict] = []
        category_rows: list[dict] = []
        links_with_id: list[dict] = []
        links_without_id: list[dict] = []

        for tree in trees or []:
            if not tree:
                continue
            section = dict((tree or {}).get("section") or {})
            categories = (tree or {}).get("categories") or []
            if not section:
                continue
            sec_id = section.get("id")
            if not isinstance(sec_id, int) or sec_id <= 0:
                return None
            sections_rows.append(section)

            for item in categories:
                cat = dict((item or {}).get("category") or {})
                if not cat:
                    continue
                cat_id = cat.get("id")
                if not isinstance(cat_id, int) or cat_id <= 0:
                    return None
                if not isinstance(cat.get("section_id"), int):
                    cat["section_id"] = sec_id
                category_rows.append(cat)

                for link in (item or {}).get("links") or []:
                    if not isinstance(link, dict):
                        continue
                    all_fields = [
                        "id", "category_id", "name", "url", "type", "notes",
                        "is_favorite", "last_used", "icon_path", "args", "browser_key", "position",
                    ]
                    rec = normalize_link_fields(link, all_fields)
                    rec["category_id"] = int(cat_id)
                    if not rec.get("icon_path"):
                        rec["icon_path"] = ""
                    if isinstance(rec.get("id"), int) and int(rec["id"]) > 0:
                        links_with_id.append(rec)
                    else:
                        links_without_id.append(rec)

        return sections_rows, category_rows, links_with_id, links_without_id

    def _fetch_existing_ids(
        self, table: str, ids: list[int], *, chunk_size: int = 500
    ) -> set[int]:
        existing: set[int] = set()
        normalized = [int(value) for value in ids if isinstance(value, int) and value > 0]
        if not normalized:
            return existing
        for offset in range(0, len(normalized), chunk_size):
            chunk = normalized[offset : offset + chunk_size]
            placeholders = build_in_clause_placeholders(len(chunk))
            cursor = self.db.connection.execute(
                f"SELECT id FROM {table} WHERE id IN ({placeholders})",
                tuple(chunk),
            )
            existing.update(int(row["id"]) for row in cursor.fetchall())
        return existing

    def _bulk_upsert_section_rows(self, sections_rows: list[dict]) -> None:
        existing_ids = self._fetch_existing_ids(
            "section",
            [int(row["id"]) for row in sections_rows if isinstance(row.get("id"), int)],
        )
        updates = []
        inserts = []
        for row in sections_rows:
            payload = (
                row.get("name"),
                row.get("sphere_id"),
                row.get("icon_path", ""),
                row.get("position", 0),
                row.get("id"),
            )
            if int(row["id"]) in existing_ids:
                updates.append(payload)
            else:
                inserts.append((row.get("id"), *payload[:-1]))

        if updates:
            self.db.connection.executemany(
                "UPDATE section SET name=?, sphere_id=?, icon_path=?, position=? WHERE id=?",
                updates,
            )
        if inserts:
            self.db.connection.executemany(
                "INSERT INTO section (id, name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                inserts,
            )

    def _bulk_upsert_category_rows(self, category_rows: list[dict]) -> None:
        existing_ids = self._fetch_existing_ids(
            "category",
            [int(row["id"]) for row in category_rows if isinstance(row.get("id"), int)],
        )
        updates = []
        inserts = []
        for row in category_rows:
            payload = (
                row.get("name"),
                row.get("section_id"),
                row.get("icon_path", ""),
                row.get("position", 0),
                row.get("id"),
            )
            if int(row["id"]) in existing_ids:
                updates.append(payload)
            else:
                inserts.append((row.get("id"), *payload[:-1]))

        if updates:
            self.db.connection.executemany(
                "UPDATE category SET name=?, section_id=?, icon_path=?, position=? WHERE id=?",
                updates,
            )
        if inserts:
            self.db.connection.executemany(
                "INSERT INTO category (id, name, section_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                inserts,
            )

    def _bulk_upsert_link_rows(
        self,
        links_with_id: list[dict],
        links_without_id: list[dict],
    ) -> None:
        fetch_existing_ms = 0.0
        updates_exec_ms = 0.0
        inserts_with_id_exec_ms = 0.0
        inserts_without_id_exec_ms = 0.0
        if links_with_id:
            fetch_started_ts = time.perf_counter()
            existing_ids = self._fetch_existing_ids(
                "link",
                [int(row["id"]) for row in links_with_id if isinstance(row.get("id"), int)],
            )
            fetch_existing_ms = (time.perf_counter() - fetch_started_ts) * 1000.0
            update_params = []
            insert_params = []
            for row in links_with_id:
                payload = (
                    row.get("category_id"),
                    row.get("name"),
                    row.get("url"),
                    row.get("type"),
                    row.get("notes"),
                    int(row.get("is_favorite", 0) or 0),
                    row.get("last_used"),
                    row.get("icon_path"),
                    row.get("args"),
                    row.get("browser_key"),
                    row.get("position", 0) if row.get("position") is not None else 0,
                    row.get("id"),
                )
                if int(row["id"]) in existing_ids:
                    update_params.append(payload)
                else:
                    insert_params.append(
                        (
                            row.get("id"),
                            row.get("category_id"),
                            row.get("name"),
                            row.get("url"),
                            row.get("type"),
                            row.get("notes"),
                            int(row.get("is_favorite", 0) or 0),
                            row.get("last_used"),
                            row.get("icon_path"),
                            row.get("args"),
                            row.get("browser_key"),
                            row.get("position", 0) if row.get("position") is not None else 0,
                        )
                    )

            if update_params:
                update_exec_started_ts = time.perf_counter()
                self.db.connection.executemany(
                    "UPDATE link SET category_id=?, name=?, url=?, type=?, notes=?, is_favorite=?, last_used=?, icon_path=?, args=?, browser_key=?, position=? WHERE id=?",
                    update_params,
                )
                updates_exec_ms = (
                    time.perf_counter() - update_exec_started_ts
                ) * 1000.0
            if insert_params:
                insert_with_id_exec_started_ts = time.perf_counter()
                self.db.connection.executemany(
                    "INSERT INTO link (id, category_id, name, url, type, notes, is_favorite, last_used, icon_path, args, browser_key, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    insert_params,
                )
                inserts_with_id_exec_ms = (
                    time.perf_counter() - insert_with_id_exec_started_ts
                ) * 1000.0

        if links_without_id:
            insert_without_id_exec_started_ts = time.perf_counter()
            self.db.connection.executemany(
                "INSERT INTO link (category_id, name, url, type, notes, is_favorite, last_used, icon_path, args, browser_key, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        row.get("category_id"),
                        row.get("name"),
                        row.get("url"),
                        row.get("type"),
                        row.get("notes"),
                        int(row.get("is_favorite", 0) or 0),
                        row.get("last_used"),
                        row.get("icon_path"),
                        row.get("args"),
                        row.get("browser_key"),
                        row.get("position", 0) if row.get("position") is not None else 0,
                    )
                    for row in links_without_id
                ],
            )
            inserts_without_id_exec_ms = (
                time.perf_counter() - insert_without_id_exec_started_ts
            ) * 1000.0

        if links_with_id or links_without_id:
            logger.info(
                "[Perf] _bulk_upsert_link_rows: with_id=%s without_id=%s fetch_existing=%.2f ms update_exec=%.2f ms insert_with_id_exec=%.2f ms insert_without_id_exec=%.2f ms",
                len(links_with_id),
                len(links_without_id),
                fetch_existing_ms,
                updates_exec_ms,
                inserts_with_id_exec_ms,
                inserts_without_id_exec_ms,
            )


    def import_category_tree(self, tree: dict):
        """Restores category and all links from backup structure."""
        with self.db.transaction():
            _upsert_category_tree(tree, self.db.connection)

    def import_category_trees_bulk(self, trees: list) -> None:
        """Imports multiple category subtrees in ONE transaction."""
        if not trees:
            return

        try:
            with self.db.transaction():
                for tree in trees:
                    if not tree:
                        continue
                    _upsert_category_tree(tree, self.db.connection)

            # Backup asynchronously after successful bulk import
            try:
                self.db.backup_async(
                    on_error=lambda e, tb: logger.warning(
                        "Failed to create backup after bulk import: %s", e
                    )
                )
            except Exception as backup_err:
                logger.warning(
                    "Failed to start backup after bulk import: %s",
                    backup_err,
                )
        except Exception as e:
            logger.error("Error bulk importing category trees: %s", e)
            raise DatabaseError(f"Failed to import category trees: {e}") from e


def _upsert_category(cat, connection):
    """Upsert category and return its ID."""
    cat_id = cat.get("id")
    name = cat.get("name")
    section_id = cat.get("section_id")
    icon_path = cat.get("icon_path", "")
    position = cat.get("position", 0)

    if cat_id:
        cur = connection.execute(
            "UPDATE category SET name=?, section_id=?, icon_path=?, position=? WHERE id=?",
            (name, section_id, icon_path, position, cat_id),
        )
        if getattr(cur, "rowcount", 0) == 0:
            connection.execute(
                "INSERT INTO category (id, name, section_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                (cat_id, name, section_id, icon_path, position),
            )
    else:
        cur = connection.execute(
            "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
            (name, section_id, icon_path, position),
        )
        try:
            cat_id = int(getattr(cur, "lastrowid", 0) or 0)
        except Exception:
            cat_id = None
    return cat_id


def _prepare_link_record(link, cat_id):
    """Prepare link record for upsert."""
    all_fields = [
        "id", "category_id", "name", "url", "type", "notes",
        "is_favorite", "last_used", "icon_path", "args", "browser_key", "position"
    ]
    rec = normalize_link_fields(link, all_fields)
    rec["category_id"] = cat_id
    # Override icon_path default for import/export (compatibility)
    if not rec.get("icon_path"):
        rec["icon_path"] = ""
    return rec


def _upsert_link_with_id(rec, all_fields, connection):
    """Upsert link with existing ID."""
    iid = rec.get("id")
    if rec.get("position") is None:
        rec["position"] = 0
    update_fields = [f for f in all_fields if f != "id"]
    update_placeholders = ", ".join([f"{f}=?" for f in update_fields])
    update_values = [rec.get(f) for f in update_fields]
    cur = connection.execute(
        f"UPDATE link SET {update_placeholders} WHERE id=?",
        tuple(update_values + [iid]),
    )
    if getattr(cur, "rowcount", 0) == 0:
        insert_fields = all_fields
        placeholders = ", ".join(["?"] * len(insert_fields))
        insert_values = [rec.get(f) for f in insert_fields]
        connection.execute(
            f"INSERT INTO link ({', '.join(insert_fields)}) VALUES ({placeholders})",
            tuple(insert_values),
        )


def _insert_new_link(rec, all_fields, connection):
    """Insert new link without ID."""
    columns = [f for f in all_fields if f != "id"]
    placeholders = ", ".join(["?"] * len(columns))
    values = [rec.get(c) for c in columns]
    try:
        connection.execute(
            f"INSERT INTO link ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(values),
        )
    except Exception as e:
        logger.warning("Failed to insert link during import: %s", e)


def _extract_cat_and_links(tree: dict) -> tuple[dict | None, list]:
    """Extract category and links from tree, validating basic structure."""
    cat = (tree or {}).get("category") or {}
    links = (tree or {}).get("links") or []
    if not isinstance(cat, dict) or not cat:
        return None, []
    # Keep only dict links; ignore invalid entries
    clean_links = [link for link in (links or []) if isinstance(link, dict)]
    return cat, clean_links


def _compute_next_position(cat_id: int, connection) -> int:
    """Compute next available position for links in category."""
    row = connection.execute(
        "SELECT COALESCE(MAX(position), 0) + 1 AS next_pos FROM link WHERE category_id=?",
        (cat_id,),
    ).fetchone()
    try:
        return int(dict(row)["next_pos"]) if row is not None else 0
    except Exception:
        return 0


def _prepare_links_for_upsert(links: list[dict], cat_id: int, connection) -> list[dict]:
    """Prepare link records and assign positions for new items without explicit position."""
    prepared: list[dict] = []
    for link in links:
        prepared.append(_prepare_link_record(link, cat_id))

    # Assign sequential positions for new links without an explicit position
    next_pos: int | None = None
    for rec in prepared:
        if rec.get("id"):
            continue
        if rec.get("position") is not None:
            continue
        if next_pos is None:
            next_pos = _compute_next_position(cat_id, connection)
        rec["position"] = next_pos
        next_pos += 1
    return prepared


def _upsert_category_tree(tree: dict, connection) -> None:
    """Performs upsert of category and its links."""
    if not tree:
        return

    cat, links = _extract_cat_and_links(tree)
    if cat is None:
        return

    cat_id = _upsert_category(cat, connection)
    if not cat_id:
        return

    prepared_links = _prepare_links_for_upsert(links, cat_id, connection)
    if not prepared_links:
        return

    all_fields = [
        "id",
        "category_id",
        "name",
        "url",
        "type",
        "notes",
        "is_favorite",
        "last_used",
        "icon_path",
        "args",
        "browser_key",
        "position",
    ]

    for rec in prepared_links:
        if rec.get("id"):
            _upsert_link_with_id(rec, all_fields, connection)
        else:
            _insert_new_link(rec, all_fields, connection)
