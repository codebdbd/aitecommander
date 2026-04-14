"""Structure context menu business logic service.
Encapsulates copy/paste operations for categories via clipboard and DB interaction.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterable
from typing import Any, cast

from PyQt6.QtWidgets import QApplication

from app.core.results import Result
from app.models.db import Database
from app.models.types.constants import CATEGORY_BULK_UUID_FIELD
from app.services.links_service import LinksService
from app.services.protocols import DatabaseProtocol
from app.services.structure_service import StructureService

logger = logging.getLogger(__name__)


class StructureContextService:
    """Structure context menu business logic without UI widget binding.

    DB-level dependencies are passed via `db` (adapter/connection),
    clipboard operations are performed via QApplication.clipboard().
    """

    def __init__(self, db: DatabaseProtocol):
        """Initializes context menu service.

        ✅ FIX: Uses DatabaseProtocol instead of Any.

        Args:
            db: Database instance
        """
        self.db = db

        concrete_db = cast(Database, db)
        self._ss = StructureService(concrete_db)
        self._ls = LinksService(concrete_db)

    # --- Qt helpers ---
    def _get_qapp(self):
        """Safely gets QApplication instance or None."""
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
            logger.error("clipboard_has_text failed: %s: %s", type(e).__name__, e)
            return False

    def _clipboard_get_json(self) -> dict | list | None:
        if not self.clipboard_has_text():
            return None
        try:
            app = self._get_qapp()
            if not app:
                return None
            txt = app.clipboard().text()
            if not txt:
                return None
            stripped = txt.lstrip()
            if not stripped or stripped[0] not in "{[":
                return None
            return json.loads(txt)
        except json.JSONDecodeError as e:
            logger.debug(
                "Clipboard JSON parse skipped: %s: %s",
                type(e).__name__,
                e,
            )
            return None
        except (RuntimeError, TypeError) as e:
            logger.warning(
                "Failed to get clipboard JSON: %s: %s",
                type(e).__name__,
                e,
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
            if data.get("type") == "category_tree" and isinstance(
                data.get("tree"), dict
            ):
                return True
            if data.get("type") == "category_trees" and isinstance(
                data.get("trees"), list
            ):
                return True
        elif isinstance(data, list):
            return any(
                isinstance(t, dict) and {"category", "links"}.issubset(set(t.keys()))
                for t in data
            )
        return False

    def clipboard_has_pastable_section(self) -> bool:
        data = self._clipboard_get_json()
        if not data or not isinstance(data, dict):
            if isinstance(data, list):
                return any(
                    isinstance(t, dict) and {"section", "categories"}.issubset(set(t.keys()))
                    for t in data
                )
            return False
        if {"section", "categories"}.issubset(set(data.keys())):
            return True
        if data.get("type") == "section_tree" and isinstance(data.get("tree"), dict):
            return True
        if data.get("type") == "section_trees" and isinstance(data.get("trees"), list):
            return True
        return False

    def get_clipboard_payload(self) -> dict | list | None:
        """Return parsed clipboard JSON payload."""
        return self._clipboard_get_json()

    def normalize_category_trees(self, payload: object) -> list[dict]:
        """Normalize payload to category tree list."""
        return self._normalize_to_tree_list(payload)

    def normalize_section_trees(self, payload: object) -> list[dict]:
        """Normalize payload to section tree list."""
        return self._normalize_to_section_tree_list(payload)

    # --- Copy operations ---
    def copy_section_tree_to_clipboard(self, section_id: int) -> None:
        """Copies full section subtree to clipboard."""
        try:
            app = self._get_qapp()
            if not app:
                return
            tree = self._ss.export_section_tree(int(section_id))
            payload = {"type": "section_tree", "tree": tree}
            app.clipboard().setText(json.dumps(payload, ensure_ascii=False))
        except (ValueError, TypeError, RuntimeError):
            logger.exception(
                "copy_section_tree_to_clipboard failed for section_id=%s", section_id
            )

    def copy_sections_to_clipboard(self, section_ids: Iterable[int]) -> None:
        """Copies multiple sections (each with categories+links) to clipboard."""
        try:
            app = self._get_qapp()
            if not app:
                return
            trees: list[dict] = []
            for sid in section_ids:
                try:
                    trees.append(self._ss.export_section_tree(int(sid)))
                except (ValueError, TypeError) as e:
                    logger.warning(
                        "Skipping section with id=%s during copy: %s", sid, e
                    )
                    continue
            if not trees:
                return
            payload = {"type": "section_trees", "trees": trees}
            app.clipboard().setText(json.dumps(payload, ensure_ascii=False))
        except (RuntimeError, TypeError):
            logger.exception("copy_sections_to_clipboard failed")

    def copy_category_tree_to_clipboard(self, cat_id: int) -> None:
        """Copies full category subtree to clipboard."""
        try:
            app = self._get_qapp()
            if not app:
                return
            tree = self._ss.export_category_tree(int(cat_id))
            payload = {"type": "category_tree", "tree": tree}
            app.clipboard().setText(json.dumps(payload, ensure_ascii=False))
        except (ValueError, TypeError, RuntimeError):
            logger.exception(
                "copy_category_tree_to_clipboard failed for cat_id=%s", cat_id
            )

    def copy_categories_to_clipboard(self, cat_ids: Iterable[int]) -> None:
        """Copies multiple categories (each with its links) to clipboard."""
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
        except (RuntimeError, TypeError):
            logger.exception("copy_categories_to_clipboard failed")

    # --- Paste operations ---
    def paste_from_clipboard_to_sphere(self, sphere_id: int) -> bool:
        """Pastes a section from clipboard to the given sphere."""
        try:
            data = self._clipboard_get_json()
            if not data:
                return False
            trees = self._normalize_to_section_tree_list(data)
            stats = self.paste_section_trees_to_sphere(trees, sphere_id)
            return bool(stats.get("created_section_ids") or stats.get("merged_category_ids") or stats.get("merged_link_ids"))
        except (ValueError, TypeError, KeyError, RuntimeError):
            logger.exception(
                "paste_from_clipboard_to_sphere(sphere_id=%s) failed", sphere_id
            )
            return False

    def _normalize_to_tree_list(self, payload: object) -> list[dict]:
        """Normalizes buffer data to list of category trees."""
        if isinstance(payload, dict):
            if {"category", "links"}.issubset(set(payload.keys())):
                return [payload]
            if payload.get("type") == "category_tree" and isinstance(
                payload.get("tree"), dict
            ):
                tree_value = payload.get("tree")
                return [dict(tree_value)] if isinstance(tree_value, dict) else []
            if payload.get("type") == "category" and payload.get("id"):
                return [self._ss.export_category_tree(int(payload["id"]))]
            if payload.get("type") == "category_trees" and isinstance(
                payload.get("trees"), list
            ):
                out: list[dict] = []
                for t in payload.get("trees", []):
                    if isinstance(t, dict) and {"category", "links"}.issubset(
                        set(t.keys())
                    ):
                        out.append(dict(t))
                return out
            return []
        if isinstance(payload, list):
            normalized: list[dict] = []
            for t in payload:
                if isinstance(t, dict) and {"category", "links"}.issubset(set(t.keys())):
                    normalized.append(dict(t))
            return normalized
        return []

    def _normalize_to_section_tree(self, payload: dict) -> dict:
        """Normalize buffer data to section tree dict."""
        if {"section", "categories"}.issubset(set(payload.keys())):
            return dict(payload)
        if payload.get("type") == "section_tree" and isinstance(payload.get("tree"), dict):
            tree_value = payload.get("tree")
            return dict(tree_value) if isinstance(tree_value, dict) else {}
        return {}

    def _normalize_to_section_tree_list(self, payload: object) -> list[dict]:
        """Normalize buffer data to list of section trees."""
        if isinstance(payload, dict):
            if {"section", "categories"}.issubset(set(payload.keys())):
                return [dict(payload)]
            if payload.get("type") == "section_tree" and isinstance(
                payload.get("tree"), dict
            ):
                tree_value = payload.get("tree")
                return [dict(tree_value)] if isinstance(tree_value, dict) else []
            if payload.get("type") == "section_trees" and isinstance(
                payload.get("trees"), list
            ):
                out: list[dict] = []
                for t in payload.get("trees", []):
                    if isinstance(t, dict) and {"section", "categories"}.issubset(
                        set(t.keys())
                    ):
                        out.append(dict(t))
                return out
            return []
        if isinstance(payload, list):
            normalized: list[dict] = []
            for t in payload:
                if isinstance(t, dict) and {"section", "categories"}.issubset(set(t.keys())):
                    normalized.append(dict(t))
            return normalized
        return []

    def paste_from_clipboard_to_section(self, section_id: int) -> list[dict]:
        """Pastes categories from clipboard to section. Returns list of created categories (dicts)."""
        try:
            data = self._clipboard_get_json()
            if not data:
                return []
            trees = self._normalize_to_tree_list(data)
            created, _created_links = self.paste_category_trees_to_section(trees, section_id)
            return created
        except (ValueError, TypeError, KeyError, RuntimeError):
            logger.exception(
                "paste_from_clipboard_to_section(section_id=%s) failed", section_id
            )
            return []

    def _unwrap_result_list(self, value: object) -> list[dict]:
        """Return list payload from Result or direct list."""
        if isinstance(value, Result):
            if value.is_success():
                payload = value.value
                return payload if isinstance(payload, list) else []
            if value.error:
                logger.warning(
                    "paste_from_clipboard_to_section: create_categories_bulk failed: %s",
                    value.error,
                )
            return []
        return value if isinstance(value, list) else []

    # --- Internal helpers ---
    def paste_category_trees_to_section(
        self, trees: Iterable[dict], section_id: int
    ) -> tuple[list[dict], list[int]]:
        """Paste category trees into section. Returns (created_categories, created_link_ids)."""
        return self._paste_category_trees_into_section(trees, section_id)

    def _paste_category_trees_into_section(
        self, trees: Iterable[dict], section_id: int
    ) -> tuple[list[dict], list[int]]:
        if not trees:
            return [], []
        # 1) Category preparation and batch creation
        batch_cats, bindings = self._prepare_categories_for_section(
            trees, section_id
        )
        if not batch_cats:
            return []

        created_list = self._unwrap_result_list(
            self._ss.create_categories_bulk(batch_cats)
        )
        if not created_list:
            return [], []

        created_by_uuid = {
            str(row.get(CATEGORY_BULK_UUID_FIELD)): dict(row)
            for row in created_list
            if row.get(CATEGORY_BULK_UUID_FIELD)
        }

        # 2) Lazy link generation and created category collection
        created_categories: list[dict] = []
        if created_by_uuid:
            links_iter = self._iter_links_for_created_categories_by_uuid(
                bindings, created_by_uuid, created_categories
            )
        else:
            index_by_name: dict[str, list[dict]] = {}
            for c in created_list:
                nm = c.get("name")
                if nm is None:
                    continue
                index_by_name.setdefault(nm, []).append(c)
            links_iter = self._iter_links_for_created_categories(
                trees, index_by_name, created_categories
            )
        # Collect links into list once for batch insertion
        all_links = list(links_iter)
        created_link_ids: list[int] = []
        if all_links:
            created_link_ids = self._ls.batch_create_or_update_links(all_links)

        return created_categories, created_link_ids

    def _prepare_categories_for_section(
        self, trees: Iterable[dict], section_id: int
    ) -> tuple[list[dict], list[tuple[str, dict]]]:
        """Prepares category data for insertion into specified section.

        Returns
        -------
        tuple[list[dict], list[tuple[str, dict]]]
            Prepared category payloads and a binding list that keeps a mapping
            from generated client UUID to the original tree node.
        """

        sid = int(section_id)
        prepared: list[dict] = []
        bindings: list[tuple[str, dict]] = []

        for tree in trees:
            tree_dict = dict(tree or {})
            src_cat = dict(tree_dict.get("category", {}) or {})
            # exclude service fields
            new_cat = {
                k: v for k, v in src_cat.items() if k not in {"id", "section_id"}
            }
            new_cat["section_id"] = sid
            token = uuid.uuid4().hex
            new_cat[CATEGORY_BULK_UUID_FIELD] = token
            prepared.append(new_cat)
            bindings.append((token, tree_dict))

        return prepared, bindings

    def _prepare_section_for_sphere(self, tree: dict, sphere_id: int) -> dict:
        """Prepare section tree for insertion into specified sphere."""
        tree_dict = dict(tree or {})
        section = dict(tree_dict.get("section", {}) or {})
        if not section:
            return {}
        section.pop("id", None)
        section["sphere_id"] = int(sphere_id)

        categories_out: list[dict] = []
        for item in tree_dict.get("categories") or []:
            if not isinstance(item, dict):
                continue
            cat = dict(item.get("category", {}) or {})
            if not cat:
                continue
            cat.pop("id", None)
            cat.pop("section_id", None)
            links_out: list[dict] = []
            for link in item.get("links") or []:
                if not isinstance(link, dict):
                    continue
                lcopy = dict(link)
                lcopy.pop("id", None)
                lcopy.pop("category_id", None)
                links_out.append(lcopy)
            categories_out.append({"category": cat, "links": links_out})

        return {"section": section, "categories": categories_out}

    def _normalize_name_key(self, name: object) -> str:
        if not isinstance(name, str):
            return ""
        return name.strip().lower()

    def _find_section_by_name(self, sphere_id: int, name: str) -> dict | None:
        try:
            sections = self.db.sections.get_sections(int(sphere_id)) or []
        except Exception:
            logger.exception(
                "Failed to load sections for sphere %s while merging", sphere_id
            )
            return None
        target = self._normalize_name_key(name)
        if not target:
            return None
        for sec in sections:
            sec_name = self._normalize_name_key((sec or {}).get("name"))
            if sec_name and sec_name == target:
                return dict(sec)
        return None

    def _group_category_items(self, categories: Iterable[dict]) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for item in categories:
            if not isinstance(item, dict):
                continue
            cat = (item or {}).get("category") or {}
            if not isinstance(cat, dict):
                continue
            key = self._normalize_name_key(cat.get("name"))
            if not key:
                continue
            grouped.setdefault(key, []).append(item)
        return grouped

    def _merge_category_items(self, items: list[dict]) -> dict | None:
        if not items:
            return None
        base = dict(items[0] or {})
        cat = dict(base.get("category") or {})
        if not cat:
            return None
        links_out: list[dict] = []
        for item in items:
            links_out.extend((item or {}).get("links") or [])
        base["category"] = cat
        base["links"] = links_out
        return base

    def _get_existing_categories_by_name(self, section_id: int) -> dict[str, dict]:
        try:
            categories = self.db.categories.get_categories(int(section_id)) or []
        except Exception:
            logger.exception(
                "Failed to load categories for section %s while merging", section_id
            )
            return {}
        out: dict[str, dict] = {}
        for cat in categories:
            if not isinstance(cat, dict):
                cat = dict(cat)
            key = self._normalize_name_key(cat.get("name"))
            if key and key not in out:
                out[key] = cat
        return out

    def _merge_section_tree_into_section(
        self,
        section_id: int,
        tree: dict,
        *,
        created_category_ids: list[int] | None = None,
        created_link_ids: list[int] | None = None,
    ) -> bool:
        categories = (tree or {}).get("categories") or []
        if not categories:
            return False
        grouped = self._group_category_items(categories)
        if not grouped:
            return False
        existing_by_name = self._get_existing_categories_by_name(section_id)
        new_trees: list[dict] = []
        existing_merge: list[tuple[int, list[dict]]] = []
        for key, items in grouped.items():
            existing = existing_by_name.get(key)
            existing_id = existing.get("id") if isinstance(existing, dict) else None
            if isinstance(existing_id, int):
                existing_merge.append((existing_id, items))
                continue
            merged = self._merge_category_items(items)
            if merged:
                new_trees.append(merged)

        inserted = False
        if new_trees:
            created, link_ids = self._paste_category_trees_into_section(new_trees, section_id)
            if created:
                inserted = True
                if created_category_ids is not None:
                    created_category_ids.extend(
                        [int(c.get("id")) for c in created if isinstance(c.get("id"), int)]
                    )
            if link_ids and created_link_ids is not None:
                created_link_ids.extend([int(x) for x in link_ids if isinstance(x, int)])
        if existing_merge:
            link_ids = self._merge_links_into_existing_categories(existing_merge)
            if link_ids:
                inserted = True
                if created_link_ids is not None:
                    created_link_ids.extend([int(x) for x in link_ids if isinstance(x, int)])
        return inserted

    def _link_key_from_record(self, record: dict) -> tuple[str, str, str, str]:
        return (
            str(record.get("url") or ""),
            str(record.get("type") or ""),
            str(record.get("args") or ""),
            str(record.get("name") or ""),
        )

    def _prepare_link_payload(self, link: dict, category_id: int) -> dict | None:
        if not isinstance(link, dict):
            return None
        name = link.get("name") or ""
        url = link.get("url") or ""
        if not name or not url:
            return None
        payload = {
            "category_id": category_id,
            "name": name,
            "url": url,
            "type": link.get("type") or "web",
            "notes": link.get("notes") or "",
            "is_favorite": int(link.get("is_favorite") or 0),
            "icon_path": link.get("icon_path") or "default.ico",
            "args": link.get("args") or "",
        }
        browser_key = link.get("browser_key")
        if browser_key is not None:
            payload["browser_key"] = browser_key
        return payload

    def _merge_links_into_existing_categories(
        self, merges: list[tuple[int, list[dict]]]
    ) -> list[int]:
        all_links: list[dict] = []
        for cat_id, items in merges:
            try:
                existing_links = self.db.links.get_links(int(cat_id)) or []
            except Exception:
                logger.exception(
                    "Failed to load links for category %s while merging", cat_id
                )
                continue
            existing_keys: set[tuple[str, str, str, str]] = set()
            for link in existing_links:
                link_dict = dict(link) if not isinstance(link, dict) else link
                existing_keys.add(self._link_key_from_record(link_dict))

            for item in items:
                for link in (item or {}).get("links") or []:
                    payload = self._prepare_link_payload(link, int(cat_id))
                    if not payload:
                        continue
                    key = self._link_key_from_record(payload)
                    if key in existing_keys:
                        continue
                    existing_keys.add(key)
                    all_links.append(payload)

        if not all_links:
            return []
        return self._ls.batch_create_or_update_links(all_links)

    def paste_section_trees_to_sphere(
        self, trees: Iterable[dict], sphere_id: int
    ) -> dict[str, list[int]]:
        """Paste section trees into sphere. Returns ids of created/merged items."""
        created_section_ids: list[int] = []
        merged_section_ids: list[int] = []
        merged_category_ids: list[int] = []
        merged_link_ids: list[int] = []

        for tree in trees or []:
            section = dict((tree or {}).get("section") or {})
            name = section.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            existing = self._find_section_by_name(int(sphere_id), name)
            if existing and isinstance(existing.get("id"), int):
                existing_id = int(existing["id"])
                if existing_id not in merged_section_ids:
                    merged_section_ids.append(existing_id)
                self._merge_section_tree_into_section(
                    existing_id,
                    tree,
                    created_category_ids=merged_category_ids,
                    created_link_ids=merged_link_ids,
                )
                continue
            prepared = self._prepare_section_for_sphere(tree, sphere_id)
            if not prepared:
                continue
            try:
                sec_id = self.db.import_section_tree(prepared)
            except Exception:
                logger.exception(
                    "paste_section_trees_to_sphere: import_section_tree failed"
                )
                continue
            if isinstance(sec_id, int):
                created_section_ids.append(sec_id)

        return {
            "created_section_ids": created_section_ids,
            "merged_section_ids": merged_section_ids,
            "merged_category_ids": merged_category_ids,
            "merged_link_ids": merged_link_ids,
        }

    def _iter_links_for_created_categories(
        self,
        trees: Iterable[dict],
        index_by_name: dict[str, list[dict]],
        created_categories_out: list[dict],
    ) -> Iterable[dict]:
        """Generates link dictionaries for newly created categories.

        Matches created rows by category name and returns links with correct category_id.
        Fills created_categories_out with copies of created categories in processing order.
        """
        for tree in trees:
            src_cat = dict((tree or {}).get("category", {}))
            nm = src_cat.get("name")
            if not nm:
                continue
            if nm not in index_by_name or not index_by_name[nm]:
                continue
            cat_row = index_by_name[nm].pop(0)
            if not cat_row:
                continue
            yield from self._yield_links_for_tree(tree, cat_row, created_categories_out)

    def _iter_links_for_created_categories_by_uuid(
        self,
        bindings: Iterable[tuple[str, dict]],
        created_by_uuid: dict[str, dict],
        created_categories_out: list[dict],
    ) -> Iterable[dict]:
        """Generates links using client-side UUID bindings."""
        for token, tree in bindings:
            if not token:
                continue
            cat_row = created_by_uuid.get(token)
            if not cat_row:
                continue
            yield from self._yield_links_for_tree(tree, cat_row, created_categories_out)

    def _yield_links_for_tree(
        self,
        tree: dict,
        cat_row: dict,
        created_categories_out: list[dict],
    ) -> Iterable[dict]:
        """Yield link payloads for a single tree node and created category row."""
        cat_copy = dict(cat_row or {})
        if not cat_copy:
            return

        cat_id_obj: Any = cat_copy.get("id")
        if cat_id_obj is None:
            return
        if not isinstance(cat_id_obj, (int, str)):
            return
        try:
            new_cat_id = int(cat_id_obj)
        except (TypeError, ValueError):
            return
        created_categories_out.append(cat_copy)

        src_links = (tree or {}).get("links", []) or []
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
