"""
subtree_io.py — импорт/экспорт поддеревьев (раздел, категория) без вложенных
транзакций, одна внешняя транзакция на операцию.

Организационный перенос из app/models/db.py без изменения логики.
"""

from __future__ import annotations

import sqlite3
from typing import List, Callable, Dict, Any

from app.models.link_type import LinkType


def export_section_tree(db: Any) -> Callable[[int], Dict[str, Any]]:
    def _export(section_id: int) -> Dict[str, Any]:
        section = db.sections.get_section_by_id(section_id) or {}
        categories = []
        for cat_row in db.categories.get_categories(section_id):
            cat = cat_row.copy()
            links = db.links.get_links(cat["id"])  # уже список dict
            categories.append({"category": cat, "links": links})
        return {"section": section, "categories": categories}

    return _export


def import_section_tree(db: Any) -> Callable[[Dict[str, Any]], None]:
    def _import(tree: Dict[str, Any]) -> None:
        section = (tree or {}).get("section") or {}
        categories = (tree or {}).get("categories") or []
        if not section:
            return

        # Одна транзакция на весь импорт раздела (с удержанием db_lock)
        with db.transaction():
            # --- Upsert раздела с сохранением ID ---
            sec_id = section.get("id")
            name = section.get("name")
            sphere_id = section.get("sphere_id")
            icon_path = section.get("icon_path", "")
            position = section.get("position", 0)

            if sec_id:
                cur = db.connection.execute(
                    "UPDATE section SET name=?, sphere_id=?, icon_path=?, position=? WHERE id=?",
                    (name, sphere_id, icon_path, position, sec_id),
                )
                if cur.rowcount == 0:
                    db.connection.execute(
                        "INSERT INTO section (id, name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                        (sec_id, name, sphere_id, icon_path, position),
                    )
            else:
                cur = db.connection.execute(
                    "INSERT INTO section (name, sphere_id, icon_path, position) VALUES (?, ?, ?, ?)",
                    (name, sphere_id, icon_path, position),
                )
                sec_id = cur.lastrowid

            # --- Восстановление категорий и их ссылок ---
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
                    ccur = db.connection.execute(
                        "UPDATE category SET name=?, section_id=?, icon_path=?, position=? WHERE id=?",
                        (c_name, c_section_id, c_icon_path, c_position, cat_id),
                    )
                    if ccur.rowcount == 0:
                        db.connection.execute(
                            "INSERT INTO category (id, name, section_id, icon_path, position) VALUES (?, ?, ?, ?, ?)",
                            (cat_id, c_name, c_section_id, c_icon_path, c_position),
                        )
                else:
                    ccur = db.connection.execute(
                        "INSERT INTO category (name, section_id, icon_path, position) VALUES (?, ?, ?, ?)",
                        (c_name, c_section_id, c_icon_path, c_position),
                    )
                    cat_id = ccur.lastrowid

                # Upsert ссылок для категории без вложенных транзакций
                raw_links = []
                for link in links:
                    if not isinstance(link, dict):
                        continue
                    link_copy = dict(link)
                    link_copy["category_id"] = cat_id
                    raw_links.append(link_copy)
                if raw_links:
                    db.links._upsert_links_no_tx(raw_links)

    return _import


def export_category_tree(db: Any) -> Callable[[int], Dict[str, Any]]:
    def _export(category_id: int) -> Dict[str, Any]:
        cat = db.categories.get_category_by_id(category_id) or {}
        links = db.links.get_links(category_id)
        return {"category": cat, "links": links}

    return _export


def import_category_tree(db: Any) -> Callable[[Dict[str, Any]], None]:
    def _import(tree: Dict[str, Any]) -> None:
        with db.transaction():
            _upsert_category_tree(tree, db.connection)

    return _import


def import_category_trees_bulk(db: Any) -> Callable[[List[Dict[str, Any]]], None]:
    def _import(trees: List[Dict[str, Any]]) -> None:
        if not trees:
            return
        with db.transaction():
            for tree in trees:
                if not tree:
                    continue
                _upsert_category_tree(tree, db.connection)
        # Резервная копия после успешного bulk-импорта
        try:
            db.backup()
        except Exception:
            # Проглатываем как warning в исходной логике — логирование делает сам метод
            pass

    return _import


def _upsert_category_tree(tree: dict, connection: sqlite3.Connection) -> None:
    if not tree:
        return

    cat = (tree or {}).get("category") or {}
    links = (tree or {}).get("links") or []
    if not isinstance(cat, dict) or not cat:
        return

    # --- Upsert категории с сохранением ID ---
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

    # --- Upsert ссылок для категории (поштучно, без вложенных транзакций) ---
    # Нормализация входных элементов и назначение category_id
    prepared_links: List[dict] = []
    for link in links or []:
        if not isinstance(link, dict):
            continue
        rec = dict(link)
        rec["category_id"] = cat_id
        # Нормализация значений по умолчанию
        rec["name"] = rec.get("name", "") or ""
        rec["url"] = rec.get("url", "") or ""
        rec["args"] = rec.get("args", "") or ""
        # Нормализация типа к строковому значению
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

    # Подготовка столбцов таблицы link
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

    next_pos = None  # type: int | None

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
                next_pos_local = int(dict(row)["next_pos"]) if row is not None else 0
            except Exception:
                next_pos_local = 0
            next_pos = next_pos_local
        rec["position"] = next_pos
        next_pos = (next_pos or 0) + 1

    for rec in prepared_links:
        iid = rec.get("id")
        if iid:  # Обновление/восстановление по id
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

        # Новая запись: назначаем позицию при необходимости
        ensure_position(rec)
        columns = [f for f in all_fields if f != "id"]
        placeholders = ", ".join(["?"] * len(columns))
        values = [rec.get(c) for c in columns]
        try:
            cur = connection.execute(
                f"INSERT INTO link ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(values),
            )
            try:
                new_id = int(getattr(cur, "lastrowid", 0) or 0)
                if new_id:
                    rec["id"] = new_id
            except Exception:
                pass
        except sqlite3.IntegrityError:
            row = connection.execute(
                "SELECT id FROM link WHERE category_id=? AND name=? AND url=? AND args=?",
                (
                    rec.get("category_id"),
                    rec.get("name", ""),
                    rec.get("url", ""),
                    rec.get("args", ""),
                ),
            ).fetchone()
            if row:
                try:
                    rec["id"] = int(dict(row)["id"])  # stable key-based access
                except Exception:
                    pass
