"""Module for managing full data structure in DB - REFACTORED VERSION."""

import copy
import logging
import time

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

    def get_full_structure(self) -> list[dict]:
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
            spheres_by_id: dict[int, dict] = {}
            sections_by_id: dict[int, dict] = {}
            categories_by_id: dict[int, dict] = {}

            sections_by_sphere: dict[int, list[dict]] = {}
            categories_by_section: dict[int, list[dict]] = {}

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
                cat_id_value = ld.get("category_id")
                if cat_id_value is None or not isinstance(cat_id_value, int):
                    continue
                cat_obj = categories_by_id.get(cat_id_value)
                if cat_obj is not None:
                    cat_obj["links"].append(ld)

            # Assemble final structure, preserving order by position
            spheres_data: list[dict] = []
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
            raise DatabaseError(f"Failed to get full structure: {e}") from e

    def _count_total_items(self, root: list[dict]) -> int:
        """Count total items for progress tracking."""
        from app.models.utils.structure_stats import count_total_items
        
        return count_total_items(root)

    def _prepare_spheres(self, root: list[dict]) -> list[dict]:
        """Extract and normalize sphere data."""
        spheres_items = []
        for s_idx, s in enumerate(root):
            if not isinstance(s, dict):
                continue
            spheres_items.append(
                {
                    "ref": id(s),
                    "id": s.get("id"),
                    "name": s.get("name", ""),
                    "icon_path": s.get("icon_path", ""),
                    "position": s.get("position", s_idx),
                }
            )
        return spheres_items

    def _prepare_sections(self, root: list[dict]) -> list[dict]:
        """Extract and normalize section data with sphere references."""
        sections_items = []
        for s in root:
            if not isinstance(s, dict):
                continue
            s_ref = id(s)
            for c_idx, sec in enumerate((s or {}).get("sections") or []):
                if not isinstance(sec, dict):
                    continue
                sections_items.append(
                    {
                        "ref": id(sec),
                        "id": sec.get("id"),
                        "name": sec.get("name", ""),
                        "icon_path": sec.get("icon_path", ""),
                        "position": sec.get("position", c_idx),
                        "sphere_ref": s_ref,
                    }
                )
        return sections_items

    def _prepare_categories(self, root: list[dict]) -> list[dict]:
        """Extract and normalize category data with section references."""
        categories_items = []
        for s in root:
            if not isinstance(s, dict):
                continue
            for sec in (s or {}).get("sections") or []:
                if not isinstance(sec, dict):
                    continue
                sec_ref = id(sec)
                for k_idx, cat in enumerate((sec or {}).get("categories") or []):
                    if not isinstance(cat, dict):
                        continue
                    categories_items.append(
                        {
                            "ref": id(cat),
                            "id": cat.get("id"),
                            "name": cat.get("name", ""),
                            "icon_path": cat.get("icon_path", ""),
                            "position": cat.get("position", k_idx),
                            "section_ref": sec_ref,
                        }
                    )
        return categories_items

    def _prepare_links(self, root: list[dict]) -> tuple[list[dict], list[dict]]:
        """Extract and normalize link data with category references.

        Returns: (links_with_id, links_without_id)
        """
        links_with_id = []
        links_without_id = []

        for s in root:
            if not isinstance(s, dict):
                continue
            for sec in (s or {}).get("sections") or []:
                if not isinstance(sec, dict):
                    continue
                for cat in (sec or {}).get("categories") or []:
                    if not isinstance(cat, dict):
                        continue
                    cat_ref = id(cat)
                    for l_idx, ln in enumerate((cat or {}).get("links") or []):
                        if not isinstance(ln, dict):
                            continue
                        ld = dict(ln)
                        try:
                            ld["type"] = LinkType.from_value(
                                ld.get("type", "web")
                            ).value
                        except Exception:
                            ld["type"] = LinkType.WEB.value
                        ld["is_favorite"] = int(ld.get("is_favorite", 0) or 0)
                        ld.setdefault("icon_path", "")
                        if ld.get("position") is None:
                            ld["position"] = l_idx
                        ld["_category_ref"] = cat_ref

                        if ld.get("id"):
                            links_with_id.append(ld)
                        else:
                            links_without_id.append(ld)

        return links_with_id, links_without_id

    def _clear_tables(self, operation: str, current: int, total_items: int) -> None:
        """Clear all tables in dependency order."""
        self.db.operation_progress.emit(
            operation, current, total_items, "Clearing tables..."
        )
        self.db.connection.execute("DELETE FROM link")
        self.db.connection.execute("DELETE FROM category")
        self.db.connection.execute("DELETE FROM section")
        self.db.connection.execute("DELETE FROM sphere")

    def _insert_spheres(
        self, spheres_items: list[dict], operation: str, current: int, total_items: int
    ) -> dict[int, int]:
        """Insert spheres and return ref->id mapping."""
        self.db.operation_progress.emit(
            operation, current, total_items, f"Inserting spheres: {len(spheres_items)}"
        )

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

        sphere_ref_to_id: dict[int, int] = {}
        for x in spheres_with_id:
            sphere_ref_to_id[x["ref"]] = int(x["id"])
        for x in spheres_no_id:
            cur = self.db.connection.execute(
                "INSERT INTO sphere (name, icon_path, position) VALUES (?, ?, ?)",
                (
                    x.get("name", ""),
                    x.get("icon_path", ""),
                    int(x.get("position", 0)),
                ),
            )
            sphere_ref_to_id[x["ref"]] = int(cur.lastrowid)

        return sphere_ref_to_id

    def _insert_sections(
        self,
        sections_items: list[dict],
        sphere_ref_to_id: dict[int, int],
        operation: str,
        current: int,
        total_items: int,
    ) -> dict[int, int]:
        """Insert sections and return ref->id mapping."""
        self.db.operation_progress.emit(
            operation,
            current,
            total_items,
            f"Inserting sections: {len(sections_items)}",
        )

        for x in sections_items:
            x["sphere_id"] = sphere_ref_to_id.get(x["sphere_ref"])

        sections_with_id = [x for x in sections_items if x.get("id")]
        sections_no_id = [x for x in sections_items if not x.get("id")]

        if sections_with_id:
            self.db.connection.executemany(
                "INSERT INTO section (id, name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        int(x["id"]),
                        x.get("name", ""),
                        int(x.get("sphere_id") or 0),
                        x.get("icon_path", ""),
                        int(x.get("position", 0)),
                    )
                    for x in sections_with_id
                ],
            )

        section_ref_to_id: dict[int, int] = {}
        for x in sections_with_id:
            section_ref_to_id[x["ref"]] = int(x["id"])
        for x in sections_no_id:
            cur = self.db.connection.execute(
                "INSERT INTO section (name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?)",
                (
                    x.get("name", ""),
                    int(x.get("sphere_id") or 0),
                    x.get("icon_path", ""),
                    int(x.get("position", 0)),
                ),
            )
            section_ref_to_id[x["ref"]] = int(cur.lastrowid)

        return section_ref_to_id

    def _insert_categories(
        self,
        categories_items: list[dict],
        section_ref_to_id: dict[int, int],
        operation: str,
        current: int,
        total_items: int,
    ) -> dict[int, int]:
        """Insert categories and return ref->id mapping."""
        self.db.operation_progress.emit(
            operation,
            current,
            total_items,
            f"Inserting categories: {len(categories_items)}",
        )

        for x in categories_items:
            x["section_id"] = section_ref_to_id.get(x["section_ref"])

        categories_with_id = [x for x in categories_items if x.get("id")]
        categories_no_id = [x for x in categories_items if not x.get("id")]

        if categories_with_id:
            self.db.connection.executemany(
                "INSERT INTO category (id, name, section_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        int(x["id"]),
                        x.get("name", ""),
                        int(x.get("section_id") or 0),
                        x.get("icon_path", ""),
                        int(x.get("position", 0)),
                    )
                    for x in categories_with_id
                ],
            )

        category_ref_to_id: dict[int, int] = {}
        for x in categories_with_id:
            category_ref_to_id[x["ref"]] = int(x["id"])
        for x in categories_no_id:
            cur = self.db.connection.execute(
                "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
                (
                    x.get("name", ""),
                    int(x.get("section_id") or 0),
                    x.get("icon_path", ""),
                    int(x.get("position", 0)),
                ),
            )
            category_ref_to_id[x["ref"]] = int(cur.lastrowid)

        return category_ref_to_id

    def _insert_links(
        self,
        links_with_id: list[dict],
        links_without_id: list[dict],
        category_ref_to_id: dict[int, int],
        operation: str,
        current: int,
        total_items: int,
    ) -> None:
        """Insert links with resolved category references."""
        total_links = len(links_with_id) + len(links_without_id)
        self.db.operation_progress.emit(
            operation, current, total_items, f"Inserting links: {total_links}"
        )

        for link in links_with_id + links_without_id:
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
                        int(link.get("id") or 0),
                        int(link.get("category_id") or 0),
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
                        int(link.get("category_id") or 0),
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

    def import_full_structure(self, data: list[dict]):
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

            total_items = self._count_total_items(root)
            self.db.operation_started.emit(operation, total_items or 1)

            self.db.operation_progress.emit(
                operation, 0, total_items or 1, "Preparing data..."
            )

            spheres_items = self._prepare_spheres(root)
            sections_items = self._prepare_sections(root)
            categories_items = self._prepare_categories(root)
            links_with_id, links_without_id = self._prepare_links(root)

            with db_lock:
                with self.db.connection:
                    self._clear_tables(operation, 0, total_items or 1)

                    sphere_ref_to_id = self._insert_spheres(
                        spheres_items, operation, 0, total_items or 1
                    )

                    section_ref_to_id = self._insert_sections(
                        sections_items,
                        sphere_ref_to_id,
                        operation,
                        len(spheres_items),
                        total_items or 1,
                    )

                    category_ref_to_id = self._insert_categories(
                        categories_items,
                        section_ref_to_id,
                        operation,
                        len(spheres_items) + len(sections_items),
                        total_items or 1,
                    )

                    self._insert_links(
                        links_with_id,
                        links_without_id,
                        category_ref_to_id,
                        operation,
                        len(spheres_items)
                        + len(sections_items)
                        + len(categories_items),
                        total_items or 1,
                    )

            t1 = time.perf_counter()
            logger.info(
                "import_full_structure: spheres=%d (with_id=%d, no_id=%d), sections=%d (with_id=%d, no_id=%d), categories=%d (with_id=%d, no_id=%d), links=%d (with_id=%d, no_id=%d), total_ms=%.2f",
                len(spheres_items),
                sum(1 for x in spheres_items if x.get("id")),
                sum(1 for x in spheres_items if not x.get("id")),
                len(sections_items),
                sum(1 for x in sections_items if x.get("id")),
                sum(1 for x in sections_items if not x.get("id")),
                len(categories_items),
                sum(1 for x in categories_items if x.get("id")),
                sum(1 for x in categories_items if not x.get("id")),
                len(links_with_id) + len(links_without_id),
                len(links_with_id),
                len(links_without_id),
                (t1 - t0) * 1000.0,
            )

            self.db.operation_finished.emit(operation, True)

            try:
                self.db.backup_async(
                    on_error=lambda e: logger.warning(
                        "Failed to create backup after import: %s", e
                    )
                )
            except Exception as backup_err:
                logger.warning(
                    "Failed to start backup after import: %s", backup_err, exc_info=True
                )

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
            raise DatabaseError(f"Failed to import structure: {e}") from e
