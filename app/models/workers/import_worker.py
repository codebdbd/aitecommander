"""Worker для импорта структуры данных в фоновом потоке."""

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
        # Делаем deep copy чтобы избежать race conditions с UI
        self.data = copy.deepcopy(data or [])

    def do_work(self, connection) -> dict[str, int]:
        """Выполняет импорт структуры.

        Returns:
            Статистика импорта: {spheres: N, sections: N, categories: N, links: N}
        """
        root = self.data

        # Подсчет элементов для прогресса
        total_items = (
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

        self.emit_progress(0, total_items, "Подготовка данных...")

        # Фаза подготовки: нормализуем вход и строим связи
        spheres_items: list[dict] = []
        sections_items: list[dict] = []
        categories_items: list[dict] = []
        links_with_id: list[dict] = []
        links_without_id: list[dict] = []
        current = 0

        for s_idx, s in enumerate(root):
            if self.is_cancelled:
                return {}

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
                if self.is_cancelled:
                    return {}

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
                    if self.is_cancelled:
                        return {}

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

                    for ln_idx, ln in enumerate((cat or {}).get("links") or []):
                        if self.is_cancelled:
                            return {}

                        if not isinstance(ln, dict):
                            continue

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
                            links_with_id.append(link_data)
                        else:
                            links_without_id.append(link_data)

        # Очистка и вставка данных с rollback при ошибке
        try:
            # Начинаем транзакцию
            connection.execute("BEGIN")

            self.emit_progress(0, total_items, "Очистка базы данных...")

            connection.execute("DELETE FROM link")
            connection.execute("DELETE FROM category")
            connection.execute("DELETE FROM section")
            connection.execute("DELETE FROM sphere")

            # Вставка сфер
            self.emit_progress(
                current, total_items, f"Импорт сфер ({len(spheres_items)})..."
            )
            sphere_map = {}
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

            # Вставка разделов
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

            # Вставка категорий
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

            # Вставка ссылок
            total_links = len(links_with_id) + len(links_without_id)
            self.emit_progress(
                current, total_items, f"Импорт ссылок ({total_links})..."
            )

            for ln in links_with_id + links_without_id:
                if self.is_cancelled:
                    connection.rollback()
                    return {}

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

            connection.commit()

            self.emit_progress(total_items, total_items, "Импорт завершен")

            return {
                "spheres": len(sphere_map),
                "sections": len(section_map),
                "categories": len(category_map),
                "links": total_links,
            }

        except Exception as e:
            # Откатываем транзакцию при ошибке
            connection.rollback()
            logger.error(f"Ошибка при импорте: {e}")
            raise
