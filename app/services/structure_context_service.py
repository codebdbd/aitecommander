"""Structure context menu business logic service.
Encapsulates copy/paste operations for categories via clipboard and DB interaction.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterable

from PyQt6.QtWidgets import QApplication

from app.models.entities.constants import CATEGORY_BULK_UUID_FIELD
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
        self._ss = StructureService(db)
        self._ls = LinksService(db)

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
            return json.loads(txt) if txt else None
        except (json.JSONDecodeError, RuntimeError, TypeError) as e:
            logger.warning(
                "Failed to get and parse JSON from clipboard: %s: %s",
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

    # --- Copy operations ---
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
    def _normalize_to_tree_list(self, payload: object) -> list[dict]:
        """Normalizes buffer data to list of category trees."""
        if isinstance(payload, dict):
            if {"category", "links"}.issubset(set(payload.keys())):
                return [payload]
            if payload.get("type") == "category_tree" and isinstance(
                payload.get("tree"), dict
            ):
                return [payload.get("tree")]  # type: ignore[return-value]
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
                        out.append(t)
                return out
            return []
        if isinstance(payload, list):
            return [
                t
                for t in payload
                if isinstance(t, dict) and {"category", "links"}.issubset(set(t.keys()))
            ]
        return []

    def paste_from_clipboard_to_section(self, section_id: int) -> list[dict]:
        """Pastes categories from clipboard to section. Returns list of created categories (dicts)."""
        try:
            data = self._clipboard_get_json()
            if not data:
                return []
            trees = self._normalize_to_tree_list(data)
            if not trees:
                return []

            # 1) Category preparation and batch creation
            batch_cats, bindings = self._prepare_categories_for_section(
                trees, section_id
            )
            if not batch_cats:
                return []

            created_list = self._ss.create_categories_bulk(batch_cats) or []
            if not created_list:
                return []

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
            if all_links:
                self._ls.batch_create_or_update_links(all_links)

            return created_categories
        except (ValueError, TypeError, KeyError, RuntimeError):
            logger.exception(
                "paste_from_clipboard_to_section(section_id=%s) failed", section_id
            )
            return []

    # --- Internal helpers ---
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
        try:
            new_cat_id = int(cat_copy.get("id"))
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
