"""Worker для экспорта структуры данных в фоновом потоке."""

import logging
import os
import sqlite3
from typing import Optional

from .base_worker import DatabaseWorker

logger = logging.getLogger(__name__)


class ExportStructureWorker(DatabaseWorker):
    """Worker для выполнения export_full_structure() в фоновом потоке.

    Экспортирует полную структуру данных из БД в формате словаря.
    """

    def __init__(self, db_path: Optional[str] = None):
        super().__init__()
        self.db_path = str(db_path) if db_path else None

    def create_connection(self):
        if self.db_path:
            try:
                from app.core.database_manager import DatabaseManager

                current_path = str(DatabaseManager.get_db_path())
                if os.path.abspath(self.db_path) != os.path.abspath(current_path):
                    conn = sqlite3.connect(self.db_path)
                    conn.row_factory = sqlite3.Row
                    return conn
            except Exception as e:
                logger.debug("Falling back to standard connection for worker: %s", e)
        return super().create_connection()

    def do_work(self, connection) -> dict[str, list]:
        """Выполняет экспорт структуры.

        Returns:
            Словарь с ключами spheres (иерархическая структура),
            а также плоскими списками sections, categories, links.
        """
        self.emit_progress(0, 4, "Экспорт сфер...")

        # Экспорт сфер
        spheres_rows = connection.execute(
            "SELECT * FROM sphere ORDER BY position"
        ).fetchall()
        spheres = [dict(row) for row in spheres_rows]

        if self.is_cancelled:
            return {}

        self.emit_progress(1, 4, "Экспорт разделов...")

        # Экспорт разделов
        sections_rows = connection.execute(
            "SELECT * FROM section ORDER BY sphere_id, position"
        ).fetchall()
        sections = [dict(row) for row in sections_rows]

        if self.is_cancelled:
            return {}

        self.emit_progress(2, 4, "Экспорт категорий...")

        # Экспорт категорий
        categories_rows = connection.execute(
            "SELECT * FROM category ORDER BY section_id, position"
        ).fetchall()
        categories = [dict(row) for row in categories_rows]

        if self.is_cancelled:
            return {}

        self.emit_progress(3, 4, "Экспорт ссылок...")

        # Экспорт ссылок
        links_rows = connection.execute(
            "SELECT * FROM link ORDER BY category_id, position"
        ).fetchall()
        links = [dict(row) for row in links_rows]

        if self.is_cancelled:
            return {}

        # Построение вложенной иерархии для совместимости с ImportStructureWorker
        spheres_by_id = {}
        for s in spheres:
            sd = dict(s)
            sd["sections"] = []
            spheres_by_id[sd["id"]] = sd

        sections_by_sphere: dict[int, list[dict]] = {}
        categories_by_section: dict[int, list[dict]] = {}
        categories_by_id = {}

        for sec in sections:
            sc = dict(sec)
            sc["categories"] = []
            sections_by_sphere.setdefault(sc["sphere_id"], []).append(sc)

        for cat in categories:
            cd = dict(cat)
            cd["links"] = []
            categories_by_id[cd["id"]] = cd
            categories_by_section.setdefault(cd["section_id"], []).append(cd)

        for ln in links:
            ld = dict(ln)
            cat_id = ld.get("category_id")
            cat_obj = categories_by_id.get(cat_id)
            if cat_obj is not None:
                cat_obj["links"].append(ld)

        spheres_data: list[dict] = []
        for s in spheres:
            s_obj = spheres_by_id.get(s["id"])
            if s_obj is not None:
                for sc in sections_by_sphere.get(s_obj["id"], []):
                    sc["categories"] = categories_by_section.get(sc["id"], [])
                    s_obj["sections"].append(sc)
                spheres_data.append(s_obj)

        self.emit_progress(4, 4, "Экспорт завершен")

        return {
            "spheres": spheres_data,
            "sections": sections,
            "categories": categories,
            "links": links,
        }
