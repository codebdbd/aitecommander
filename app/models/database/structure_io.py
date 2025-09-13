"""
structure_io.py — экспорт/импорт полной структуры (bulk) с потокобезопасностью
и неизменностью входных данных. Приватные хелперы для апсерта вложенных
элементов также размещаются здесь.

Организационный перенос из app/models/db.py без функциональных изменений.
"""

from __future__ import annotations

import copy
import logging
import time
from typing import Dict, List

from app.models.link_type import LinkType

logger = logging.getLogger(__name__)


def export_full_structure(db) -> Dict[str, List]:
    try:
        # Загружаем все таблицы одной выборкой каждую под единой блокировкой
        t0 = time.perf_counter()
        with db_lock(db):
            spheres = db.connection.execute(
                "SELECT * FROM sphere ORDER BY position"
            ).fetchall()
            sections = db.connection.execute(
                "SELECT * FROM section ORDER BY position"
            ).fetchall()
            categories = db.connection.execute(
                "SELECT * FROM category ORDER BY position"
            ).fetchall()
            links = db.connection.execute(
                "SELECT * FROM link ORDER BY position"
            ).fetchall()
        t1 = time.perf_counter()

        # Подготовка индексов для сборки структуры
        spheres_by_id = {}
        sections_by_id = {}
        categories_by_id = {}

        sections_by_sphere = {}
        categories_by_section = {}

        # Преобразуем строки в dict и инициализируем контейнеры
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

        # Линки просто добавляем к категориям
        for ln in links:
            ld = dict(ln)
            cat_id = ld.get("category_id")
            cat_obj = categories_by_id.get(cat_id)
            if cat_obj is not None:
                cat_obj["links"].append(ld)

        # Собираем иерархию, сохраняя порядок по position (он уже в ORDER BY)
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
            len(spheres),
            len(sections),
            len(categories),
            len(links),
            db_ms,
            build_ms,
            total_ms,
        )
        if total_ms > 50.0:
            logger.info(
                "export_full_structure: завершено, total_ms=%.2f (>50ms), db_ms=%.2f, build_ms=%.2f",
                total_ms,
                db_ms,
                build_ms,
            )
        else:
            logger.debug("Экспорт структуры выполнен успешно (bulk-загрузка)")
        return {"spheres": spheres_data}
    except Exception as e:
        logger.error("Ошибка экспорта структуры: %s", e, exc_info=True)
        raise


def get_full_structure(db) -> List[Dict]:
    try:
        t0 = time.perf_counter()
        with db_lock(db):
            spheres_rows = db.connection.execute(
                "SELECT * FROM sphere ORDER BY position"
            ).fetchall()
            sections_rows = db.connection.execute(
                "SELECT * FROM section ORDER BY position"
            ).fetchall()
            categories_rows = db.connection.execute(
                "SELECT * FROM category ORDER BY position"
            ).fetchall()
            links_rows = db.connection.execute(
                "SELECT * FROM link ORDER BY position"
            ).fetchall()

        t1 = time.perf_counter()

        spheres_by_id: Dict[int, Dict] = {}
        sections_by_id: Dict[int, Dict] = {}
        categories_by_id: Dict[int, Dict] = {}

        sections_by_sphere: Dict[int, List[Dict]] = {}
        categories_by_section: Dict[int, List[Dict]] = {}

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

        for ln in links_rows:
            ld = dict(ln)
            cat_id = ld.get("category_id")
            if cat_id is None:
                continue
            cat_obj = categories_by_id.get(int(cat_id))
            if cat_obj is not None:
                cat_obj["links"].append(ld)

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
        logger.error("Ошибка получения полной структуры: %s", e, exc_info=True)
        raise


def db_lock(db):  # helper to access the same lock the Database uses
    from app.utils.db.synchronization import db_lock as _lock

    # возвращаем сам объект блокировки; используется как контекст-менеджер
    return _lock


