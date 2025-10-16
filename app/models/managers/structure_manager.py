"""Module for managing full data structure in DB."""
import copy
import logging
import time
from typing import Dict, List

from ..base.db_base import DatabaseError, db_lock
from ..types.link_type import LinkType

logger = logging.getLogger(__name__)


class StructureManager:
    """Management of getting and importing full data structure."""

    def __init__(self, db):
        """
        Args:
            db: Database instance for accessing connection and signals
        """
        self.db = db

    def get_full_structure(self) -> List[Dict]:
        """Returns full data structure as nested dictionaries."""
        try:
            # Single bulk selections at all levels to avoid N+1
            t0 = time.perf_counter()
            with db_lock:
                spheres_rows = self.db.connection.execute(
                    "SELECT * FROM sphere ORDER BY position"
                ).fetchall()
                sections_rows = self.db.connection.execute(
                    "SELECT * FROM section ORDER BY position"
                ).fetchall()
                categories_rows = self.db.connection.execute(
                    "SELECT * FROM category ORDER BY position"
                ).fetchall()
                links_rows = self.db.connection.execute(
                    "SELECT * FROM link ORDER BY position"
                ).fetchall()

            t1 = time.perf_counter()

            # Indexes for hierarchy assembly
            spheres_by_id: Dict[int, Dict] = {}
            sections_by_id: Dict[int, Dict] = {}
            categories_by_id: Dict[int, Dict] = {}

            sections_by_sphere: Dict[int, List[Dict]] = {}
            categories_by_section: Dict[int, List[Dict]] = {}

            # Convert rows to dict and prepare containers
            for s in spheres_rows:
                sd = dict(s)
                sd["sections"] = []
                spheres_by_id[int(sd["id"])] = sd

            for sec in sections_rows:
                sc = dict(sec)
                sc["categories"] = []
                sec_id = int(sc["id"])
                sections_by_id[sec_id] = sc
                sections_by_sphere.setdefault(int(sc["sphere_id"]), []).append(sc)

            for cat in categories_rows:
                cd = dict(cat)
                cd["links"] = []
                cat_id = int(cd["id"])
                categories_by_id[cat_id] = cd
                categories_by_section.setdefault(int(cd["section_id"]), []).append(cd)

            # Distribute links by categories
            for ln in links_rows:
                ld = dict(ln)
                cat_id = ld.get("category_id")
                if cat_id is None:
                    continue
                cat_obj = categories_by_id.get(int(cat_id))
                if cat_obj is not None:
                    cat_obj["links"].append(ld)

            # Assemble final structure, preserving order by position
            spheres_data: List[Dict] = []
            for s in spheres_rows:
                s_obj = spheres_by_id[int(s["id"])]
                for sc in sections_by_sphere.get(int(s_obj["id"]), []):
                    sc["categories"] = categories_by_section.get(int(sc["id"]), [])
                    s_obj["sections"].append(sc)
                spheres_data.append(s_obj)

            t2 = time.perf_counter()
            total_ms = (t2 - t0) * 1000.0
            db_ms = (t1 - t0) * 1000.0
            build_ms = (t2 - t1) * 1000.0
            logger.debug(
                "get_full_structure: spheres=%d, sections=%d, categories=%d, links=%d, db_ms=%.2f, build_ms=%.2f, total_ms=%.2f",
                len(spheres_rows),
                len(sections_rows),
                len(categories_rows),
                len(links_rows),
                db_ms,
                build_ms,
                total_ms,
            )
            return spheres_data
        except Exception as e:
            logger.error("Error getting full structure: %s", e, exc_info=True)
            raise DatabaseError(f"Failed to get full structure: {e}")

    def import_full_structure(self, data: List[Dict]):
        """Clears database and imports data from structure.

        Thread-safe operation that doesn't modify input data.

        Args:
            data: List of dictionaries with data structure for import.
                  Original object remains unchanged.
        """
        operation = "import_full_structure"
        try:
            t0 = time.perf_counter()
            root = copy.deepcopy(data or [])
            
            # Count elements for progress
            total_items = (
                len(root) +
                sum(len((s or {}).get("sections", [])) for s in root) +
                sum(len((sec or {}).get("categories", []))
                    for s in root for sec in (s or {}).get("sections", [])) +
                sum(len((cat or {}).get("links", []))
                    for s in root for sec in (s or {}).get("sections", [])
                    for cat in (sec or {}).get("categories", []))
            )
            self.db.operation_started.emit(operation, total_items or 1)

            # --- Preparation phase: normalize input and build relations ---
            self.db.operation_progress.emit(operation, 0, total_items or 1, "Preparing data...")
            spheres_items: List[Dict] = []  # {ref, id?, name, icon_path, position}
            sections_items: List[Dict] = []  # {ref, id?, name, sphere_ref, icon_path, position}
            categories_items: List[Dict] = []  # {ref, id?, name, section_ref, icon_path, position}
            links_with_id: List[Dict] = []  # ready for executemany
            links_without_id: List[Dict] = []  # individual INSERT
            current = 0

            for s_idx, s in enumerate(root):
                if not isinstance(s, dict):
                    continue
                s_ref = id(s)
                s_name = s.get("name", "")
                s_pos = s.get("position", s_idx)
                s_icon = s.get("icon_path", "")
                spheres_items.append(
                    {
                        "ref": s_ref,
                        "id": s.get("id"),
                        "name": s_name,
                        "icon_path": s_icon,
                        "position": s_pos,
                    }
                )

                for c_idx, sec in enumerate((s or {}).get("sections") or []):
                    if not isinstance(sec, dict):
                        continue
                    sec_ref = id(sec)
                    sections_items.append(
                        {
                            "ref": sec_ref,
                            "id": sec.get("id"),
                            "name": sec.get("name", ""),
                            "icon_path": sec.get("icon_path", ""),
                            "position": sec.get("position", c_idx),
                            "sphere_ref": s_ref,
                        }
                    )

                    for k_idx, cat in enumerate((sec or {}).get("categories") or []):
                        if not isinstance(cat, dict):
                            continue
                        cat_ref = id(cat)
                        categories_items.append(
                            {
                                "ref": cat_ref,
                                "id": cat.get("id"),
                                "name": cat.get("name", ""),
                                "icon_path": cat.get("icon_path", ""),
                                "position": cat.get("position", k_idx),
                                "section_ref": sec_ref,
                            }
                        )

                        for l_idx, ln in enumerate((cat or {}).get("links") or []):
                            if not isinstance(ln, dict):
                                continue
                            ld = dict(ln)
                            # Minimum normalization
                            try:
                                ld["type"] = LinkType.from_value(ld.get("type", "web")).value
                            except Exception:
                                ld["type"] = LinkType.WEB.value
                            ld["is_favorite"] = int(ld.get("is_favorite", 0) or 0)
                            ld.setdefault("icon_path", "")
                            if ld.get("position") is None:
                                ld["position"] = l_idx
                            # Set deferred reference to category via ref
                            ld["_category_ref"] = cat_ref
                            if ld.get("id"):
                                links_with_id.append(ld)
                            else:
                                links_without_id.append(ld)

            # --- Insertion phase: one transaction, levels top to bottom ---
            with db_lock:
                with self.db.connection:
                    # Clear tables in dependency order
                    self.db.operation_progress.emit(operation, current, total_items or 1, "Clearing tables...")
                    self.db.connection.execute("DELETE FROM link")
                    self.db.connection.execute("DELETE FROM category")
                    self.db.connection.execute("DELETE FROM section")
                    self.db.connection.execute("DELETE FROM sphere")

                    # 1) Spheres
                    self.db.operation_progress.emit(operation, current, total_items or 1, f"Inserting spheres: {len(spheres_items)}")
                    spheres_with_id = [x for x in spheres_items if x.get("id")]
                    spheres_no_id = [x for x in spheres_items if not x.get("id")]

                    if spheres_with_id:
                        self.db.connection.executemany(
                            "INSERT INTO sphere (id, name, icon_path, position) VALUES (?, ?, ?, ?)",
                            [
                                (
                                    int(x["id"]),
                                    x.get("name", ""),
                                    x.get("icon_path", ""),
                                    int(x.get("position", 0)),
                                )
                                for x in spheres_with_id
                            ],
                        )

                    sphere_ref_to_id: Dict[int, int] = {}
                    for x in spheres_with_id:
                        sphere_ref_to_id[x["ref"]] = int(x["id"])  # explicitly set
                    for x in spheres_no_id:
                        cur = self.db.connection.execute(
                            "INSERT INTO sphere (name, icon_path, position) VALUES (?, ?, ?)",
                            (x.get("name", ""), x.get("icon_path", ""), int(x.get("position", 0))),
                        )
                        sphere_ref_to_id[x["ref"]] = int(cur.lastrowid)

                    # 2) Sections
                    self.db.operation_progress.emit(operation, len(spheres_items), total_items or 1, f"Inserting sections: {len(sections_items)}")
                    for x in sections_items:
                        x["sphere_id"] = sphere_ref_to_id.get(x["sphere_ref"])  # ensure FK
                    sections_with_id = [x for x in sections_items if x.get("id")]
                    sections_no_id = [x for x in sections_items if not x.get("id")]

                    if sections_with_id:
                        self.db.connection.executemany(
                            "INSERT INTO section (id, name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                            [
                                (
                                    int(x["id"]),
                                    x.get("name", ""),
                                    int(x.get("sphere_id")),
                                    x.get("icon_path", ""),
                                    int(x.get("position", 0)),
                                )
                                for x in sections_with_id
                            ],
                        )

                    section_ref_to_id: Dict[int, int] = {}
                    for x in sections_with_id:
                        section_ref_to_id[x["ref"]] = int(x["id"])  # задан явно
                    for x in sections_no_id:
                        cur = self.db.connection.execute(
                            "INSERT INTO section (name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?)",
                            (
                                x.get("name", ""),
                                int(x.get("sphere_id")),
                                x.get("icon_path", ""),
                                int(x.get("position", 0)),
                            ),
                        )
                        section_ref_to_id[x["ref"]] = int(cur.lastrowid)

                    # 3) Categories
                    self.db.operation_progress.emit(operation, len(spheres_items) + len(sections_items), total_items or 1, f"Inserting categories: {len(categories_items)}")
                    for x in categories_items:
                        x["section_id"] = section_ref_to_id.get(x["section_ref"])  # ensure FK
                    categories_with_id = [x for x in categories_items if x.get("id")]
                    categories_no_id = [x for x in categories_items if not x.get("id")]

                    if categories_with_id:
                        self.db.connection.executemany(
                            "INSERT INTO category (id, name, section_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                            [
                                (
                                    int(x["id"]),
                                    x.get("name", ""),
                                    int(x.get("section_id")),
                                    x.get("icon_path", ""),
                                    int(x.get("position", 0)),
                                )
                                for x in categories_with_id
                            ],
                        )

                    category_ref_to_id: Dict[int, int] = {}
                    for x in categories_with_id:
                        category_ref_to_id[x["ref"]] = int(x["id"])  # explicitly set
                    for x in categories_no_id:
                        cur = self.db.connection.execute(
                            "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
                            (
                                x.get("name", ""),
                                int(x.get("section_id")),
                                x.get("icon_path", ""),
                                int(x.get("position", 0)),
                            ),
                        )
                        category_ref_to_id[x["ref"]] = int(cur.lastrowid)

                    # 4) Links
                    total_links = len(links_with_id) + len(links_without_id)
                    self.db.operation_progress.emit(operation, len(spheres_items) + len(sections_items) + len(categories_items), total_items or 1, f"Inserting links: {total_links}")
                    # Set actual category_id from map
                    for link in links_with_id:
                        if not link.get("category_id"):
                            cref = link.get("_category_ref")
                            if cref is not None:
                                link["category_id"] = category_ref_to_id.get(cref)
                        link.pop("_category_ref", None)
                    for link in links_without_id:
                        if not link.get("category_id"):
                            cref = link.get("_category_ref")
                            if cref is not None:
                                link["category_id"] = category_ref_to_id.get(cref)
                        link.pop("_category_ref", None)

                    if links_with_id:
                        cols = [
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
                        placeholders = ",".join(["?"] * len(cols))
                        sql = f"INSERT INTO link ({', '.join(cols)}) VALUES ({placeholders})"
                        self.db.connection.executemany(
                            sql,
                            [
                                (
                                    int(link.get("id")),
                                    int(link.get("category_id")),
                                    link.get("name", ""),
                                    link.get("url", ""),
                                    link.get("type", "web"),
                                    link.get("notes", ""),
                                    int(link.get("is_favorite", 0) or 0),
                                    link.get("last_used"),
                                    link.get("icon_path", ""),
                                    link.get("args", ""),
                                    link.get("browser_key"),
                                    int(link.get("position", 0)),
                                )
                                for link in links_with_id
                            ],
                        )

                    # Respect agreed hotfix: individual INSERT for links without id
                    if links_without_id:
                        cols = [
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
                        placeholders = ", ".join(["?"] * len(cols))
                        sql = f"INSERT INTO link ({', '.join(cols)}) VALUES ({placeholders})"
                        for link in links_without_id:
                            self.db.connection.execute(
                                sql,
                                (
                                    int(link.get("category_id")),
                                    link.get("name", ""),
                                    link.get("url", ""),
                                    link.get("type", "web"),
                                    link.get("notes", ""),
                                    int(link.get("is_favorite", 0) or 0),
                                    link.get("last_used"),
                                    link.get("icon_path", ""),
                                    link.get("args", ""),
                                    link.get("browser_key"),
                                    int(link.get("position", 0)),
                                ),
                            )

            t1 = time.perf_counter()
            logger.info(
                "import_full_structure: spheres=%d (with_id=%d, no_id=%d), sections=%d (with_id=%d, no_id=%d), categories=%d (with_id=%d, no_id=%d), links=%d (with_id=%d, no_id=%d), total_ms=%.2f",
                len(spheres_items),
                sum(1 for x in spheres_items if x.get('id')),
                sum(1 for x in spheres_items if not x.get('id')),
                len(sections_items),
                sum(1 for x in sections_items if x.get('id')),
                sum(1 for x in sections_items if not x.get('id')),
                len(categories_items),
                sum(1 for x in categories_items if x.get('id')),
                sum(1 for x in categories_items if not x.get('id')),
                len(links_with_id) + len(links_without_id),
                len(links_with_id),
                len(links_without_id),
                (t1 - t0) * 1000.0,
            )

            self.db.operation_finished.emit(operation, True)
            
            # Create a backup asynchronously after a large import operation
            try:
                self.db.backup_async(
                    on_error=lambda e: logger.warning(
                        "Failed to create backup after import: %s", e
                    )
                )
            except Exception as backup_err:
                logger.warning(
                    "Failed to start backup after import: %s",
                    backup_err,
{{ ... }}
                )
            
            # Notify UI about successful structure import
            try:
                self.db.structure_loaded.emit()
            except Exception as signal_err:
                logger.debug(
                    "Error sending structure_loaded signal: %s",
                    signal_err,
                    exc_info=True,
                )
        except Exception as e:
            logger.error("Error importing structure: %s", e, exc_info=True)
            self.db.operation_finished.emit(operation, False)
            try:
                self.db.error_occurred.emit("Import error", str(e))
            except Exception:
                pass
            raise DatabaseError(f"Failed to import structure: {e}")
