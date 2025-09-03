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

    # --- Qt helpers ---
    def _get_qapp(self):
        """Безопасно получает экземпляр QApplication или None."""
        try:
            return QApplication.instance()
        except RuntimeError:
            return None

    # --- Clipboard helpers ---
    def clipboard_has_text(self) -> bool:
        try:
            app = self._get_qapp()
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
            app = self._get_qapp()
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
            app = self._get_qapp()
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
            app = self._get_qapp()
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

            # 1) Подготовка категорий и батчевое создание
            batch_cats = self._prepare_categories_for_section(trees, section_id)
            if not batch_cats:
                return []

            created_list = self._ss.create_categories_bulk(batch_cats) or []
            if not created_list:
                return []

            # Индекс по имени для сопоставления созданных id с исходными деревьями
            index_by_name: dict[str, list[dict]] = {}
            for c in created_list:
                nm = c.get("name")
                if nm is None:
                    continue
                index_by_name.setdefault(nm, []).append(c)

            # 2) Генерация ссылок лениво и сбор созданных категорий
            created_categories: list[dict] = []
            links_iter = self._iter_links_for_created_categories(trees, index_by_name, created_categories)
            # Собираем ссылки в список единожды для батчевой вставки
            all_links = list(links_iter)
            if all_links:
                self._ls.batch_create_or_update_links(all_links)

            return created_categories
        except (ValueError, TypeError, KeyError, RuntimeError) as e:
            logger.exception(
                "paste_from_clipboard_to_section(section_id=%s) failed", section_id
            )
            return []

    # --- Internal helpers ---
    def _prepare_categories_for_section(self, trees: Iterable[dict], section_id: int) -> list[dict]:
        """Готовит данные категорий для вставки в указанный раздел.

        Возвращает список словарей для batch-создания. Исключает поля id/section_id из исходных данных.
        """
        def gen():
            sid = int(section_id)
            for tree in trees:
                src_cat = dict((tree or {}).get("category", {}))
                # исключаем служебные поля
                new_cat = {k: v for k, v in src_cat.items() if k not in {"id", "section_id"}}
                new_cat["section_id"] = sid
                yield new_cat

        return list(gen())

    def _iter_links_for_created_categories(
        self,
        trees: Iterable[dict],
        index_by_name: dict[str, list[dict]],
        created_categories_out: list[dict],
    ) -> Iterable[dict]:
        """Генерирует словари ссылок для только что созданных категорий.

        По имени категории сопоставляет созданные строки и возвращает ссылки, указывая верный category_id.
        Попутно заполняет created_categories_out копиями созданных категорий в порядке обработки.
        """
        for tree in trees:
            src_cat = dict((tree or {}).get("category", {}))
            src_links = (tree or {}).get("links", []) or []
            nm = src_cat.get("name")
            if not nm:
                continue
            if nm not in index_by_name or not index_by_name[nm]:
                continue
            cat_row = index_by_name[nm].pop(0)
            if not cat_row:
                continue
            created_categories_out.append(dict(cat_row))
            new_cat_id = int(cat_row.get("id"))

            for link in src_links:
                src = dict(link or {})
                name = src.get("name") or ""
                url = src.get("url") or ""
                if not name or not url:
                    continue
                ltype = src.get("type") or "web"
                notes = src.get("notes") or ""
                is_favorite = int(src.get("is_favorite") or 0)
                icon_path = src.get("icon_path") or "default.ico"
                args = src.get("args") or ""
                browser_key = src.get("browser_key")

                payload = {
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
                    payload["browser_key"] = browser_key
                yield payload
