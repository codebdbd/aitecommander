import copy
import logging
import time
from typing import Dict, List
import sqlite3

from app.models.link_type import LinkType

logger = logging.getLogger(__name__)


def import_full_structure(conn: sqlite3.Connection, data: List[Dict]):
    """Очищает базу и импортирует данные из структуры.

    Потокобезопасность и блокировки должны обеспечиваться на уровне вызывающего кода.
    Внутри выполняется одна транзакция для согласованности данных.
    """
    t0 = time.perf_counter()
    root = copy.deepcopy(data or [])

    # --- Фаза подготовки: нормализуем вход и строим связи ---
    spheres_items: List[Dict] = []  # {ref, id?, name, icon_path, position}
    sections_items: List[Dict] = []  # {ref, id?, name, sphere_ref, icon_path, position}
    categories_items: List[Dict] = []  # {ref, id?, name, section_ref, icon_path, position}
    links_with_id: List[Dict] = []  # готово к executemany
    links_without_id: List[Dict] = []  # поштучные INSERT

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
                    # Нормализация минимума
                    try:
                        ld["type"] = LinkType.from_value(ld.get("type", "web")).value
                    except Exception:
                        ld["type"] = LinkType.WEB.value
                    ld["is_favorite"] = int(ld.get("is_favorite", 0) or 0)
                    ld.setdefault("icon_path", "")
                    if ld.get("position") is None:
                        ld["position"] = l_idx
                    # Проставим отложенную ссылку на категорию через ref
                    ld["_category_ref"] = cat_ref
                    if ld.get("id"):
                        links_with_id.append(ld)
                    else:
                        links_without_id.append(ld)

    # --- Фаза вставки: одна транзакция, уровни сверху вниз ---
    with conn:
        # Очистка таблиц в порядке зависимостей
        conn.execute("DELETE FROM link")
        conn.execute("DELETE FROM category")
        conn.execute("DELETE FROM section")
        conn.execute("DELETE FROM sphere")

        # 1) Сферы
        spheres_with_id = [x for x in spheres_items if x.get("id")]
        spheres_no_id = [x for x in spheres_items if not x.get("id")]

        if spheres_with_id:
            conn.executemany(
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
            sphere_ref_to_id[x["ref"]] = int(x["id"])  # задан явно
        for x in spheres_no_id:
            cur = conn.execute(
                "INSERT INTO sphere (name, icon_path, position) VALUES (?, ?, ?)",
                (x.get("name", ""), x.get("icon_path", ""), int(x.get("position", 0))),
            )
            sphere_ref_to_id[x["ref"]] = int(cur.lastrowid)

        # 2) Разделы
        for x in sections_items:
            x["sphere_id"] = sphere_ref_to_id.get(x["sphere_ref"])  # гарантируем FK
        sections_with_id = [x for x in sections_items if x.get("id")]
        sections_no_id = [x for x in sections_items if not x.get("id")]

        if sections_with_id:
            conn.executemany(
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
            cur = conn.execute(
                "INSERT INTO section (name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?)",
                (
                    x.get("name", ""),
                    int(x.get("sphere_id")),
                    x.get("icon_path", ""),
                    int(x.get("position", 0)),
                ),
            )
            section_ref_to_id[x["ref"]] = int(cur.lastrowid)

        # 3) Категории
        for x in categories_items:
            x["section_id"] = section_ref_to_id.get(x["section_ref"])  # гарантируем FK
        categories_with_id = [x for x in categories_items if x.get("id")]
        categories_no_id = [x for x in categories_items if not x.get("id")]

        if categories_with_id:
            conn.executemany(
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
            category_ref_to_id[x["ref"]] = int(x["id"])  # задан явно
        for x in categories_no_id:
            cur = conn.execute(
                "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
                (
                    x.get("name", ""),
                    int(x.get("section_id")),
                    x.get("icon_path", ""),
                    int(x.get("position", 0)),
                ),
            )
            category_ref_to_id[x["ref"]] = int(cur.lastrowid)

        # 4) Ссылки
        # Проставим фактические category_id из карты
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
            conn.executemany(
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

        # Уважаем согласованный хотфикс: поштучные INSERT для ссылок без id
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
                conn.execute(
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

        # 5) Обновление ссылок без поля last_used задано как есть в исходной логике
        # (оставлено без изменений, если требуются доработки — делаются выше по стеку)

    t1 = time.perf_counter()
    logger.debug("import_full_structure: duration_ms=%.2f", (t1 - t0) * 1000.0)
