"""Module for importing/exporting database structure."""

import logging
import time

from ..base.db_base import DatabaseError, db_lock
from ..types.constants import PERFORMANCE_WARNING_THRESHOLD_MS
from ..types.link_type import LinkType

logger = logging.getLogger(__name__)


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
                self.db.operation_progress.emit(operation, 0, 4, "Loading spheres...")
                spheres = self.db.connection.execute(
                    "SELECT * FROM sphere ORDER BY position"
                ).fetchall()
                self.db.operation_progress.emit(operation, 1, 4, "Loading sections...")
                sections = self.db.connection.execute(
                    "SELECT * FROM section ORDER BY position"
                ).fetchall()
                self.db.operation_progress.emit(
                    operation, 2, 4, "Loading categories..."
                )
                categories = self.db.connection.execute(
                    "SELECT * FROM category ORDER BY position"
                ).fetchall()
                self.db.operation_progress.emit(operation, 3, 4, "Loading links...")
                links = self.db.connection.execute(
                    "SELECT * FROM link ORDER BY position"
                ).fetchall()
            t1 = time.perf_counter()

            # Prepare indexes for structure assembly
            spheres_by_id = {}
            sections_by_id = {}
            categories_by_id = {}

            sections_by_sphere = {}
            categories_by_section = {}

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
                operation, 4, 4, "Hierarchy assembly completed"
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


def _upsert_category_tree(tree: dict, connection) -> None:
    """Performs upsert of category and its links."""
    if not tree:
        return

    cat = (tree or {}).get("category") or {}
    links = (tree or {}).get("links") or []
    if not isinstance(cat, dict) or not cat:
        return

    # Upsert category
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

    if not cat_id:
        return

    # Upsert ссылок
    prepared_links = []
    for link in links or []:
        if not isinstance(link, dict):
            continue
        rec = dict(link)
        rec["category_id"] = cat_id
        rec["name"] = rec.get("name", "") or ""
        rec["url"] = rec.get("url", "") or ""
        rec["args"] = rec.get("args", "") or ""
        try:
            rec["type"] = LinkType.from_value(rec.get("type", "web")).value
        except Exception:
            rec["type"] = LinkType.WEB.value
        rec["notes"] = rec.get("notes", "") or ""
        rec["is_favorite"] = int(rec.get("is_favorite", 0) or 0)
        rec["icon_path"] = rec.get("icon_path", "default.ico") or "default.ico"
        prepared_links.append(rec)

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

    next_pos = None

    def ensure_position(rec: dict) -> None:
        nonlocal next_pos
        if rec.get("position") is not None:
            return
        if next_pos is None:
            row = connection.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 AS next_pos FROM link WHERE category_id=?",
                (cat_id,),
            ).fetchone()
            try:
                next_pos = int(dict(row)["next_pos"]) if row is not None else 0
            except Exception:
                next_pos = 0
        rec["position"] = next_pos
        next_pos += 1 if next_pos is not None else 1

    for rec in prepared_links:
        iid = rec.get("id")
        if iid:
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
            continue

        ensure_position(rec)
        columns = [f for f in all_fields if f != "id"]
        placeholders = ", ".join(["?"] * len(columns))
        values = [rec.get(c) for c in columns]
        try:
            connection.execute(
                f"INSERT INTO link ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(values),
            )
        except Exception:
            pass