def import_full_structure(db, data: List[Dict]):
    try:
        t0 = time.perf_counter()
        # Database.import_full_structure уже делает deepcopy входных данных.
        # Здесь используем данные как есть, чтобы избежать второго вызова deepcopy.
        root = data or []

        spheres_items: List[Dict] = []
        sections_items: List[Dict] = []
        categories_items: List[Dict] = []
        links_with_id: List[Dict] = []
        links_without_id: List[Dict] = []

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
                        try:
                            ld["type"] = LinkType.from_value(ld.get("type", "web")).value
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

        with db_lock(db):
            with db.connection:
                # Очистка таблиц
                db.connection.execute("DELETE FROM link")
                db.connection.execute("DELETE FROM category")
                db.connection.execute("DELETE FROM section")
                db.connection.execute("DELETE FROM sphere")

                # Сферы
                spheres_with_id = [x for x in spheres_items if x.get("id")]
                spheres_no_id = [x for x in spheres_items if not x.get("id")]
                if spheres_with_id:
                    db.connection.executemany(
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
                sphere_ref_to_id = {}
                for x in spheres_with_id:
                    sphere_ref_to_id[x["ref"]] = int(x["id"])  # задан явно
                for x in spheres_no_id:
                    cur = db.connection.execute(
                        "INSERT INTO sphere (name, icon_path, position) VALUES (?, ?, ?)",
                        (x.get("name", ""), x.get("icon_path", ""), int(x.get("position", 0))),
                    )
                    sphere_ref_to_id[x["ref"]] = int(cur.lastrowid)

                # Разделы
                for x in sections_items:
                    x["sphere_id"] = sphere_ref_to_id.get(x["sphere_ref"])  # FK
                sections_with_id = [x for x in sections_items if x.get("id")]
                sections_no_id = [x for x in sections_items if not x.get("id")]
                if sections_with_id:
                    db.connection.executemany(
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
                section_ref_to_id = {}
                for x in sections_with_id:
                    section_ref_to_id[x["ref"]] = int(x["id"])  # задан явно
                for x in sections_no_id:
                    cur = db.connection.execute(
                        "INSERT INTO section (name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?)",
                        (
                            x.get("name", ""),
                            int(x.get("sphere_id")),
                            x.get("icon_path", ""),
                            int(x.get("position", 0)),
                        ),
                    )
                    section_ref_to_id[x["ref"]] = int(cur.lastrowid)

                # Категории
                for x in categories_items:
                    x["section_id"] = section_ref_to_id.get(x["section_ref"])  # FK
                categories_with_id = [x for x in categories_items if x.get("id")]
                categories_no_id = [x for x in categories_items if not x.get("id")]
                if categories_with_id:
                    db.connection.executemany(
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
                category_ref_to_id = {}
                for x in categories_with_id:
                    category_ref_to_id[x["ref"]] = int(x["id"])  # задан явно
                for x in categories_no_id:
                    cur = db.connection.execute(
                        "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
                        (
                            x.get("name", ""),
                            int(x.get("section_id")),
                            x.get("icon_path", ""),
                            int(x.get("position", 0)),
                        ),
                    )
                    category_ref_to_id[x["ref"]] = int(cur.lastrowid)

                # Ссылки
                for l in links_with_id:
                    if not l.get("category_id"):
                        cref = l.get("_category_ref")
                        if cref is not None:
                            l["category_id"] = category_ref_to_id.get(cref)
                    l.pop("_category_ref", None)
                for l in links_without_id:
                    if not l.get("category_id"):
                        cref = l.get("_category_ref")
                        if cref is not None:
                            l["category_id"] = category_ref_to_id.get(cref)
                    l.pop("_category_ref", None)

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
                    db.connection.executemany(
                        sql,
                        [
                            (
                                int(l.get("id")),
                                int(l.get("category_id")),
                                l.get("name", ""),
                                l.get("url", ""),
                                l.get("type", "web"),
                                l.get("notes", ""),
                                int(l.get("is_favorite", 0) or 0),
                                l.get("last_used"),
                                l.get("icon_path", ""),
                                l.get("args", ""),
                                l.get("browser_key"),
                                int(l.get("position", 0)),
                            )
                            for l in links_with_id
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
                    for l in links_without_id:
                        db.connection.execute(
                            sql,
                            (
                                int(l.get("category_id")),
                                l.get("name", ""),
                                l.get("url", ""),
                                l.get("type", "web"),
                                l.get("notes", ""),
                                int(l.get("is_favorite", 0) or 0),
                                l.get("last_used"),
                                l.get("icon_path", ""),
                                l.get("args", ""),
                                l.get("browser_key"),
                                int(l.get("position", 0)),
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

        # Создаем резервную копию после большой операции импорта
        try:
            db.backup()
        except Exception as backup_err:
            logger.warning(
                "Не удалось создать резервную копию после импорта: %s",
                backup_err,
                exc_info=True,
            )
    except Exception as e:
        logger.error("Ошибка импорта структуры: %s", e, exc_info=True)
        raise
