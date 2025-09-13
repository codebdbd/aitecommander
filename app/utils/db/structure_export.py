import logging
import time
from typing import Dict, List
import sqlite3

logger = logging.getLogger(__name__)


def export_full_structure(conn: sqlite3.Connection) -> Dict[str, List]:
    """Экспортирует всю структуру данных из БД в виде словаря.

    Выполняет bulk-выборки и собирает вложенную структуру в памяти.
    """
    try:
        # Загружаем все таблицы одной выборкой каждую
        t0 = time.perf_counter()
        spheres = conn.execute("SELECT * FROM sphere ORDER BY position").fetchall()
        sections = conn.execute("SELECT * FROM section ORDER BY position").fetchall()
        categories = conn.execute("SELECT * FROM category ORDER BY position").fetchall()
        links = conn.execute("SELECT * FROM link ORDER BY position").fetchall()
        t1 = time.perf_counter()

        # Подготовка индексов для сборки структуры
        spheres_by_id = {}
        sections_by_id = {}
        categories_by_id = {}

        sections_by_sphere = {}
        categories_by_section = {}

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

        for ln in links:
            ld = dict(ln)
            cat_id = ld.get("category_id")
            cat_obj = categories_by_id.get(cat_id)
            if cat_obj is not None:
                cat_obj["links"].append(ld)

        spheres_data: List[Dict] = []
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
            len(spheres), len(sections), len(categories), len(links), db_ms, build_ms, total_ms,
        )
        if total_ms > 50.0:
            logger.info(
                "export_full_structure: завершено, total_ms=%.2f (>50ms), db_ms=%.2f, build_ms=%.2f",
                total_ms, db_ms, build_ms,
            )
        else:
            logger.debug("Экспорт структуры выполнен успешно (bulk-загрузка)")
        return {"spheres": spheres_data}
    except Exception as e:
        logger.error("Ошибка экспорта структуры: %s", e, exc_info=True)
        raise
