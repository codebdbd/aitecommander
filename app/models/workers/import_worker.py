"""Worker для импорта структуры данных в фоновом потоке - REFACTORED."""

import copy
import logging

from ..types.link_type import LinkType
from .base_worker import DatabaseWorker

logger = logging.getLogger(__name__)


class ImportStructureWorker(DatabaseWorker):
    """Worker для выполнения import_full_structure() в фоновом потоке.

    Импортирует полную структуру данных (сферы, разделы, категории, ссылки)
    с поддержкой прогресса и отмены операции.
    """

    def __init__(self, db_path: str, data: list[dict]):
        """
        Args:
            db_path: Путь к файлу БД
            data: Структура данных для импорта
        """
        super().__init__(db_path)
        self.data = copy.deepcopy(data or [])

    def _count_total_items(self, root: list[dict]) -> int:
        """Count total items for progress tracking."""
        return (
            len(root)
            + sum(len((s or {}).get("sections", [])) for s in root)
            + sum(
                len((sec or {}).get("categories", []))
                for s in root
                for sec in (s or {}).get("sections", [])
            )
            + sum(
                len((cat or {}).get("links", []))
                for s in root
                for sec in (s or {}).get("sections", [])
                for cat in (sec or {}).get("categories", [])
            )
        )

    def _prepare_spheres(self, root: list[dict]) -> list[dict]:
        """Extract and normalize sphere data."""
        spheres_items: list[dict] = []
        for s_idx, s in enumerate(root):
            if self.is_cancelled:
                return spheres_items
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
        sections_items: list[dict] = []
        for s in root:
            if self.is_cancelled:
                return sections_items
            if not isinstance(s, dict):
                continue
            s_ref = id(s)
            for c_idx, sec in enumerate((s or {}).get("sections") or []):
                if self.is_cancelled:
                    return sections_items
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
        categories_items: list[dict] = []
        for s in root:
            if self.is_cancelled:
                return categories_items
            if not isinstance(s, dict):
                continue
            for sec in (s or {}).get("sections") or []:
                if self.is_cancelled:
                    return categories_items
                if not isinstance(sec, dict):
                    continue
                sec_ref = id(sec)
                for k_idx, cat in enumerate((sec or {}).get("categories") or []):
                    if self.is_cancelled:
                        return categories_items
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

    def _normalize_link(self, ln: dict, cat_ref: int, ln_idx: int) -> dict:
        """Normalize single link data."""
        link_type = LinkType.from_value(ln.get("type"))
        link_data = {
            "category_ref": cat_ref,
            "name": ln.get("name", ""),
            "url": ln.get("url", ""),
            "args": ln.get("args", ""),
            "type": link_type.value,
            "browser_key": ln.get("browser_key", ""),
            "icon_path": ln.get("icon_path", ""),
            "position": ln.get("position", ln_idx),
        }
        if ln.get("id"):
            link_data["id"] = ln["id"]
        return link_data

    def _process_category_links(
        self, cat: dict, links_with_id: list[dict], links_without_id: list[dict]
    ) -> None:
        """Process all links in a category."""
        cat_ref = id(cat)
        for ln_idx, ln in enumerate((cat or {}).get("links") or []):
            if self.is_cancelled:
                return
            if not isinstance(ln, dict):
                continue

            link_data = self._normalize_link(ln, cat_ref, ln_idx)

            if ln.get("id"):
                links_with_id.append(link_data)
            else:
                links_without_id.append(link_data)

    def _prepare_links(self, root: list[dict]) -> tuple[list[dict], list[dict]]:
        """Extract and normalize link data with category references.

        Returns: (links_with_id, links_without_id)
        """
        links_with_id: list[dict] = []
        links_without_id: list[dict] = []

        for s in root:
            if self.is_cancelled:
                return links_with_id, links_without_id
            if not isinstance(s, dict):
                continue
            for sec in (s or {}).get("sections") or []:
                if self.is_cancelled:
                    return links_with_id, links_without_id
                if not isinstance(sec, dict):
                    continue
                for cat in (sec or {}).get("categories") or []:
                    if self.is_cancelled:
                        return links_with_id, links_without_id
                    if not isinstance(cat, dict):
                        continue
                    self._process_category_links(cat, links_with_id, links_without_id)

        return links_with_id, links_without_id

    def _clear_tables(self, connection, total_items: int) -> None:
        """Clear all tables in dependency order."""
        self.emit_progress(0, total_items, "Очистка базы данных...")
        connection.execute("DELETE FROM link")
        connection.execute("DELETE FROM category")
        connection.execute("DELETE FROM section")
        connection.execute("DELETE FROM sphere")

    def _insert_spheres(
        self, connection, spheres_items: list[dict], total_items: int
    ) -> dict[int, int]:
        """Insert spheres and return ref->id mapping."""
        self.emit_progress(0, total_items, f"Импорт сфер ({len(spheres_items)})...")

        sphere_map = {}
        current = 0
        for sp in spheres_items:
            if self.is_cancelled:
                connection.rollback()
                return {}

            cursor = connection.execute(
                "INSERT INTO sphere (name, icon_path, position) VALUES (?, ?, ?)",
                (sp["name"], sp["icon_path"], sp["position"]),
            )
            sphere_map[sp["ref"]] = cursor.lastrowid
            current += 1
            if current % 10 == 0:
                self.emit_progress(current, total_items, "Импорт сфер...")

        return sphere_map

    def _insert_sections(
        self,
        connection,
        sections_items: list[dict],
        sphere_map: dict[int, int],
        total_items: int,
        current: int,
    ) -> dict[int, int]:
        """Insert sections and return ref->id mapping."""
        self.emit_progress(
            current, total_items, f"Импорт разделов ({len(sections_items)})..."
        )

        section_map = {}
        for sec in sections_items:
            if self.is_cancelled:
                connection.rollback()
                return {}

            sphere_id = sphere_map.get(sec["sphere_ref"])
            if not sphere_id:
                continue

            cursor = connection.execute(
                "INSERT INTO section (name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?)",
                (sec["name"], sphere_id, sec["icon_path"], sec["position"]),
            )
            section_map[sec["ref"]] = cursor.lastrowid
            current += 1
            if current % 10 == 0:
                self.emit_progress(current, total_items, "Импорт разделов...")

        return section_map

    def _insert_categories(
        self,
        connection,
        categories_items: list[dict],
        section_map: dict[int, int],
        total_items: int,
        current: int,
    ) -> dict[int, int]:
        """Insert categories and return ref->id mapping."""
        self.emit_progress(
            current, total_items, f"Импорт категорий ({len(categories_items)})..."
        )

        category_map = {}
        for cat in categories_items:
            if self.is_cancelled:
                connection.rollback()
                return {}

            section_id = section_map.get(cat["section_ref"])
            if not section_id:
                continue

            cursor = connection.execute(
                "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
                (cat["name"], section_id, cat["icon_path"], cat["position"]),
            )
            category_map[cat["ref"]] = cursor.lastrowid
            current += 1
            if current % 10 == 0:
                self.emit_progress(current, total_items, "Импорт категорий...")

        return category_map

    def _insert_links(
        self,
        connection,
        links_with_id: list[dict],
        links_without_id: list[dict],
        category_map: dict[int, int],
        total_items: int,
        current: int,
    ) -> int:
        """Insert links and return count of inserted links."""
        total_links = len(links_with_id) + len(links_without_id)
        self.emit_progress(current, total_items, f"Импорт ссылок ({total_links})...")

        for ln in links_with_id + links_without_id:
            if self.is_cancelled:
                connection.rollback()
                return 0

            category_id = category_map.get(ln["category_ref"])
            if not category_id:
                continue

            connection.execute(
                """INSERT INTO link 
                   (category_id, name, url, args, type, browser_key, icon_path, position)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    category_id,
                    ln["name"],
                    ln["url"],
                    ln["args"],
                    ln["type"],
                    ln["browser_key"],
                    ln["icon_path"],
                    ln["position"],
                ),
            )
            current += 1
            if current % 20 == 0:
                self.emit_progress(current, total_items, "Импорт ссылок...")

        return total_links

    def do_work(self, connection) -> dict[str, int]:
        """Выполняет импорт структуры.

        Returns:
            Статистика импорта: {spheres: N, sections: N, categories: N, links: N}
        """
        root = self.data

        total_items = self._count_total_items(root)
        self.emit_progress(0, total_items, "Подготовка данных...")

        spheres_items = self._prepare_spheres(root)
        if self.is_cancelled:
            return {}

        sections_items = self._prepare_sections(root)
        if self.is_cancelled:
            return {}

        categories_items = self._prepare_categories(root)
        if self.is_cancelled:
            return {}

        links_with_id, links_without_id = self._prepare_links(root)
        if self.is_cancelled:
            return {}

        try:
            connection.execute("BEGIN")

            self._clear_tables(connection, total_items)

            sphere_map = self._insert_spheres(connection, spheres_items, total_items)
            if self.is_cancelled:
                connection.rollback()
                return {}

            section_map = self._insert_sections(
                connection, sections_items, sphere_map, total_items, len(spheres_items)
            )
            if self.is_cancelled:
                connection.rollback()
                return {}

            category_map = self._insert_categories(
                connection,
                categories_items,
                section_map,
                total_items,
                len(spheres_items) + len(sections_items),
            )
            if self.is_cancelled:
                connection.rollback()
                return {}

            total_links = self._insert_links(
                connection,
                links_with_id,
                links_without_id,
                category_map,
                total_items,
                len(spheres_items) + len(sections_items) + len(categories_items),
            )
            if self.is_cancelled:
                connection.rollback()
                return {}

            connection.commit()
            self.emit_progress(total_items, total_items, "Импорт завершен")

            return {
                "spheres": len(sphere_map),
                "sections": len(section_map),
                "categories": len(category_map),
                "links": total_links,
            }

        except Exception as e:
            connection.rollback()
            logger.error(f"Ошибка при импорте: {e}")
            raise
