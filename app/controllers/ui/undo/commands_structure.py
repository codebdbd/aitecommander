"""Undo commands for managing structure entities."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, QTimer

from app.controllers.business.structure_business import StructureBusinessLogic
from app.controllers.ui.dialogs import DialogManager
from app.controllers.ui.undo.base import BaseCommand, log_command
from app.controllers.ui.undo.stack import UndoManager
from app.core.results import ErrorNotification, InvalidateRegion, Result
from app.models.db import Database
from app.services.links_service import LinksService
from app.services.structure_context_service import StructureContextService
from app.services.structure_service import StructureService
from app.controllers.ui.state.task_scheduler import schedule_selection_restore
from app.utils.ui.icon.cache_manager import clear_icon_cache
from app.utils.ui.db_tasks import run_db

logger = logging.getLogger(__name__)

_UNDO_DIALOG_CONTEXT = "UndoCommands"
_UNDO_DELETE_CANCELED_TITLE = QT_TRANSLATE_NOOP(_UNDO_DIALOG_CONTEXT, "Delete canceled")
_UNDO_BACKUP_FAILED_MESSAGE = QT_TRANSLATE_NOOP(
    _UNDO_DIALOG_CONTEXT,
    "Backup failed. Delete canceled to keep undo available.",
)


def _tr_undo(text: str) -> str:
    return QCoreApplication.translate(_UNDO_DIALOG_CONTEXT, text)


def _resolve_database(main_window: Any) -> Database:
    dc = getattr(main_window, "database_controller", None)
    db_obj = getattr(dc, "db", None)
    if not isinstance(db_obj, Database):
        raise RuntimeError("Main window database is not available")
    return db_obj


def _cached_service(obj: Any, attr_name: str, factory: Callable[[], Any]) -> Any:
    """Lazily cache service instance on command object."""
    service = getattr(obj, attr_name, None)
    if service is None:
        service = factory()
        setattr(obj, attr_name, service)
    return service


def _fallback_structure_service(cmd: Any) -> StructureService:
    """Return cached fallback StructureService for a command instance."""
    return _cached_service(
        cmd,
        "_structure_service_cache",
        lambda: StructureService(cmd.db),
    )


def _new_structure_context_service(db: Database) -> StructureContextService:
    return StructureContextService(db)


def _new_structure_service(db: Database) -> StructureService:
    return StructureService(db)


def _new_links_service(db: Database) -> LinksService:
    return LinksService(db)


def _request_top_panels_refresh(main_window: Any) -> None:
    controller = getattr(main_window, "top_panels_controller", None)
    if controller is None:
        return
    try:
        if hasattr(controller, "refresh_favorites") and callable(
            controller.refresh_favorites
        ):
            controller.refresh_favorites()
            return
    except Exception:
        logger.debug(
            "commands_structure: refresh_favorites() failed for top panels",
            exc_info=True,
        )
    try:
        if hasattr(controller, "request_favorites_refresh") and callable(
            controller.request_favorites_refresh
        ):
            controller.request_favorites_refresh(0)
            return
    except Exception:
        logger.debug(
            "commands_structure: request_favorites_refresh() failed for top panels",
            exc_info=True,
        )
    try:
        if hasattr(controller, "request_refresh") and callable(controller.request_refresh):
            controller.request_refresh(0)
    except Exception:
        logger.debug(
            "commands_structure: request_refresh() failed for top panels",
            exc_info=True,
        )


def _invalidate_links_business_cache(main_window: Any) -> None:
    links_business = getattr(main_window, "links_business", None)
    if links_business is None:
        return
    try:
        if hasattr(links_business, "invalidate_cache") and callable(
            links_business.invalidate_cache
        ):
            links_business.invalidate_cache()
            return
    except Exception:
        logger.debug(
            "commands_structure: invalidate_cache() failed for links business",
            exc_info=True,
        )
    try:
        if hasattr(links_business, "_invalidate_cache") and callable(
            links_business._invalidate_cache
        ):
            links_business._invalidate_cache()
    except Exception:
        logger.debug(
            "commands_structure: _invalidate_cache() failed for links business",
            exc_info=True,
        )


class UndoResultSnapshot:
    """Stores payload and metadata captured from `Result` for undo replay."""

    def __init__(
        self,
        *,
        payload: dict[str, Any] | None,
        invalidate: tuple[InvalidateRegion, ...],
        notifications: tuple[ErrorNotification, ...],
    ) -> None:
        self.payload = payload
        self.invalidate = invalidate
        self.notifications = notifications


def _snapshot_from_result(
    result: Result[dict[str, Any] | None],
    *,
    payload: dict[str, Any] | None = None,
) -> UndoResultSnapshot:
    payload_to_store = payload if payload is not None else result.value
    return UndoResultSnapshot(
        payload=dict(payload_to_store) if isinstance(payload_to_store, dict) else None,
        invalidate=tuple(result.invalidate_regions),
        notifications=tuple(result.notifications),
    )


def _warm_category_icons_for_restore(
    categories_by_section: dict[int, list[dict[str, Any]]],
    *,
    max_icons: int | None = None,
) -> None:
    """Normalize category icon paths and warm cache for fast tiles/tree render."""
    if not categories_by_section:
        return
    try:
        from app.utils.ui.icon import resolve_category_icon_path
        from app.utils.ui.icon.icon_resolver import resolve_icon_path
        from app.utils.ui.icon.cache_manager import get_cached_category_icon
    except Exception:
        return

    warmed: set[str] = set()
    default_name: str | None = None
    warmed_count = 0
    limited_mode = isinstance(max_icons, int) and max_icons >= 0
    for categories in categories_by_section.values():
        if not isinstance(categories, list):
            continue
        for category in categories:
            if not isinstance(category, dict):
                continue
            icon_path = category.get("icon_path")
            if not isinstance(icon_path, str) or not icon_path.strip():
                icon_hint = category.get("icon")
                if isinstance(icon_hint, str) and icon_hint.strip():
                    icon_path = icon_hint
                    # Keep compatibility for tiles model that relies on icon_path
                    category["icon_path"] = icon_hint
            if not isinstance(icon_path, str) or not icon_path.strip():
                if default_name is None:
                    try:
                        default_resolved = resolve_category_icon_path("")
                        default_name = (
                            Path(default_resolved).name if default_resolved else ""
                        )
                    except Exception:
                        default_name = ""
                if default_name:
                    category["icon_path"] = default_name
                    icon_path = default_name
                else:
                    continue
            # For large restores we only prewarm a bounded number of icons.
            # Keep icon metadata filled for all rows, but avoid expensive
            # path resolution on the tail to prevent UI regressions.
            if limited_mode and warmed_count >= int(max_icons):
                continue
            resolved = resolve_category_icon_path(icon_path)
            if not resolved:
                continue
            if not limited_mode:
                needs_override = False
                try:
                    raw_trimmed = str(icon_path).strip()
                    if not raw_trimmed:
                        needs_override = True
                    else:
                        raw_path = Path(raw_trimmed)
                        if raw_path.is_absolute():
                            needs_override = not raw_path.exists()
                        else:
                            needs_override = not bool(resolve_icon_path(raw_trimmed))
                except Exception:
                    needs_override = True
                if needs_override:
                    category["icon_path"] = resolved
            if resolved in warmed:
                continue
            warmed.add(resolved)
            try:
                get_cached_category_icon(resolved)
                warmed_count += 1
            except Exception:
                pass


def _undo_icon_warm_limit_default() -> int:
    """Bounded default for synchronous icon warmup during large undo restore."""
    try:
        raw = os.getenv("AITE_UNDO_ICON_WARM_LIMIT", "0").strip()
        value = int(raw or "0")
    except Exception:
        value = 0
    # Keep warmup bounded to avoid blocking UI phase.
    return max(0, min(24, value))


def _update_cache_after_restore(
    business: StructureBusinessLogic,
    categories_by_section: dict[int, list[dict[str, Any]]],
    restored_sections: list[dict[str, Any]] | None = None,
) -> None:
    cache = getattr(business, "cache_manager", None)
    if cache is None and not categories_by_section and not restored_sections:
        return

    if cache is None:
        return

    for section_id, categories in categories_by_section.items():
        try:
            cache.set(f"categories_{section_id}", categories)
        except Exception:
            logger.debug(
                "_update_cache_after_restore: cache set failed for section %s",
                section_id,
                exc_info=True,
            )
    if restored_sections:
        sections_by_sphere: dict[int, list[dict[str, Any]]] = {}
        for payload in restored_sections:
            sphere_id = payload.get("sphere_id")
            if isinstance(sphere_id, int):
                sections_by_sphere.setdefault(sphere_id, []).append(payload)

        for sphere_id, sections in sections_by_sphere.items():
            key = f"sections_{sphere_id}"
            current = cache.get(key)
            updated: list[dict[str, Any]]
            if isinstance(current, list):
                restored_ids = {
                    int(p.get("id"))
                    for p in sections
                    if isinstance(p.get("id"), int)
                }
                updated = [
                    dict(s)
                    for s in current
                    if isinstance(s, dict) and s.get("id") not in restored_ids
                ]
            else:
                updated = []

            for payload in sections:
                section_stub = dict(payload)
                section_stub.pop("categories", None)
                updated.append(section_stub)

            try:
                updated.sort(
                    key=lambda s: (
                        int(s.get("position"))
                        if isinstance(s.get("position"), int)
                        else 0,
                        str(s.get("name", "")).lower(),
                    )
                )
            except Exception:
                pass

            try:
                cache.set(key, updated)
            except Exception:
                logger.debug(
                    "_update_cache_after_restore: sections cache set failed for sphere %s",
                    sphere_id,
                    exc_info=True,
                )

            structure_key = f"structure_{sphere_id}"
            current_structure = cache.get(structure_key)
            struct_map: dict[int, dict[str, Any]] = {}
            if isinstance(current_structure, list):
                for item in current_structure:
                    if isinstance(item, dict):
                        sid = item.get("id")
                        if isinstance(sid, int):
                            struct_map[int(sid)] = dict(item)

            for section_id, categories in categories_by_section.items():
                if section_id in struct_map:
                    struct_map[section_id]["categories"] = categories

            for payload in sections:
                sid = payload.get("id")
                if isinstance(sid, int) and sid not in struct_map:
                    stub = dict(payload)
                    stub["categories"] = categories_by_section.get(int(sid), [])
                    struct_map[int(sid)] = stub

            struct_updated = list(struct_map.values())
            try:
                struct_updated.sort(
                    key=lambda s: (
                        int(s.get("position"))
                        if isinstance(s.get("position"), int)
                        else 0,
                        str(s.get("name", "")).lower(),
                    )
                )
            except Exception:
                pass

            try:
                cache.set(structure_key, struct_updated)
            except Exception:
                logger.debug(
                    "_update_cache_after_restore: structure cache set failed for sphere %s",
                    sphere_id,
                    exc_info=True,
                )

            try:
                cache.invalidate_first_category_cache_for_sphere(int(sphere_id))
            except Exception:
                pass
        return

    try:
        cache.invalidate_first_category_cache()
    except Exception:
        pass


def _apply_restored_categories_update(
    *,
    business: StructureBusinessLogic,
    tree_manager: Any | None,
    categories_by_section: dict[int, list[dict[str, Any]]],
    restored_sections: list[dict[str, Any]] | None = None,
    context: str = "restore",
    warm_icon_limit: int | None = None,
    refresh_tiles: bool = True,
    track_restored_spheres: bool = True,
) -> None:
    def _resolve_section_for_tiles() -> int | None:
        if not categories_by_section:
            return None
        if tree_manager is not None:
            try:
                from app.utils.ui.qt.roles import get_tree_tuple

                current = tree_manager.tree.currentIndex()
                if current and current.isValid():
                    meta = get_tree_tuple(current, 0)
                    if (
                        isinstance(meta, (tuple, list))
                        and len(meta) == 2
                        and meta[0] == "section"
                        and isinstance(meta[1], int)
                        and meta[1] in categories_by_section
                    ):
                        return int(meta[1])
                    if (
                        isinstance(meta, (tuple, list))
                        and len(meta) == 2
                        and meta[0] == "category"
                    ):
                        parent = current.parent()
                        if parent and parent.isValid():
                            parent_meta = get_tree_tuple(parent, 0)
                            if (
                                isinstance(parent_meta, (tuple, list))
                                and len(parent_meta) == 2
                                and parent_meta[0] == "section"
                                and isinstance(parent_meta[1], int)
                                and parent_meta[1] in categories_by_section
                            ):
                                return int(parent_meta[1])
            except Exception:
                logger.debug(
                    "%s: resolve tiles section failed", context, exc_info=True
                )

        if restored_sections:
            for payload in restored_sections:
                sid = payload.get("id")
                if isinstance(sid, int) and sid in categories_by_section:
                    return int(sid)

        for sid in categories_by_section:
            if isinstance(sid, int):
                return int(sid)
        return None

    def _is_tiles_view() -> bool:
        if tree_manager is None:
            return False
        try:
            controller = getattr(tree_manager, "controller", None)
            main = getattr(controller, "main", None)
            stack = getattr(main, "stack", None)
            if stack is None or not hasattr(stack, "currentIndex"):
                return False
            from app.config_data.runtime_config import get_tiles_stack_index

            tiles_index = get_tiles_stack_index()
            return stack.currentIndex() == tiles_index
        except Exception:
            logger.debug("%s: tiles view check failed", context, exc_info=True)
            return False

    def _refresh_tiles_after_restore() -> bool:
        if tree_manager is None:
            return False
        tiles_controller = getattr(tree_manager, "tiles_controller", None)
        if tiles_controller is None or not hasattr(tiles_controller, "refresh"):
            return False
        section_id = _resolve_section_for_tiles()
        if section_id is None:
            return False
        switch_view = _is_tiles_view()
        try:
            tiles_controller.refresh(int(section_id), switch_view=switch_view)
            return True
        except Exception:
            logger.debug(
                "%s: tiles refresh failed for section %s",
                context,
                section_id,
                exc_info=True,
            )
            return False

    did_apply_updates = False
    if categories_by_section:
        _warm_category_icons_for_restore(categories_by_section, max_icons=warm_icon_limit)
    if tree_manager is not None and categories_by_section:
        for section_id, categories in categories_by_section.items():
            try:
                tree_manager.replace_section_categories(section_id, categories)
            except Exception:
                logger.debug(
                    "%s: replace_section_categories failed for section %s",
                    context,
                    section_id,
                    exc_info=True,
                )
        did_apply_updates = True

    _update_cache_after_restore(
        business,
        categories_by_section,
        restored_sections=restored_sections,
    )
    if getattr(business, "cache_manager", None) is not None:
        did_apply_updates = True

    if refresh_tiles:
        _refresh_tiles_after_restore()
    event_service = getattr(business, "event_service", None)
    if event_service is not None:
        if categories_by_section:
            for section_id in categories_by_section:
                try:
                    event_service.add_batch_section(int(section_id))
                except Exception:
                    logger.debug(
                        "%s: add_batch_section failed for %s",
                        context,
                        section_id,
                        exc_info=True,
                    )
        if restored_sections:
            for payload in restored_sections:
                try:
                    section_id = payload.get("id")
                    sphere_id = payload.get("sphere_id")
                    if isinstance(section_id, int):
                        event_service.add_batch_section(section_id)
                    if track_restored_spheres and isinstance(sphere_id, int):
                        event_service.add_batch_sphere(sphere_id)
                except Exception:
                    logger.debug(
                        "%s: add_batch_sphere failed",
                        context,
                        exc_info=True,
                    )


def _prime_restored_section_categories_deferred(
    tree_manager: Any | None,
    categories_by_section: dict[int, list[dict[str, Any]]],
    *,
    context: str,
) -> None:
    """Attach restored categories to freshly inserted section nodes without full materialization."""
    if tree_manager is None or not categories_by_section:
        return
    model = getattr(tree_manager, "model", None)
    if model is None:
        return

    deferred_store = getattr(model, "_deferred_categories_by_section", None)
    deferred_parent_map = getattr(model, "_deferred_category_parent_by_id", None)
    section_map = getattr(model, "_section_by_id", None)
    if not isinstance(deferred_store, dict) or not isinstance(section_map, dict):
        return

    for raw_section_id, categories in categories_by_section.items():
        try:
            section_id = int(raw_section_id)
        except Exception:
            continue
        sec_node = section_map.get(section_id)
        if sec_node is None:
            continue

        prepared = [dict(item) for item in (categories or []) if isinstance(item, dict)]
        if prepared:
            deferred_store[section_id] = prepared
            try:
                setattr(sec_node, "children_populated", False)
            except Exception:
                logger.debug(
                    "%s: failed to mark section %s as deferred",
                    context,
                    section_id,
                    exc_info=True,
                )
            if isinstance(deferred_parent_map, dict):
                for payload in prepared:
                    category_id = payload.get("id")
                    if isinstance(category_id, int):
                        deferred_parent_map[int(category_id)] = section_id
        else:
            deferred_store.pop(section_id, None)
            try:
                setattr(sec_node, "children_populated", True)
            except Exception:
                logger.debug(
                    "%s: failed to mark empty section %s as populated",
                    context,
                    section_id,
                    exc_info=True,
                )


def _split_section_trees_for_deferred_links(
    trees: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[int]]:
    """Detach links from section backup trees so they can be restored later."""
    stripped_trees: list[dict[str, Any]] = []
    deferred_links: list[dict[str, Any]] = []
    affected_category_ids: set[int] = set()

    for tree in trees or []:
        if not isinstance(tree, dict):
            continue
        section_payload = dict(tree.get("section") or {})
        if not section_payload:
            continue
        stripped_categories: list[dict[str, Any]] = []
        for item in tree.get("categories") or []:
            if not isinstance(item, dict):
                continue
            category_payload = dict((item or {}).get("category") or {})
            if not category_payload:
                continue
            category_id = category_payload.get("id")
            if isinstance(category_id, int) and category_id > 0:
                affected_category_ids.add(int(category_id))
                for link in (item or {}).get("links") or []:
                    if not isinstance(link, dict):
                        continue
                    link_payload = dict(link)
                    link_payload["category_id"] = int(category_id)
                    deferred_links.append(link_payload)
            stripped_categories.append(
                {
                    "category": category_payload,
                    "links": [],
                }
            )
        stripped_trees.append(
            {
                "section": section_payload,
                "categories": stripped_categories,
            }
        )

    return stripped_trees, deferred_links, affected_category_ids


class SaveSectionCmd(BaseCommand):
    """Save (create/edit) section.
    Thin wrapper over DB with business-layer signal emission for UI.
    """

    def __init__(
        self,
        new_data: dict,
        old_data: dict | None,
        main_window,
        *,
        business: StructureBusinessLogic | None = None,
        undo_manager: UndoManager | None = None,
    ) -> None:
        super().__init__("Save section", main_window)
        self.main = main_window
        self._business = business
        self._undo_manager = undo_manager
        if business is not None:
            self.structure_service = business.structure_service
        else:
            self.db: Database = _resolve_database(main_window)
            self.structure_service = _fallback_structure_service(self)
        self.new_data = dict(new_data) if new_data else {}
        self.old_data = dict(old_data) if old_data else None
        self.is_new = not bool(self.new_data.get("id"))
        self.new_id = self.new_data.get("id")
        self._last_snapshot: UndoResultSnapshot | None = None

    def _store_snapshot(self, snapshot: UndoResultSnapshot | None) -> None:
        self._last_snapshot = snapshot

    def _resolve_business(self) -> StructureBusinessLogic | None:
        return self._business or getattr(self.main, "structure_business", None)

    def _dispatch_result(
        self,
        result: Result[dict[str, Any] | None],
        *,
        description: str,
        on_success: Callable[[dict[str, Any] | None], None] | None = None,
    ) -> None:
        def _fallback_success(payload: dict[str, Any] | None) -> None:
            if on_success:
                on_success(payload)

        def _fallback_error(exc: Exception) -> None:
            logger.warning("%s failed: %s", description, exc)

        if self._undo_manager is None:
            if result.is_success():
                _fallback_success(result.value)
            elif result.error:
                _fallback_error(result.error)
            return

        self._undo_manager.dispatch_result(
            result,
            on_success=_fallback_success if on_success else None,
            on_error=_fallback_error,
            description=description,
        )

    def _emit_reload(self, payload: dict[str, Any] | None) -> None:
        business = self._resolve_business()
        if business is None:
            return
        try:
            if self.is_new:
                business.item_added.emit("section", self.new_id, payload or self.new_data)
            else:
                business.item_updated.emit("section", self.new_id, payload or self.new_data)
        except Exception as exc:
            logger.warning(
                "SaveSectionCmd._emit_reload: failed to emit update signals: %s",
                exc,
                exc_info=True,
            )

    def _target_sphere_changed(self, payload: dict[str, Any] | None = None) -> bool:
        if self.is_new or not isinstance(self.old_data, dict):
            return False
        data = payload if isinstance(payload, dict) else self.new_data
        old_sphere_id = self.old_data.get("sphere_id")
        new_sphere_id = data.get("sphere_id")
        return (
            isinstance(old_sphere_id, int)
            and isinstance(new_sphere_id, int)
            and old_sphere_id != new_sphere_id
        )

    def _fill_missing_update_fields(self) -> None:
        if self.is_new or not isinstance(self.old_data, dict):
            return
        for key in ("name", "sphere_id", "position"):
            if key not in self.new_data and key in self.old_data:
                self.new_data[key] = self.old_data[key]

    def _schedule_focus_after_sphere_switch(
        self,
        section_id: int,
        *,
        after_structure_loaded: bool = False,
    ) -> None:
        structure = getattr(self.main, "structure", None)
        selection_handler = getattr(structure, "selection_handler", None)
        restore = getattr(selection_handler, "_restore_selection_after_load", None)
        if not callable(restore):
            return
        try:
            schedule_selection_restore(
                lambda: restore("section", section_id),
                f"section_move_sphere_{section_id}",
                delay=0 if after_structure_loaded else None,
            )
        except Exception:
            logger.debug(
                "SaveSectionCmd: failed to schedule moved section focus",
                exc_info=True,
            )

    def _schedule_focus_when_structure_loaded(self, section_id: int) -> bool:
        business = self._resolve_business()
        signal = getattr(business, "structure_loaded", None)
        if not hasattr(signal, "connect"):
            return False

        def _on_loaded(*_args: Any) -> None:
            try:
                if hasattr(signal, "disconnect"):
                    signal.disconnect(_on_loaded)
            except Exception:
                logger.debug(
                    "SaveSectionCmd: failed to disconnect structure_loaded focus hook",
                    exc_info=True,
                )
            self._schedule_focus_after_sphere_switch(
                section_id,
                after_structure_loaded=True,
            )

        try:
            signal.connect(_on_loaded)
            return True
        except Exception:
            logger.debug(
                "SaveSectionCmd: failed to connect structure_loaded focus hook",
                exc_info=True,
            )
            return False

    def _switch_to_target_sphere_and_focus(
        self,
        section_id: int,
        sphere_id: int,
    ) -> bool:
        structure = getattr(self.main, "structure", None)
        switch_sphere = getattr(structure, "switch_sphere", None)
        if not callable(switch_sphere):
            return False
        try:
            connected_focus_hook = self._schedule_focus_when_structure_loaded(section_id)
            switch_sphere(int(sphere_id))
            if not connected_focus_hook:
                self._schedule_focus_after_sphere_switch(section_id)
            return True
        except Exception:
            logger.debug(
                "SaveSectionCmd: failed to switch to target sphere %s",
                sphere_id,
                exc_info=True,
            )
            return False

    @log_command
    def redo(self) -> None:
        try:
            if getattr(self.main, "_suppress_deletes", False):
                logger.debug(
                    "[DeleteGuard] SaveSectionCmd.redo suppressed by _suppress_deletes flag"
                )
                return
        except Exception as exc:
            logger.debug("SaveSectionCmd.redo: delete guard check failed: %s", exc)

        if self.is_new:
            result = self.structure_service.create_section(self.new_data)
        else:
            self._fill_missing_update_fields()
            section_id = self.new_id if isinstance(self.new_id, int) else self.new_data.get("id")
            result = self.structure_service.update_section(int(section_id), self.new_data)

        def _on_success(payload: dict[str, Any] | None) -> None:
            was_new = self.is_new
            if isinstance(payload, dict):
                self.new_data = dict(payload)
            new_id = self.new_data.get("id")
            if isinstance(new_id, int):
                self.new_id = new_id
            business = self._resolve_business()
            if business is not None and isinstance(self.new_id, int) and not was_new:
                data = payload if isinstance(payload, dict) else self.new_data
                target_sphere_id = data.get("sphere_id")
                moved_to_other_sphere = self._target_sphere_changed(payload)
                switched = False
                if moved_to_other_sphere and isinstance(target_sphere_id, int):
                    switched = self._switch_to_target_sphere_and_focus(
                        int(self.new_id),
                        int(target_sphere_id),
                    )
                if not switched:
                    try:
                        business.section_selected.emit(self.new_id)
                    except Exception as exc:
                        logger.warning("SaveSectionCmd.redo: section_selected failed: %s", exc)
            if not self._target_sphere_changed(payload):
                self._emit_reload(payload)
            self.is_new = False
            self._store_snapshot(
                _snapshot_from_result(result, payload=payload or self.new_data)
            )

        self._dispatch_result(
            result,
            description="save-section-redo" if not self.is_new else "create-section-redo",
            on_success=_on_success,
        )

    @log_command
    def undo(self) -> None:
        if self.is_new:
            result = self.structure_service.delete_section(int(self.new_id))

            def _on_delete_success(payload: dict[str, Any] | None) -> None:
                business = self._resolve_business()
                if business is not None and isinstance(self.new_id, int):
                    try:
                        business.item_deleted.emit("section", int(self.new_id))
                    except Exception as exc:
                        logger.warning(
                            "SaveSectionCmd.undo: item_deleted emit failed: %s",
                            exc,
                        )
                self._store_snapshot(
                    _snapshot_from_result(result, payload=result.value)
                )

            self._dispatch_result(
                result,
                description="save-section-undo-delete",
                on_success=_on_delete_success,
            )
            return

        if not self.old_data:
            return

        result = self.structure_service.update_section(
            int(self.old_data["id"]), self.old_data
        )
        previous_data = dict(self.new_data) if isinstance(self.new_data, dict) else {}

        def _on_restore_success(payload: dict[str, Any] | None) -> None:
            restored = dict(payload) if isinstance(payload, dict) else dict(self.old_data)
            self.new_data = restored
            self.new_id = restored.get("id", self.new_id)
            business = self._resolve_business()
            switched = False
            if business is not None:
                previous_sphere_id = previous_data.get("sphere_id")
                target_sphere_id = restored.get("sphere_id")
                if (
                    isinstance(previous_sphere_id, int)
                    and isinstance(target_sphere_id, int)
                    and previous_sphere_id != target_sphere_id
                    and isinstance(restored.get("id"), int)
                ):
                    switched = self._switch_to_target_sphere_and_focus(
                        int(restored["id"]),
                        int(target_sphere_id),
                    )
                if not switched:
                    try:
                        business.section_selected.emit(int(restored["id"]))
                    except Exception as exc:
                        logger.warning(
                            "SaveSectionCmd.undo: select_section failed: %s",
                            exc,
                        )
            if not switched:
                self._emit_reload(restored)
            self._store_snapshot(
                _snapshot_from_result(result, payload=restored)
            )

        self._dispatch_result(
            result,
            description="save-section-undo-update",
            on_success=_on_restore_success,
        )


class DeleteSectionCmd(BaseCommand):
    """Delete structure section with optional lightweight reloading."""

    def __init__(
        self,
        section_data: dict[str, Any] | None,
        main_window,
        *,
        business: StructureBusinessLogic | None = None,
        undo_manager: UndoManager | None = None,
    ) -> None:
        super().__init__("Delete section", main_window)
        self.main = main_window
        self._business = business
        self._undo_manager = undo_manager
        if business is not None:
            self.structure_service = business.structure_service
        else:
            self.db: Database = _resolve_database(main_window)
            self.structure_service = _fallback_structure_service(self)
        self.section = dict(section_data) if section_data else {}
        self._backup_tree: dict[str, Any] | None = None
        self._backup_failed = False
        self._last_snapshot: UndoResultSnapshot | None = None
        section_id_obj = self.section.get("id")
        if isinstance(section_id_obj, int):
            try:
                self._backup_tree = self.structure_service.export_section_tree(
                    section_id_obj
                )
            except Exception as exc:
                self._backup_failed = True
                logger.warning(
                    "DeleteSectionCmd.__init__: unable to export section tree: %s",
                    exc,
                )

    def _store_snapshot(self, snapshot: UndoResultSnapshot | None) -> None:
        self._last_snapshot = snapshot

    def _resolve_business(self) -> StructureBusinessLogic | None:
        return self._business or getattr(self.main, "structure_business", None)

    def _dispatch_result(
        self,
        result: Result[dict[str, Any] | None],
        *,
        description: str,
        on_success: Callable[[dict[str, Any] | None], None] | None = None,
    ) -> None:
        def _fallback_success(payload: dict[str, Any] | None) -> None:
            if on_success:
                on_success(payload)

        def _fallback_error(exc: Exception) -> None:
            logger.warning("%s failed: %s", description, exc)

        if self._undo_manager is None:
            if result.is_success():
                _fallback_success(result.value)
            elif result.error:
                _fallback_error(result.error)
            return

        self._undo_manager.dispatch_result(
            result,
            on_success=_fallback_success if on_success else None,
            on_error=_fallback_error,
            description=description,
        )

    def _warn_backup_failed(self) -> None:
        try:
            DialogManager.show_error(
                self.main,
                _tr_undo(_UNDO_BACKUP_FAILED_MESSAGE),
                _tr_undo(_UNDO_DELETE_CANCELED_TITLE),
            )
        except Exception:
            pass


    def _restore_section_from_backup(self) -> tuple[dict[str, Any], int] | None:
        """Import the section backup and return payload with identifier."""

        try:
            self.structure_service.import_section_tree(self._backup_tree)
        except Exception as exc:
            logger.exception("DeleteSectionCmd.undo: restore failed: %s", exc)
            return None
        source = self._backup_tree or {}
        section_payload = dict(source.get("section") or {})
        section_id = section_payload.get("id")
        if not isinstance(section_id, int):
            return None
        return section_payload, section_id

    def _select_first_category_after_restore(self) -> None:
        """Select the first restored category when available."""

        try:
            source = self._backup_tree or {}
            categories = source.get("categories") or []
            for item in categories:
                category_payload = (item or {}).get("category") or {}
                category_id = category_payload.get("id")
                if isinstance(category_id, int):
                    business = self._resolve_business()
                    if business:
                        business.select_category(category_id)
                    break
        except Exception as exc:
            logger.warning(
                "DeleteSectionCmd.undo: categories handling failed: %s", exc
            )

    def _emit_section_restore_signals(
        self, section_id: int, section_payload: dict[str, Any]
    ) -> None:
        """Emit UI signals after restoring a section."""

        business = self._resolve_business()
        if not business:
            return
        try:
            business.section_selected.emit(section_id)
        except Exception as exc:
            logger.warning("DeleteSectionCmd.undo: select_section failed: %s", exc)
        sphere_id = section_payload.get("sphere_id")
        parent_id = int(sphere_id) if isinstance(sphere_id, int) else section_id
        try:
            business.item_added.emit("section", parent_id, section_payload)
        except Exception as exc:
            logger.debug(
                "DeleteSectionCmd.undo: item_added emit failed: %s",
                exc,
                exc_info=True,
            )

    def _restore_section_categories_in_tree(self, section_id: int) -> None:
        """Restore section children in tree model from backup payload."""

        structure_ctrl = getattr(self.main, "structure", None)
        tree_manager = getattr(structure_ctrl, "tree_manager", None)
        if tree_manager is None or not hasattr(tree_manager, "replace_section_categories"):
            return

        source = self._backup_tree or {}
        raw_categories = source.get("categories") or []
        restored_categories: list[dict[str, Any]] = []
        for item in raw_categories:
            payload = dict((item or {}).get("category") or {})
            if not payload:
                continue
            payload["__from_undo__"] = True
            payload["__skip_focus__"] = True
            if not isinstance(payload.get("section_id"), int):
                payload["section_id"] = int(section_id)
            restored_categories.append(payload)
        if not restored_categories:
            return
        try:
            tree_manager.replace_section_categories(int(section_id), restored_categories)
        except Exception:
            logger.debug(
                "DeleteSectionCmd.undo: replace_section_categories failed for section %s",
                section_id,
                exc_info=True,
            )

    def redo(self) -> None:
        if self._backup_failed or not self._backup_tree:
            logger.warning("DeleteSectionCmd.redo: backup missing; delete canceled")
            self.set_obsolete(True)
            self._warn_backup_failed()
            return
        section_id_obj = self.section.get("id")
        if not isinstance(section_id_obj, int):
            return
        section_id = section_id_obj
        categories_deleted = len((self._backup_tree or {}).get("categories") or [])

        result = self.structure_service.delete_section(section_id)

        def _on_success(payload: dict[str, Any] | None) -> None:
            business = self._resolve_business()
            if business is not None:
                try:
                    business.item_deleted.emit("section", section_id)
                except Exception as exc:
                    logger.debug(
                        "DeleteSectionCmd.redo: item_deleted emit failed: %s",
                        exc,
                        exc_info=True,
                    )
            payload = result.value or {}
            payload = dict(payload) if isinstance(payload, dict) else {}
            payload.setdefault("categories_deleted", categories_deleted)
            payload.setdefault("links_deleted", 0)
            self._store_snapshot(_snapshot_from_result(result, payload=payload))

        self._dispatch_result(
            result,
            description="delete-section-redo",
            on_success=_on_success,
        )

    def undo(self) -> None:
        if not self._backup_tree:
            logger.warning("DeleteSectionCmd.undo: backup missing; undo skipped")
            return
        restored = self._restore_section_from_backup()
        if restored is None:
            return
        section_payload, section_id = restored
        self._emit_section_restore_signals(section_id, section_payload)
        self._restore_section_categories_in_tree(section_id)
        self._select_first_category_after_restore()
        self._store_snapshot(_snapshot_from_result(Result.success(section_payload)))


class BatchDeleteCategoriesCmd(BaseCommand):
    """Batch delete categories with bulk storage operations and undo support."""

    def __init__(
        self,
        categories_to_delete: list[dict[str, Any]] | None,
        main_window,
        *,
        business: StructureBusinessLogic | None = None,
        undo_manager: UndoManager | None = None,
    ) -> None:
        super().__init__("Batch delete categories", main_window)
        self.main = main_window
        self._business = business
        self._undo_manager = undo_manager
        if business is not None:
            self.structure_service = business.structure_service
        else:
            self.db: Database = _resolve_database(main_window)
            self.structure_service = _fallback_structure_service(self)

        self.categories = [dict(x) for x in (categories_to_delete or [])]
        self._category_ids: list[int] = []
        self._backup_trees: list[dict[str, Any]] = []
        self._backup_failed = False
        self._touched_sections: set[int] = set()

        for payload in self.categories:
            cid = payload.get("id")
            if isinstance(cid, int):
                self._category_ids.append(cid)
                section_id = payload.get("section_id")
                if isinstance(section_id, int):
                    self._touched_sections.add(int(section_id))
                try:
                    tree = self.structure_service.export_category_tree(cid)
                except Exception as exc:
                    self._backup_failed = True
                    logger.warning(
                        "BatchDeleteCategoriesCmd.__init__: export_category_tree failed for %s: %s",
                        cid,
                        exc,
                    )
                else:
                    if tree:
                        self._backup_trees.append(tree)

    def _resolve_business(self) -> StructureBusinessLogic | None:
        return self._business or getattr(self.main, "structure_business", None)

    def _dispatch_result(
        self,
        result: Result[Any],
        *,
        description: str,
        on_success: Callable[[Any], None] | None = None,
    ) -> None:
        def _fallback_success(payload: Any) -> None:
            if on_success:
                on_success(payload)

        def _fallback_error(exc: Exception) -> None:
            logger.warning("%s failed: %s", description, exc)

        if self._undo_manager is None:
            if result.is_success():
                _fallback_success(result.value)
            elif result.error:
                _fallback_error(result.error)
            return

        self._undo_manager.dispatch_result(
            result,
            on_success=_fallback_success if on_success else None,
            on_error=_fallback_error,
            description=description,
        )

    def _warn_backup_failed(self) -> None:
        try:
            DialogManager.show_error(
                self.main,
                _tr_undo(_UNDO_BACKUP_FAILED_MESSAGE),
                _tr_undo(_UNDO_DELETE_CANCELED_TITLE),
            )
        except Exception:
            pass

    @log_command
    def redo(self) -> None:
        if self._backup_failed or not self._backup_trees:
            logger.warning(
                "BatchDeleteCategoriesCmd.redo: backup missing; delete canceled"
            )
            self.set_obsolete(True)
            self._warn_backup_failed()
            return
        if not self._category_ids:
            return

        logger.info(
            "BatchDeleteCategoriesCmd.redo: deleting categories count=%s",
            len(self._category_ids),
        )
        result = self.structure_service.delete_categories_bulk(self._category_ids)

        def _on_success(_: dict[str, Any] | None) -> None:
            business = self._resolve_business()
            if business is not None:
                for section_id in self._touched_sections:
                    try:
                        business._invalidate_categories_cache(section_id)
                    except Exception:
                        logger.debug(
                            "BatchDeleteCategoriesCmd.redo: cache invalidation failed for section %s",
                            section_id,
                            exc_info=True,
                        )
                try:
                    business.items_batch_deleted.emit(
                        "category", list(self._category_ids)
                    )
                except Exception as exc:
                    logger.debug(
                        "BatchDeleteCategoriesCmd.redo: items_batch_deleted emit failed: %s",
                        exc,
                        exc_info=True,
                    )

        self._dispatch_result(
            result,
            description="batch-delete-categories-redo",
            on_success=_on_success,
        )

    @log_command
    def undo(self) -> None:
        if not self._backup_trees:
            logger.warning("BatchDeleteCategoriesCmd.undo: backup missing; undo skipped")
            return
        selection_handler = None
        tree_manager = None
        try:
            structure_ctrl = getattr(self.main, "structure", None)
            selection_handler = getattr(structure_ctrl, "selection_handler", None)
            tree_manager = getattr(structure_ctrl, "tree_manager", None)
        except Exception:
            selection_handler = None
            tree_manager = None
        started = time.perf_counter()
        total = len(self._backup_trees)
        logger.info(
            "BatchDeleteCategoriesCmd.undo: restoring categories count=%s",
            total,
        )
        try:
            large_batch_threshold = 20
        except Exception:
            large_batch_threshold = 20
        business_for_preload = self._resolve_business()
        if business_for_preload is not None and total >= large_batch_threshold:
            try:
                business_for_preload.suspend_structure_preload(
                    duration_ms=3000,
                    reason="batch-delete-categories-undo",
                )
            except Exception:
                logger.debug(
                    "BatchDeleteCategoriesCmd.undo: failed to suspend structure preload",
                    exc_info=True,
                )

        def _restore_task() -> int:
            self.structure_service.import_category_trees_bulk(self._backup_trees)
            return total

        def _after_restore(_restored_count: int) -> None:
            after_db_ts = time.perf_counter()
            elapsed_ms = (after_db_ts - started) * 1000.0
            logger.info(
                "BatchDeleteCategoriesCmd.undo: restore completed in %.2f ms (count=%s)",
                elapsed_ms,
                _restored_count,
            )
            ui_phase_started = time.perf_counter()
            business = self._resolve_business()
            restored_payloads: list[dict[str, Any]] = []
            categories_by_section: dict[int, list[dict[str, Any]]] = {}
            for tree in self._backup_trees:
                payload = dict(tree.get("category") or {})
                if not payload:
                    continue
                payload["__from_undo__"] = True
                payload["__skip_focus__"] = True
                restored_payloads.append(payload)
                section_id = payload.get("section_id")
                if isinstance(section_id, int):
                    categories_by_section.setdefault(section_id, []).append(payload)

            if business is not None:
                first_id = restored_payloads[0].get("id") if restored_payloads else None
                first_section_id = (
                    restored_payloads[0].get("section_id") if restored_payloads else None
                )
            else:
                first_id = None
                first_section_id = None

            restore_update_ms = 0.0
            end_batch_ms = 0.0
            focus_restore_ms = 0.0
            if business is not None:
                if selection_handler is not None:
                    selection_handler.begin_suppress_selection()
                business.begin_batch()
                try:
                    if (
                        total >= large_batch_threshold
                        and tree_manager is not None
                        and hasattr(tree_manager, "request_next_snapshot_mode")
                    ):
                        try:
                            tree_manager.request_next_snapshot_mode("full_restore")
                        except Exception:
                            logger.debug(
                                "BatchDeleteCategoriesCmd.undo: failed to request full_restore snapshot mode",
                                exc_info=True,
                            )
                    if categories_by_section:
                        if total >= large_batch_threshold:
                            try:
                                restore_update_started = time.perf_counter()
                                # Large restore fast-path:
                                # 1) prime touched section caches with already-restored payload,
                                # 2) mark touched sections in batch event service,
                                # 3) let end_batch skip redundant async reloads for primed sections.
                                for section_id in categories_by_section:
                                    try:
                                        primed_categories = sorted(
                                            [
                                                dict(item)
                                                for item in categories_by_section.get(
                                                    int(section_id), []
                                                )
                                                if isinstance(item, dict)
                                            ],
                                            key=lambda item: (
                                                int(item.get("position", 0))
                                                if isinstance(
                                                    item.get("position", 0), int
                                                )
                                                else 0
                                            ),
                                        )
                                        business.prime_categories_cache(
                                            int(section_id),
                                            primed_categories,
                                            ttl_s=2.0,
                                        )
                                    except Exception:
                                        logger.debug(
                                            "BatchDeleteCategoriesCmd.undo: cache prime failed for section %s",
                                            section_id,
                                            exc_info=True,
                                        )
                                event_service = getattr(business, "event_service", None)
                                if event_service is not None:
                                    for section_id in categories_by_section:
                                        try:
                                            event_service.add_batch_section(int(section_id))
                                        except Exception:
                                            logger.debug(
                                                "BatchDeleteCategoriesCmd.undo: add_batch_section failed for %s",
                                                section_id,
                                                exc_info=True,
                                            )
                                # Keep tree model consistent immediately after DB restore.
                                # `load_categories_async` in end_batch updates tiles/data flow,
                                # but does not guarantee section children rebuild in tree model.
                                if tree_manager is not None:
                                    try:
                                        # Warm a limited icon set for the primary restored section
                                        # to avoid "text first, icons later" visual regression.
                                        primary_sid = (
                                            int(first_section_id)
                                            if isinstance(first_section_id, int)
                                            and int(first_section_id) in categories_by_section
                                            else next(iter(categories_by_section.keys()), None)
                                        )
                                        warm_limit = _undo_icon_warm_limit_default()
                                        if isinstance(primary_sid, int):
                                            _warm_category_icons_for_restore(
                                                {
                                                    int(primary_sid): list(
                                                        categories_by_section.get(int(primary_sid), [])
                                                    )
                                                },
                                                max_icons=warm_limit,
                                            )
                                    except Exception:
                                        logger.debug(
                                            "BatchDeleteCategoriesCmd.undo: icon warmup failed",
                                            exc_info=True,
                                        )

                                    def _rebuild_tree_sections() -> None:
                                        for section_id, categories in categories_by_section.items():
                                            try:
                                                lightweight_categories: list[dict[str, Any]] = []
                                                for payload in categories or []:
                                                    if not isinstance(payload, dict):
                                                        continue
                                                    item = {
                                                        "id": payload.get("id"),
                                                        "name": payload.get("name", ""),
                                                        "section_id": payload.get("section_id", section_id),
                                                        "position": payload.get("position", 0),
                                                        "__from_undo__": True,
                                                        "__skip_focus__": True,
                                                    }
                                                    icon_path = payload.get("icon_path")
                                                    if isinstance(icon_path, str) and icon_path.strip():
                                                        item["icon_path"] = icon_path
                                                    icon_name = payload.get("icon")
                                                    if isinstance(icon_name, str) and icon_name.strip():
                                                        item["icon"] = icon_name
                                                    lightweight_categories.append(item)
                                                tree_manager.replace_section_categories(
                                                    int(section_id), lightweight_categories
                                                )
                                            except Exception:
                                                logger.debug(
                                                    "BatchDeleteCategoriesCmd.undo: replace_section_categories failed for section %s",
                                                    section_id,
                                                    exc_info=True,
                                                )

                                    try:
                                        QTimer.singleShot(0, _rebuild_tree_sections)
                                    except Exception:
                                        _rebuild_tree_sections()
                                restore_update_ms = (
                                    time.perf_counter() - restore_update_started
                                ) * 1000.0
                                logger.debug(
                                    "BatchDeleteCategoriesCmd.undo: skipped inline category UI restore for large batch; relying on end_batch refresh (count=%s)",
                                    total,
                                )
                            except Exception:
                                logger.debug(
                                    "BatchDeleteCategoriesCmd.undo: lightweight restore update failed",
                                    exc_info=True,
                                )
                        else:
                            restore_update_started = time.perf_counter()
                            _apply_restored_categories_update(
                                business=business,
                                tree_manager=tree_manager,
                                categories_by_section=categories_by_section,
                                restored_sections=None,
                                context="BatchDeleteCategoriesCmd.undo",
                                warm_icon_limit=(24 if total >= large_batch_threshold else None),
                            )
                            restore_update_ms = (
                                time.perf_counter() - restore_update_started
                            ) * 1000.0
                finally:
                    end_batch_started = time.perf_counter()
                    business.end_batch()
                    end_batch_ms = (time.perf_counter() - end_batch_started) * 1000.0
                    if selection_handler is not None:
                        selection_handler.end_suppress_selection()

            if business is not None and tree_manager is None and restored_payloads:
                try:
                    max_emits = int(
                        os.getenv("AITE_UNDO_ITEM_ADDED_EMIT_LIMIT", "10").strip()
                        or "10"
                    )
                except Exception:
                    max_emits = 10
                if max_emits > 0 and len(restored_payloads) <= max_emits:
                    for payload in restored_payloads:
                        section_id = payload.get("section_id")
                        if isinstance(section_id, int):
                            try:
                                business.item_added.emit(
                                    "category", section_id, payload
                                )
                            except Exception:
                                logger.debug(
                                    "BatchDeleteCategoriesCmd.undo: item_added emit failed",
                                    exc_info=True,
                                )
                else:
                    logger.info(
                        "BatchDeleteCategoriesCmd.undo: skip item_added emits (count=%s, limit=%s)",
                        len(restored_payloads),
                        max_emits,
                    )

            if business is not None and restored_payloads:
                if isinstance(first_id, int):
                    focus_started = time.perf_counter()
                    try:
                        if total >= large_batch_threshold:
                            # For large restores, avoid early category selection while
                            # section categories are still loading asynchronously.
                            # Early TABLE switch creates heavy UI contention and delays
                            # `categories_loaded` delivery.
                            def _select_when_ready(
                                cid: int = int(first_id),
                                sid: int | None = (
                                    int(first_section_id)
                                    if isinstance(first_section_id, int)
                                    else None
                                ),
                                attempt: int = 0,
                            ) -> None:
                                try:
                                    if sid is None:
                                        business.select_category(cid)
                                        return
                                    cache = getattr(business, "cache_manager", None)
                                    cached = (
                                        cache.get(f"categories_{sid}") if cache is not None else None
                                    )
                                    ready = isinstance(cached, list) and any(
                                        isinstance(item, dict)
                                        and int(item.get("id", -1)) == cid
                                        for item in cached
                                        if isinstance(item, dict)
                                    )
                                    if ready or attempt >= 20:
                                        business.select_category(cid)
                                        return
                                except Exception:
                                    if attempt >= 20:
                                        try:
                                            business.select_category(cid)
                                        except Exception:
                                            pass
                                    return
                                QTimer.singleShot(
                                    75,
                                    lambda cid=cid, sid=sid, attempt=attempt + 1: _select_when_ready(
                                        cid, sid, attempt
                                    ),
                                )

                            QTimer.singleShot(180, _select_when_ready)
                        else:
                            business.select_category(first_id)
                    except Exception as exc:
                        logger.debug(
                            "BatchDeleteCategoriesCmd.undo: select_category failed: %s",
                            exc,
                            exc_info=True,
                        )
                    finally:
                        focus_restore_ms = (
                            time.perf_counter() - focus_started
                        ) * 1000.0
            if business is not None and total >= large_batch_threshold:
                try:
                    business.resume_structure_preload(
                        delay_ms=1200,
                        reason="batch-delete-categories-undo",
                    )
                except Exception:
                    logger.debug(
                        "BatchDeleteCategoriesCmd.undo: failed to resume structure preload",
                        exc_info=True,
                    )
            ui_phase_ms = (time.perf_counter() - ui_phase_started) * 1000.0
            total_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                "[Perf] UndoTotals batch_delete_categories: db_restore=%.2f ms ui_apply=%.2f ms total=%.2f ms count=%s",
                elapsed_ms,
                ui_phase_ms,
                total_ms,
                _restored_count,
            )
            logger.info(
                "[Perf] UndoBreakdown batch_delete_categories: restore_update=%.2f ms end_batch=%.2f ms focus_restore=%.2f ms count=%s",
                restore_update_ms,
                end_batch_ms,
                focus_restore_ms,
                _restored_count,
            )

        def _on_restore_error(exc: Exception) -> None:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.exception(
                "BatchDeleteCategoriesCmd.undo: restore failed after %.2f ms: %s",
                elapsed_ms,
                exc,
            )
            business = self._resolve_business()
            if business is not None and total >= large_batch_threshold:
                try:
                    business.resume_structure_preload(
                        delay_ms=400,
                        reason="batch-delete-categories-undo-error",
                    )
                except Exception:
                    logger.debug(
                        "BatchDeleteCategoriesCmd.undo: failed to resume preload on error",
                        exc_info=True,
                    )

        run_db(
            _restore_task,
            description="batch_delete_categories_undo_restore",
            on_finished=_after_restore,
            on_error=_on_restore_error,
        )


class DeleteSectionsCmd(BaseCommand):
    """Batch delete multiple sections with bulk storage operations and undo support."""

    def __init__(
        self,
        sections_data: list[dict[str, Any]] | None,
        main_window,
        *,
        business: StructureBusinessLogic | None = None,
        undo_manager: UndoManager | None = None,
    ) -> None:
        super().__init__("Delete sections", main_window)
        self.main = main_window
        self._business = business
        self._undo_manager = undo_manager
        if business is not None:
            self.structure_service = business.structure_service
        else:
            self.db: Database = _resolve_database(main_window)
            self.structure_service = _fallback_structure_service(self)

        self.sections = [dict(x) for x in (sections_data or [])]
        self._section_ids: list[int] = []
        self._backup_trees: list[dict[str, Any]] = []
        self._backup_failed = False
        self._touched_spheres: set[int] = set()

        for payload in self.sections:
            sid = payload.get("id")
            if isinstance(sid, int):
                self._section_ids.append(sid)
                sphere_id = payload.get("sphere_id")
                if isinstance(sphere_id, int):
                    self._touched_spheres.add(int(sphere_id))
                try:
                    tree = self.structure_service.export_section_tree(sid)
                except Exception as exc:
                    self._backup_failed = True
                    logger.warning(
                        "DeleteSectionsCmd.__init__: export_section_tree failed for %s: %s",
                        sid,
                        exc,
                    )
                else:
                    if tree:
                        self._backup_trees.append(tree)

    def _resolve_business(self) -> StructureBusinessLogic | None:
        return self._business or getattr(self.main, "structure_business", None)

    def _dispatch_result(
        self,
        result: Result[Any],
        *,
        description: str,
        on_success: Callable[[Any], None] | None = None,
    ) -> None:
        def _fallback_success(payload: Any) -> None:
            if on_success:
                on_success(payload)

        def _fallback_error(exc: Exception) -> None:
            logger.warning("%s failed: %s", description, exc)

        if self._undo_manager is None:
            if result.is_success():
                _fallback_success(result.value)
            elif result.error:
                _fallback_error(result.error)
            return

        self._undo_manager.dispatch_result(
            result,
            on_success=_fallback_success if on_success else None,
            on_error=_fallback_error,
            description=description,
        )

    def _warn_backup_failed(self) -> None:
        try:
            DialogManager.show_error(
                self.main,
                _tr_undo(_UNDO_BACKUP_FAILED_MESSAGE),
                _tr_undo(_UNDO_DELETE_CANCELED_TITLE),
            )
        except Exception:
            pass

    @log_command
    def redo(self) -> None:
        if self._backup_failed or not self._backup_trees:
            logger.warning("DeleteSectionsCmd.redo: backup missing; delete canceled")
            self.set_obsolete(True)
            self._warn_backup_failed()
            return
        if not self._section_ids:
            return

        logger.info(
            "DeleteSectionsCmd.redo: deleting sections count=%s",
            len(self._section_ids),
        )
        result = self.structure_service.delete_sections_bulk(self._section_ids)

        def _on_success(_: Any) -> None:
            business = self._resolve_business()
            if business is not None:
                try:
                    business.items_batch_deleted.emit(
                        "section", list(self._section_ids)
                    )
                except Exception as exc:
                    logger.debug(
                        "DeleteSectionsCmd.redo: items_batch_deleted emit failed: %s",
                        exc,
                        exc_info=True,
                    )
            _invalidate_links_business_cache(self.main)
            _request_top_panels_refresh(self.main)

        self._dispatch_result(
            result,
            description="delete-sections-redo",
            on_success=_on_success,
        )

    @log_command
    def undo(self) -> None:
        if not self._backup_trees:
            logger.warning("DeleteSectionsCmd.undo: backup missing; undo skipped")
            return
        selection_handler = None
        tree_manager = None
        try:
            structure_ctrl = getattr(self.main, "structure", None)
            selection_handler = getattr(structure_ctrl, "selection_handler", None)
            tree_manager = getattr(structure_ctrl, "tree_manager", None)
        except Exception:
            selection_handler = None
            tree_manager = None

        started = time.perf_counter()
        total = len(self._backup_trees)
        large_restore_sections_threshold = 8
        large_restore_categories_threshold = 64
        logger.info(
            "DeleteSectionsCmd.undo: restoring sections count=%s",
            total,
        )
        business_for_preload = self._resolve_business()
        estimated_categories_total = sum(
            len((tree or {}).get("categories") or []) for tree in (self._backup_trees or [])
        )
        is_large_restore = (
            total >= large_restore_sections_threshold
            or estimated_categories_total >= large_restore_categories_threshold
        )
        if business_for_preload is not None:
            try:
                business_for_preload.suspend_structure_preload(
                    duration_ms=(4500 if is_large_restore else 2500),
                    reason="delete-sections-undo",
                )
            except Exception:
                logger.debug(
                    "DeleteSectionsCmd.undo: failed to suspend structure preload",
                    exc_info=True,
                )

        def _restore_task():
            restored_payloads_local: list[dict[str, Any]] = []
            categories_by_section_local: dict[int, list[dict[str, Any]]] = {}
            restore_trees = self._backup_trees
            deferred_links_local: list[dict[str, Any]] = []
            deferred_link_category_ids_local: set[int] = set()
            if is_large_restore:
                (
                    restore_trees,
                    deferred_links_local,
                    deferred_link_category_ids_local,
                ) = _split_section_trees_for_deferred_links(self._backup_trees)
                logger.info(
                    "DeleteSectionsCmd.undo: deferred links restore enabled sections=%s links=%s categories=%s",
                    total,
                    len(deferred_links_local),
                    len(deferred_link_category_ids_local),
                )
            self.structure_service.import_section_trees_bulk(restore_trees)
            for tree in restore_trees:
                payload = dict(tree.get("section") or {})
                if not payload:
                    continue
                payload["__from_undo__"] = True
                payload["__skip_focus__"] = True
                restored_payloads_local.append(payload)
                categories = tree.get("categories") or []
                section_id = payload.get("id")
                if not isinstance(section_id, int):
                    continue
                bucket = categories_by_section_local.setdefault(section_id, [])
                for item in categories:
                    category_payload = dict((item or {}).get("category") or {})
                    if not category_payload:
                        continue
                    category_payload["__from_undo__"] = True
                    category_payload["__skip_focus__"] = True
                    if not isinstance(category_payload.get("section_id"), int):
                        category_payload["section_id"] = section_id
                    bucket.append(category_payload)
            return (
                restored_payloads_local,
                categories_by_section_local,
                deferred_links_local,
                deferred_link_category_ids_local,
            )

        def _after_restore(
            result: tuple[
                list[dict[str, Any]],
                dict[int, list[dict[str, Any]]],
                list[dict[str, Any]],
                set[int],
            ]
        ) -> None:
            after_db_ts = time.perf_counter()
            elapsed_ms = (after_db_ts - started) * 1000.0
            (
                restored_payloads,
                categories_by_section,
                deferred_links,
                deferred_link_category_ids,
            ) = result
            logger.info(
                "DeleteSectionsCmd.undo: restore completed in %.2f ms (sections=%s)",
                elapsed_ms,
                len(restored_payloads),
            )
            restored_categories_total = sum(
                len(categories or []) for categories in categories_by_section.values()
            )
            is_large_restore_runtime = (
                total >= large_restore_sections_threshold
                or restored_categories_total >= large_restore_categories_threshold
            )
            ui_phase_started = time.perf_counter()
            business = self._resolve_business()
            first_section_id = None
            if restored_payloads:
                try:
                    first_section_id = next(
                        int(s.get("id"))
                        for s in restored_payloads
                        if isinstance(s.get("id"), int)
                    )
                except Exception:
                    first_section_id = None

            restore_update_ms = 0.0
            end_batch_ms = 0.0
            focus_restore_ms = 0.0
            if business is not None:
                if selection_handler is not None:
                    selection_handler.begin_suppress_selection()
                business.begin_batch()
                try:
                    if tree_manager is not None and hasattr(tree_manager, "request_next_snapshot_mode"):
                        try:
                            tree_manager.request_next_snapshot_mode("full_restore")
                        except Exception:
                            logger.debug(
                                "DeleteSectionsCmd.undo: failed to request full_restore snapshot mode",
                                exc_info=True,
                            )
                    if tree_manager is not None and restored_payloads:
                        model = getattr(tree_manager, "model", None)
                        if model is not None and hasattr(model, "insert_sections"):
                            try:
                                restored_payloads.sort(
                                    key=lambda s: (
                                        int(s.get("position"))
                                        if isinstance(s.get("position"), int)
                                        else 0,
                                        str(s.get("name", "")).lower(),
                                    )
                                )
                            except Exception:
                                pass
                            try:
                                model.insert_sections(-1, restored_payloads)
                            except Exception:
                                logger.debug(
                                    "DeleteSectionsCmd.undo: model.insert_sections failed",
                                    exc_info=True,
                                )
                finally:
                    # For large section restores, avoid expensive per-section category replacement in UI.
                    # Prime deferred child payloads instead of materializing thousands of nodes inline.
                    if categories_by_section or restored_payloads:
                        if is_large_restore_runtime:
                            try:
                                restore_update_started = time.perf_counter()
                                _prime_restored_section_categories_deferred(
                                    tree_manager,
                                    categories_by_section,
                                    context="DeleteSectionsCmd.undo.large",
                                )
                                logger.debug(
                                    "DeleteSectionsCmd.undo: primed deferred category payloads for large section restore; skipping full structure reload trigger (sections=%s)",
                                    total,
                                )
                                restore_update_ms = (
                                    time.perf_counter() - restore_update_started
                                ) * 1000.0
                            except Exception:
                                logger.debug(
                                    "DeleteSectionsCmd.undo: lightweight restore update failed",
                                    exc_info=True,
                                )
                        else:
                            restore_update_started = time.perf_counter()
                            _apply_restored_categories_update(
                                business=business,
                                tree_manager=tree_manager,
                                categories_by_section=categories_by_section,
                                restored_sections=restored_payloads,
                                context="DeleteSectionsCmd.undo",
                                warm_icon_limit=(
                                    24 if total >= large_restore_sections_threshold else None
                                ),
                            )
                            restore_update_ms = (
                                time.perf_counter() - restore_update_started
                            ) * 1000.0
                    end_batch_started = time.perf_counter()
                    business.end_batch()
                    end_batch_ms = (time.perf_counter() - end_batch_started) * 1000.0
                    if selection_handler is not None:
                        selection_handler.end_suppress_selection()

            if business is not None and restored_payloads:
                first_id = restored_payloads[0].get("id")
                if isinstance(first_id, int) and not is_large_restore_runtime:
                    focus_started = time.perf_counter()
                    try:
                        business.select_section(first_id)
                    except Exception as exc:
                        logger.debug(
                            "DeleteSectionsCmd.undo: select_section failed: %s",
                            exc,
                            exc_info=True,
                        )
                    finally:
                        focus_restore_ms = (
                            time.perf_counter() - focus_started
                        ) * 1000.0
            if business is not None:
                try:
                    business.resume_structure_preload(
                        delay_ms=(1200 if is_large_restore_runtime else 400),
                        reason="delete-sections-undo",
                    )
                except Exception:
                    logger.debug(
                        "DeleteSectionsCmd.undo: failed to resume structure preload",
                        exc_info=True,
                    )
            ui_phase_ms = (time.perf_counter() - ui_phase_started) * 1000.0
            total_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                "[Perf] UndoTotals delete_sections: db_restore=%.2f ms ui_apply=%.2f ms total=%.2f ms sections=%s",
                elapsed_ms,
                ui_phase_ms,
                total_ms,
                len(restored_payloads),
            )
            logger.info(
                "[Perf] UndoBreakdown delete_sections: restore_update=%.2f ms end_batch=%.2f ms focus_restore=%.2f ms sections=%s",
                restore_update_ms,
                end_batch_ms,
                focus_restore_ms,
                len(restored_payloads),
            )
            if not deferred_links:
                _invalidate_links_business_cache(self.main)
                _request_top_panels_refresh(self.main)
            if deferred_links:
                deferred_links_generation: int | None = None
                if business is not None:
                    try:
                        deferred_links_generation = (
                            business.current_structure_mutation_generation()
                        )
                    except Exception:
                        deferred_links_generation = None
                logger.info(
                    "DeleteSectionsCmd.undo: scheduling deferred links restore links=%s categories=%s",
                    len(deferred_links),
                    len(deferred_link_category_ids),
                )
                def _restore_links_task() -> tuple[bool, int]:
                    current_business = self._resolve_business()
                    if (
                        deferred_links_generation is not None
                        and current_business is not None
                    ):
                        try:
                            if not current_business.is_structure_mutation_generation_current(
                                deferred_links_generation
                            ):
                                logger.info(
                                    "DeleteSectionsCmd.undo: skipped stale deferred links restore scheduled_generation=%s current_generation=%s",
                                    deferred_links_generation,
                                    current_business.current_structure_mutation_generation(),
                                )
                                return (False, 0)
                        except Exception:
                            logger.debug(
                                "DeleteSectionsCmd.undo: failed to validate deferred links restore generation",
                                exc_info=True,
                            )
                    links_started = time.perf_counter()
                    db_obj = _resolve_database(self.main)
                    db_obj.import_export_manager.import_links_bulk(deferred_links)
                    return (True, int((time.perf_counter() - links_started) * 1000.0))

                def _on_links_restored(result: tuple[bool, int] | int) -> None:
                    restored = True
                    duration_ms = 0
                    if isinstance(result, tuple):
                        try:
                            restored, duration_ms = bool(result[0]), int(result[1])
                        except Exception:
                            restored, duration_ms = True, 0
                    else:
                        duration_ms = int(result)
                    if not restored:
                        logger.info(
                            "DeleteSectionsCmd.undo.deferred_links_restore: skipped stale restore links=%s categories=%s",
                            len(deferred_links),
                            len(deferred_link_category_ids),
                        )
                        return
                    logger.info(
                        "[Perf] DeleteSectionsCmd.undo.deferred_links_restore: links=%s categories=%s total=%s ms",
                        len(deferred_links),
                        len(deferred_link_category_ids),
                        duration_ms,
                    )
                    _invalidate_links_business_cache(self.main)
                    _request_top_panels_refresh(self.main)
                    try:
                        current_category_id = self.main.get_current_category_id()
                    except Exception:
                        current_category_id = None
                    if (
                        isinstance(current_category_id, int)
                        and current_category_id in deferred_link_category_ids
                    ):
                        try:
                            self.main.reload_current_category()
                        except Exception:
                            logger.debug(
                                "DeleteSectionsCmd.undo: reload_current_category failed after deferred links restore",
                                exc_info=True,
                            )

                def _on_links_restore_error(exc: Exception) -> None:
                    logger.exception(
                        "DeleteSectionsCmd.undo: deferred links restore failed: %s",
                        exc,
                    )

                run_db(
                    _restore_links_task,
                    description="delete_sections_undo_restore_links",
                    on_finished=_on_links_restored,
                    on_error=_on_links_restore_error,
                )

        def _on_restore_error(exc: Exception) -> None:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.exception(
                "DeleteSectionsCmd.undo: restore failed after %.2f ms: %s",
                elapsed_ms,
                exc,
            )
            business = self._resolve_business()
            if business is not None:
                try:
                    business.resume_structure_preload(
                        delay_ms=250,
                        reason="delete-sections-undo-error",
                    )
                except Exception:
                    logger.debug(
                        "DeleteSectionsCmd.undo: failed to resume preload on error",
                        exc_info=True,
                    )

        run_db(
            _restore_task,
            description="delete_sections_undo_restore",
            on_finished=_after_restore,
            on_error=_on_restore_error,
        )


class PasteCategoriesCmd(BaseCommand):
    """Paste categories as a single undoable command."""

    def __init__(
        self,
        trees: list[dict],
        section_id: int,
        main_window,
        *,
        business: StructureBusinessLogic | None = None,
        undo_manager: UndoManager | None = None,
    ) -> None:
        super().__init__("Paste categories", main_window)
        self.main = main_window
        self._business = business
        self._undo_manager = undo_manager
        self._section_id = int(section_id)
        self._trees = list(trees or [])
        self._created_category_ids: list[int] = []
        db = _resolve_database(main_window)
        self._svc = _new_structure_context_service(db)
        self._structure_service = (
            business.structure_service if business is not None else _new_structure_service(db)
        )

    def _resolve_business(self) -> StructureBusinessLogic | None:
        return self._business or getattr(self.main, "structure_business", None)

    def _refresh_after_categories(self) -> None:
        business = self._resolve_business()
        if business is None:
            return
        try:
            clear_icon_cache()
        except Exception:
            logger.debug("PasteCategoriesCmd: clear_icon_cache failed", exc_info=True)
        try:
            business._invalidate_categories_cache(int(self._section_id))
        except Exception:
            logger.debug("PasteCategoriesCmd: invalidate cache failed", exc_info=True)
        try:
            categories = business.get_categories(int(self._section_id)) or []
        except Exception:
            categories = []
            logger.debug("PasteCategoriesCmd: get_categories failed", exc_info=True)
        try:
            structure_ctrl = getattr(self.main, "structure", None)
            tree_manager = getattr(structure_ctrl, "tree_manager", None)
            if tree_manager is not None and hasattr(
                tree_manager, "replace_section_categories"
            ):
                tree_manager.replace_section_categories(
                    int(self._section_id),
                    categories,
                )
        except Exception:
            logger.debug(
                "PasteCategoriesCmd: replace_section_categories failed",
                exc_info=True,
            )
        try:
            business.section_selected.emit(int(self._section_id))
        except Exception:
            logger.debug("PasteCategoriesCmd: section_selected failed", exc_info=True)

    def redo(self) -> None:
        if not self._trees:
            return
        created, _link_ids = self._svc.paste_category_trees_to_section(
            self._trees, self._section_id
        )
        self._created_category_ids = [
            int(c.get("id")) for c in created if isinstance(c.get("id"), int)
        ]
        self._refresh_after_categories()

    def undo(self) -> None:
        if not self._created_category_ids:
            return
        try:
            self._structure_service.delete_categories_bulk(self._created_category_ids)
        except Exception:
            logger.exception("PasteCategoriesCmd.undo: delete failed")
        self._refresh_after_categories()


class PasteSectionsCmd(BaseCommand):
    """Paste sections as a single undoable command."""

    def __init__(
        self,
        trees: list[dict],
        sphere_id: int,
        main_window,
        *,
        business: StructureBusinessLogic | None = None,
        undo_manager: UndoManager | None = None,
    ) -> None:
        super().__init__("Paste sections", main_window)
        self.main = main_window
        self._business = business
        self._undo_manager = undo_manager
        self._sphere_id = int(sphere_id)
        self._trees = list(trees or [])
        self._created_section_ids: list[int] = []
        self._merged_section_ids: list[int] = []
        self._merged_category_ids: list[int] = []
        self._merged_link_ids: list[int] = []
        db = _resolve_database(main_window)
        self._svc = _new_structure_context_service(db)
        self._structure_service = (
            business.structure_service if business is not None else _new_structure_service(db)
        )
        self._links_service = _new_links_service(db)

    def _resolve_business(self) -> StructureBusinessLogic | None:
        return self._business or getattr(self.main, "structure_business", None)

    def _refresh_after_sections(self, *, is_undo: bool = False) -> None:
        business = self._resolve_business()
        if business is None:
            return
        try:
            clear_icon_cache()
        except Exception:
            logger.debug("PasteSectionsCmd: clear_icon_cache failed", exc_info=True)
        try:
            business._invalidate_structure_cache()
        except Exception:
            logger.debug("PasteSectionsCmd: invalidate cache failed", exc_info=True)
        did_targeted_refresh = False
        try:
            sections = business.get_sections(int(self._sphere_id)) or []
            sections_by_id = {
                int(section.get("id")): dict(section)
                for section in sections
                if isinstance(section, dict) and isinstance(section.get("id"), int)
            }
            structure_ctrl = getattr(self.main, "structure", None)
            tree_manager = getattr(structure_ctrl, "tree_manager", None)

            if is_undo:
                item_deleted = getattr(business, "item_deleted", None)
                if item_deleted is not None and hasattr(item_deleted, "emit"):
                    for section_id in self._created_section_ids:
                        item_deleted.emit("section", int(section_id))
                    did_targeted_refresh = True
            else:
                item_added = getattr(business, "item_added", None)
                if item_added is not None and hasattr(item_added, "emit"):
                    for section_id in self._created_section_ids:
                        payload = sections_by_id.get(int(section_id))
                        if payload:
                            item_added.emit("section", int(self._sphere_id), payload)
                            did_targeted_refresh = True

            section_ids_to_refresh = {
                int(section_id)
                for section_id in (
                    list(self._created_section_ids) + list(self._merged_section_ids)
                )
                if isinstance(section_id, int) and int(section_id) > 0
            }
            if (
                tree_manager is not None
                and hasattr(tree_manager, "replace_section_categories")
            ):
                for section_id in sorted(section_ids_to_refresh):
                    categories = business.get_categories(int(section_id)) or []
                    tree_manager.replace_section_categories(int(section_id), categories)
                if section_ids_to_refresh:
                    did_targeted_refresh = True
        except Exception:
            logger.debug("PasteSectionsCmd: targeted refresh failed", exc_info=True)
            did_targeted_refresh = False
        if not did_targeted_refresh:
            try:
                if getattr(business, "async_service", None):
                    business.async_service.schedule_structure_reload(0)
            except Exception:
                logger.debug("PasteSectionsCmd: schedule reload failed", exc_info=True)

    def redo(self) -> None:
        if not self._trees:
            return
        stats = self._svc.paste_section_trees_to_sphere(self._trees, self._sphere_id)
        self._created_section_ids = list(stats.get("created_section_ids") or [])
        self._merged_section_ids = list(stats.get("merged_section_ids") or [])
        self._merged_category_ids = list(stats.get("merged_category_ids") or [])
        self._merged_link_ids = list(stats.get("merged_link_ids") or [])
        self._refresh_after_sections()

    def undo(self) -> None:
        try:
            if self._merged_link_ids:
                self._links_service.batch_delete_links(self._merged_link_ids)
        except Exception:
            logger.exception("PasteSectionsCmd.undo: delete links failed")
        try:
            if self._merged_category_ids:
                self._structure_service.delete_categories_bulk(self._merged_category_ids)
        except Exception:
            logger.exception("PasteSectionsCmd.undo: delete categories failed")
        for sec_id in reversed(self._created_section_ids):
            try:
                self._structure_service.delete_section(int(sec_id))
            except Exception:
                logger.exception(
                    "PasteSectionsCmd.undo: delete section failed id=%s", sec_id
                )
        self._refresh_after_sections(is_undo=True)


class SaveCategoryCmd(BaseCommand):
    """Save (create/edit) category using Result dispatch."""

    def __init__(
        self,
        new_data: dict,
        old_data: dict | None,
        main_window,
        *,
        business: StructureBusinessLogic | None = None,
        undo_manager: UndoManager | None = None,
        skip_reload: bool = False,
    ) -> None:
        super().__init__("Save category", main_window)
        self.main = main_window
        self._business = business
        self._undo_manager = undo_manager
        if business is not None:
            self.structure_service = business.structure_service
        else:
            self.db: Database = _resolve_database(main_window)
            self.structure_service = _fallback_structure_service(self)
        self.new_data = dict(new_data) if new_data else {}
        self.old_data = dict(old_data) if old_data else None
        self.is_new = not bool(self.new_data.get("id"))
        self.new_id = self.new_data.get("id")
        self.skip_reload = skip_reload
        self._last_snapshot: UndoResultSnapshot | None = None

    def _store_snapshot(self, snapshot: UndoResultSnapshot | None) -> None:
        self._last_snapshot = snapshot

    def _resolve_business(self) -> StructureBusinessLogic | None:
        return self._business or getattr(self.main, "structure_business", None)

    def _dispatch_result(
        self,
        result: Result[dict[str, Any] | None],
        *,
        description: str,
        on_success: Callable[[dict[str, Any] | None], None] | None = None,
    ) -> None:
        def _fallback_success(payload: dict[str, Any] | None) -> None:
            if on_success:
                on_success(payload)

        def _fallback_error(exc: Exception) -> None:
            logger.warning("%s failed: %s", description, exc)

        if self._undo_manager is None:
            if result.is_success():
                _fallback_success(result.value)
            elif result.error:
                _fallback_error(result.error)
            return

        self._undo_manager.dispatch_result(
            result,
            on_success=_fallback_success if on_success else None,
            on_error=_fallback_error,
            description=description,
        )

    def _maybe_clear_icon_cache(
        self,
        payload: dict[str, Any] | None,
    ) -> None:
        if self.skip_reload:
            return
        try:
            if self.old_data and payload:
                icon_path_changed = (
                    payload.get("icon_path") != self.old_data.get("icon_path")
                )
                if icon_path_changed:
                    clear_icon_cache()
                    logger.debug("Category icon path changed, clearing icon cache")
        except Exception as exc:
            logger.warning(
                "SaveCategoryCmd._maybe_clear_icon_cache: failed to clear cache: %s",
                exc,
            )

    def _emit_reload(self, payload: dict[str, Any] | None) -> None:
        if self.skip_reload:
            return
        business = self._resolve_business()
        if business is None:
            return
        try:
            if self.is_new:
                parent_id = (payload or self.new_data or {}).get("section_id")
                business.item_added.emit("category", parent_id, payload or self.new_data)
            else:
                business.item_updated.emit("category", self.new_id, payload or self.new_data)
        except Exception as exc:
            logger.warning("SaveCategoryCmd._emit_reload: emit failed: %s", exc)

    @log_command
    def redo(self) -> None:
        if self.is_new:
            result = self.structure_service.create_category(self.new_data)
        else:
            if self.old_data:
                for key in ("id", "section_id", "position", "icon_path"):
                    if key not in self.new_data and key in self.old_data:
                        self.new_data[key] = self.old_data[key]
                if "name" not in self.new_data and "name" in self.old_data:
                    self.new_data["name"] = self.old_data["name"]
            result = self.structure_service.update_category(
                int(self.new_data.get("id")), self.new_data
            )

        def _on_success(payload: dict[str, Any] | None) -> None:
            was_new = self.is_new
            if isinstance(payload, dict):
                self.new_data = dict(payload)
            new_id = self.new_data.get("id")
            if isinstance(new_id, int):
                self.new_id = new_id
            self._maybe_clear_icon_cache(self.new_data)
            business = self._resolve_business()
            if (
                business is not None
                and not self.skip_reload
                and isinstance(self.new_id, int)
                and not was_new
            ):
                try:
                    business.select_category(self.new_id)
                except Exception as exc:
                    logger.warning("SaveCategoryCmd.redo: select_category failed: %s", exc)
            self._emit_reload(payload)
            self.is_new = False
            self._store_snapshot(
                _snapshot_from_result(result, payload=payload or self.new_data)
            )

        self._dispatch_result(
            result,
            description="save-category-redo" if not self.is_new else "create-category-redo",
            on_success=_on_success,
        )

    @log_command
    def undo(self) -> None:
        if self.is_new:
            result = self.structure_service.delete_category(int(self.new_id))

            def _on_delete_success(payload: dict[str, Any] | None) -> None:
                business = self._resolve_business()
                if business is not None and not self.skip_reload and isinstance(self.new_id, int):
                    try:
                        section_id = self.new_data.get("section_id")
                        business.section_selected.emit(int(section_id))
                    except Exception as exc:
                        logger.warning("SaveCategoryCmd.undo: select_section failed: %s", exc)
                business = self._resolve_business()
                if business is not None and isinstance(self.new_id, int):
                    try:
                        business.item_deleted.emit("category", int(self.new_id))
                    except Exception as exc:
                        logger.warning("SaveCategoryCmd.undo: item_deleted emit failed: %s", exc)
                self._store_snapshot(_snapshot_from_result(result))

            self._dispatch_result(
                result,
                description="save-category-undo-delete",
                on_success=_on_delete_success,
            )
            return

        if not self.old_data:
            return

        result = self.structure_service.update_category(
            int(self.old_data["id"]), self.old_data
        )

        def _on_restore_success(payload: dict[str, Any] | None) -> None:
            restored = dict(payload) if isinstance(payload, dict) else dict(self.old_data)
            self.new_data = restored
            self.new_id = restored.get("id", self.new_id)
            self._maybe_clear_icon_cache(restored)
            business = self._resolve_business()
            if business is not None and not self.skip_reload:
                try:
                    business.select_category(int(restored["id"]))
                except Exception as exc:
                    logger.warning(
                        "SaveCategoryCmd.undo: select_category failed: %s",
                        exc,
                    )
            self._emit_reload(restored)
            self._store_snapshot(
                _snapshot_from_result(result, payload=restored)
            )

        self._dispatch_result(
            result,
            description="save-category-undo-update",
            on_success=_on_restore_success,
        )


class DeleteCategoryCmd(BaseCommand):
    """Delete category with subtree restore (category+links)."""

    def __init__(
        self,
        category_data: dict,
        main_window,
        *,
        business: StructureBusinessLogic | None = None,
        undo_manager: UndoManager | None = None,
        skip_reload: bool = False,
        lightweight_reload: bool = False,
    ) -> None:
        super().__init__("Delete category", main_window)
        self.main = main_window
        self._business = business
        self._undo_manager = undo_manager
        if business is not None:
            self.structure_service = business.structure_service
        else:
            self.db: Database = _resolve_database(main_window)
            self.structure_service = _fallback_structure_service(self)
        self.category = dict(category_data) if category_data else {}
        self.skip_reload = bool(skip_reload)
        self.lightweight_reload = bool(lightweight_reload)
        self._backup_tree: dict | None = None
        self._backup_failed = False
        self._last_snapshot: UndoResultSnapshot | None = None
        cat_id_obj = self.category.get("id")
        if isinstance(cat_id_obj, int):
            try:
                self._backup_tree = self.structure_service.export_category_tree(
                    cat_id_obj
                )
            except Exception as exc:
                self._backup_failed = True
                logger.warning(
                    "DeleteCategoryCmd.__init__: export_category_tree failed: %s",
                    exc,
                )

    def _store_snapshot(self, snapshot: UndoResultSnapshot | None) -> None:
        self._last_snapshot = snapshot

    def _resolve_business(self) -> StructureBusinessLogic | None:
        return self._business or getattr(self.main, "structure_business", None)

    def _dispatch_result(
        self,
        result: Result[dict[str, Any] | None],
        *,
        description: str,
        on_success: Callable[[dict[str, Any] | None], None] | None = None,
    ) -> None:
        def _fallback_success(payload: dict[str, Any] | None) -> None:
            if on_success:
                on_success(payload)

        def _fallback_error(exc: Exception) -> None:
            logger.warning("%s failed: %s", description, exc)

        if self._undo_manager is None:
            if result.is_success():
                _fallback_success(result.value)
            elif result.error:
                _fallback_error(result.error)
            return

        self._undo_manager.dispatch_result(
            result,
            on_success=_fallback_success if on_success else None,
            on_error=_fallback_error,
            description=description,
        )

    def _handle_skip_reload(
        self, business: StructureBusinessLogic | None, category_id: int
    ) -> None:
        try:
            if business:
                business.item_deleted.emit("category", category_id)
        except Exception as exc:
            logger.warning(
                "DeleteCategoryCmd.redo(skip_reload): item_deleted emit failed: %s",
                exc,
            )

    def _handle_lightweight_reload(
        self,
        business: StructureBusinessLogic | None,
        section_id: int | None,
        category_id: int,
    ) -> None:
        try:
            if business and isinstance(section_id, int):
                business.section_selected.emit(section_id)
        except Exception as exc:
            logger.warning(
                "DeleteCategoryCmd.redo(lightweight): select_section failed: %s",
                exc,
            )
        try:
            if business and isinstance(section_id, int):
                try:
                    business._invalidate_categories_cache(section_id)
                except Exception as exc:
                    logger.debug(
                        "DeleteCategoryCmd.redo(lightweight): invalidate cache failed: %s",
                        exc,
                    )
                business.section_selected.emit(section_id)
                business.item_deleted.emit("category", category_id)
        except Exception as exc:
            logger.warning(
                "DeleteCategoryCmd.redo(lightweight): updates failed: %s", exc
            )

    def _handle_regular_reload(
        self,
        business: StructureBusinessLogic | None,
        section_id: int | None,
        category_id: int,
    ) -> None:
        try:
            if business and isinstance(section_id, int):
                try:
                    business._invalidate_categories_cache(section_id)
                except Exception as exc:
                    logger.debug(
                        "DeleteCategoryCmd.redo: invalidate cache failed: %s", exc
                    )
                business.section_selected.emit(section_id)
        except Exception as exc:
            logger.warning("DeleteCategoryCmd.redo: select_section failed: %s", exc)
        try:
            if business:
                try:
                    clear_icon_cache()
                except Exception as exc:
                    logger.debug(
                        "DeleteCategoryCmd.redo: clear_icon_cache failed: %s", exc
                    )
                business.item_deleted.emit("category", category_id)
        except Exception as exc:
            logger.warning("DeleteCategoryCmd.redo: item_deleted emit failed: %s", exc)

    def _emit_restore_signals(self, payload: dict[str, Any]) -> None:
        business = self._resolve_business()
        category_id = payload.get("id") if isinstance(payload, dict) else None
        section_id = payload.get("section_id") if isinstance(payload, dict) else None
        try:
            if business and isinstance(category_id, int):
                business.select_category(category_id)
        except Exception as exc:
            logger.debug("DeleteCategoryCmd.undo: select_category failed: %s", exc)
        try:
            if business:
                try:
                    clear_icon_cache()
                except Exception:
                    pass
                payload = dict(payload)
                payload["__from_undo__"] = True
                business.item_added.emit("category", section_id, payload)
        except Exception as exc:
            logger.debug("DeleteCategoryCmd.undo: item_added emit failed: %s", exc)

    def _import_backup_tree(self) -> bool:
        try:
            self.structure_service.import_category_tree(self._backup_tree)
            return True
        except Exception as exc:
            logger.exception("DeleteCategoryCmd.undo: restore failed: %s", exc)
            return False

    def _build_invalidate_regions(
        self, payload: dict[str, Any]
    ) -> tuple[InvalidateRegion, ...]:
        section_identifier = payload.get("section_id") if isinstance(payload, dict) else None
        if isinstance(section_identifier, int):
            return (
                InvalidateRegion(scope="categories", identifier=section_identifier),
            )
        return tuple()

    def _make_restore_success_handler(
        self,
        restore_result: Result[dict[str, Any] | None],
        restored_payload: dict[str, Any],
    ) -> Callable[[dict[str, Any] | None], None]:
        def _on_success(payload: dict[str, Any] | None) -> None:
            data = dict(payload) if isinstance(payload, dict) else dict(restored_payload)
            self.category = data
            self._emit_restore_signals(data)
            self._store_snapshot(
                _snapshot_from_result(restore_result, payload=data)
            )

        return _on_success

    def _prepare_restore_payload(self) -> tuple[dict[str, Any], Result[dict[str, Any] | None]]:
        restored_payload = dict(self._backup_tree.get("category") or {})
        if restored_payload:
            self.category = dict(restored_payload)
        invalidate = self._build_invalidate_regions(restored_payload)
        restore_result = Result.success(restored_payload or None, invalidate=invalidate)
        return restored_payload, restore_result

    @log_command
    def redo(self) -> None:
        if self._backup_failed or not self._backup_tree:
            logger.warning("DeleteCategoryCmd.redo: backup missing; delete canceled")
            self.set_obsolete(True)
            self._warn_backup_failed()
            return
        try:
            if getattr(self.main, "_suppress_deletes", False):
                logger.debug(
                    "[DeleteGuard] DeleteCategoryCmd.redo suppressed by _suppress_deletes flag"
                )
                return
        except Exception as exc:
            logger.debug(
                "DeleteCategoryCmd.redo: delete guard check failed: %s",
                exc,
                exc_info=True,
            )
        category_id_obj = self.category.get("id")
        if not isinstance(category_id_obj, int):
            return
        category_id = category_id_obj
        result = self.structure_service.delete_category(category_id)
        section_id_obj = self.category.get("section_id")
        section_id = section_id_obj if isinstance(section_id_obj, int) else None

        def _on_success(payload: dict[str, Any] | None) -> None:
            business = self._resolve_business()
            if self.skip_reload:
                self._handle_skip_reload(business, category_id)
            elif self.lightweight_reload:
                self._handle_lightweight_reload(business, section_id, category_id)
            else:
                self._handle_regular_reload(business, section_id, category_id)
            self._store_snapshot(_snapshot_from_result(result))

        self._dispatch_result(
            result,
            description="delete-category-redo",
            on_success=_on_success,
        )

    @log_command
    def undo(self) -> None:
        if not self._backup_tree:
            logger.warning("DeleteCategoryCmd.undo: backup missing; undo skipped")
            return
        if not self._import_backup_tree():
            return

        restored_payload, restore_result = self._prepare_restore_payload()
        success_handler = self._make_restore_success_handler(
            restore_result,
            restored_payload,
        )

        self._dispatch_result(
            restore_result,
            description="delete-category-undo",
            on_success=success_handler,
        )

    def _warn_backup_failed(self) -> None:
        try:
            DialogManager.show_error(
                self.main,
                _tr_undo(_UNDO_BACKUP_FAILED_MESSAGE),
                _tr_undo(_UNDO_DELETE_CANCELED_TITLE),
            )
        except Exception:
            pass

