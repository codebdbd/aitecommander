"""Сервис бизнес-логики контекстного меню структуры.
Инкапсулирует операции копирования/вставки категорий через буфер обмена и работу с БД.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Iterable, Optional

from PyQt6.QtWidgets import QApplication

from app.services.links_service import LinksService
from app.services.structure_service import StructureService

logger = logging.getLogger(__name__)


class StructureContextService:
    """Бизнес-логика контекстного меню структуры без привязки к UI-виджетам.

    Зависимости на уровне БД передаются через `db` (adapter/connection),
    операции с буфером производятся через QApplication.clipboard().
    """

    def __init__(self, db: Any):
        self.db = db
        self._ss = StructureService(db)
        self._ls = LinksService(db)

    # --- Clipboard helpers ---
    def clipboard_has_text(self) -> bool:
        try:
            app = QApplication.instance()
            if not app:
                return False
            md = app.clipboard().mimeData()
            return bool(md and md.hasText() and md.text())
        except RuntimeError as e:
            logger.error(
                "clipboard_has_text failed: %s: %s", type(e).__name__, e
            )
            return False

    def _clipboard_get_json(self) -> Optional[dict | list]:
        if not self.clipboard_has_text():
            return None
        try:
            app = QApplication.instance()
            if not app:
                return None
            txt = app.clipboard().text()
            return json.loads(txt) if txt else None
        except (json.JSONDecodeError, RuntimeError, TypeError) as e:
            logger.warning(
                "Failed to get and parse JSON from clipboard: %s: %s", type(e).__name__, e
            )
            return None

    def clipboard_has_pastable_category(self) -> bool:
        data = self._clipboard_get_json()
        if not data:
            return False
        if isinstance(data, dict):
            if {"category", "links"}.issubset(set(data.keys())):
                return True
            if data.get("type") == "category" and data.get("id"):
                return True
            if data.get("type") == "category_tree" and isinstance(data.get("tree"), dict):
                return True
            if data.get("type") == "category_trees" and isinstance(data.get("trees"), list):
                return True
        elif isinstance(data, list):
            return any(
                isinstance(t, dict) and {"category", "links"}.issubset(set(t.keys()))
                for t in data
            )
        return False

    # --- Copy operations ---
    def copy_category_tree_to_clipboard(self, cat_id: int) -> None:
        """Копирует полное поддерево категории в буфер обмена."""
        try:
            app = QApplication.instance()
            if not app:
                return
            tree = self._ss.export_category_tree(int(cat_id))
            payload = {"type": "category_tree", "tree": tree}
            app.clipboard().setText(json.dumps(payload, ensure_ascii=False))
        except (ValueError, TypeError, RuntimeError) as e:
            logger.exception(
                "copy_category_tree_to_clipboard failed for cat_id=%s", cat_id
            )

    def copy_categories_to_clipboard(self, cat_ids: Iterable[int]) -> None:
        """Копирует несколько категорий (каждую с её ссылками) в буфер обмена."""
        try:
            app = QApplication.instance()
            if not app:
                return
            trees: list[dict] = []
            for cid in cat_ids:
                try:
                    trees.append(self._ss.export_category_tree(int(cid)))
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "Skipping category with id=%s during copy: %s", cid, e
                    )
                    continue
            if not trees:
                return
            payload = {"type": "category_trees", "trees": trees}
            app.clipboard().setText(json.dumps(payload, ensure_ascii=False))
        except (RuntimeError, TypeError) as e:
            logger.exception("copy_categories_to_clipboard failed")

    # --- Paste operations ---
    def _normalize_to_tree_list(self, payload: object) -> list[dict]:
        """Нормализует данные буфера в список деревьев категорий."""
        if isinstance(payload, dict):
            if {"category", "links"}.issubset(set(payload.keys())):
                return [payload]
            if payload.get("type") == "category_tree" and isinstance(payload.get("tree"), dict):
                return [payload.get("tree")]  # type: ignore[return-value]
            if payload.get("type") == "category" and payload.get("id"):
                return [self._ss.export_category_tree(int(payload["id"]))]
            if payload.get("type") == "category_trees" and isinstance(payload.get("trees"), list):
                out: list[dict] = []
                for t in payload.get("trees", []):
                    if isinstance(t, dict) and {"category", "links"}.issubset(set(t.keys())):
                        out.append(t)
                return out
            return []
        if isinstance(payload, list):
            return [t for t in payload if isinstance(t, dict) and {"category", "links"}.issubset(set(t.keys()))]
        return []

    def paste_from_clipboard_to_section(self, section_id: int) -> list[dict]:
        """Вставляет категории из буфера в раздел. Возвращает список созданных категорий (словари)."""
        try:
            data = self._clipboard_get_json()
            if not data:
                return []
            trees = self._normalize_to_tree_list(data)
            if not trees:
                return []

            # 1) Создаём категории батчем
            batch_cats: list[dict] = []
            for tree in trees:
                src_cat = dict(tree.get("category", {}))
                new_cat_data = {k: v for k, v in src_cat.items() if k not in {"id", "section_id"}}
                new_cat_data["section_id"] = int(section_id)
                batch_cats.append(new_cat_data)

            created_categories: list[dict] = []
            if batch_cats:
                created_list = self._ss.create_categories_bulk(batch_cats) or []
                # индекс по имени (учёт дублей — списки)
                index_by_name: dict[str, list[dict]] = {}
                for c in created_list:
                    nm = c.get("name")
                    if nm is None:
                        continue
                    index_by_name.setdefault(nm, []).append(c)

                # 2) Собираем все ссылки для вставки
                all_links: list[dict] = []
                for tree in trees:
                    src_cat = dict(tree.get("category", {}))
                    src_links = list(tree.get("links", []))
                    nm = src_cat.get("name")
                    cat_row: Optional[dict] = None
                    if nm in index_by_name and index_by_name[nm]:
                        cat_row = index_by_name[nm].pop(0)
                    if not cat_row:
                        continue
                    created_categories.append(dict(cat_row))
                    new_cat_id = int(cat_row.get("id"))

                    for link in src_links:
                        src = dict(link)
                        name = src.get("name") or ""
                        url = src.get("url") or ""
                        ltype = src.get("type") or "web"
                        if not url or not name:
                            continue
                        notes = src.get("notes") or ""
                        is_favorite = int(src.get("is_favorite") or 0)
                        icon_path = src.get("icon_path") or "default.ico"
                        args = src.get("args") or ""
                        browser_key = src.get("browser_key")

                        link_data = {
                            "category_id": new_cat_id,
                            "name": name,
                            "url": url,
                            "type": ltype,
                            "notes": notes,
                            "is_favorite": is_favorite,
                            "icon_path": icon_path,
                            "args": args,
                        }
                        if browser_key is not None:
                            link_data["browser_key"] = browser_key
                        all_links.append(link_data)

                if all_links:
                    self._ls.batch_create_or_update_links(all_links)

            return created_categories
        except (ValueError, TypeError, KeyError, RuntimeError) as e:
            logger.exception(
                "paste_from_clipboard_to_section(section_id=%s) failed", section_id
            )
            return []
