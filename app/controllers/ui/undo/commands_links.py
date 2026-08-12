# app/utils/system/undo/commands_links.py
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QCoreApplication

from app.config_data.runtime_config import get_table_selection_restore_delay_ms
from app.controllers.ui.state.task_scheduler import schedule_selection_restore
from app.controllers.ui.undo.base import BaseCommand, log_command
from app.controllers.ui.dialogs import DialogManager
from app.services import LinksService
from app.utils.db.api import run_db


def _cached_service(obj: Any, attr_name: str, factory: Callable[[], Any]) -> Any:
    """Lazily cache service instance on command object."""
    service = getattr(obj, attr_name, None)
    if service is None:
        service = factory()
        setattr(obj, attr_name, service)
    return service


def _new_links_service(cmd: Any) -> LinksService:
    return LinksService(cmd.db)


def _links_service_for(cmd: Any) -> LinksService:
    """Lazily cache fallback LinksService per command instance."""
    return _cached_service(
        cmd,
        "_links_service_cache",
        lambda: _new_links_service(cmd),
    )


def _reload_links_via_controller(main_window, category_ids) -> None:
    ctrl = getattr(main_window, "links_table_controller", None)
    if ctrl is None or not hasattr(ctrl, "reload"):
        logger.warning("LinksTableController unavailable for reload")
        return
    unique_ids = set(category_ids or [])
    for cat_id in unique_ids:
        if isinstance(cat_id, int) and cat_id > 0:
            try:
                ctrl.reload(cat_id)
            except Exception as exc:
                logger.warning(
                    "LinksTableController.reload failed for category %s: %s",
                    cat_id,
                    exc,
                )

logger = logging.getLogger(__name__)


def _show_links_command_error(main_window, title: str, message: str) -> None:
    try:
        DialogManager.show_error(main_window, message, title)
    except Exception:
        logger.debug("Failed to show links command error dialog", exc_info=True)


def _run_links_db_command(
    task: Callable[[], Any],
    *,
    description: str,
    on_finished: Callable[[Any], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    run_db(
        task,
        description=description,
        on_finished=on_finished,
        on_error=on_error,
    )


def _is_valid_category_id(value: Any) -> bool:
    return isinstance(value, int) and value > 0


def _resolve_category_id(main_window: Any, *payloads: Any) -> int | None:
    for payload in payloads:
        if isinstance(payload, dict):
            category_id = payload.get("category_id")
            if _is_valid_category_id(category_id):
                return int(category_id)

    getter = getattr(main_window, "get_current_category_id", None)
    if callable(getter):
        try:
            category_id = getter()
        except Exception:
            logger.debug(
                "Failed to resolve current category via get_current_category_id",
                exc_info=True,
            )
        else:
            if _is_valid_category_id(category_id):
                return int(category_id)

    category_id = getattr(main_window, "current_category_id", None)
    if _is_valid_category_id(category_id):
        return int(category_id)

    ui_state = getattr(main_window, "ui_state", None)
    getter = getattr(ui_state, "get_current_category_id", None)
    if callable(getter):
        try:
            category_id = getter()
        except Exception:
            logger.debug(
                "Failed to resolve current category via ui_state",
                exc_info=True,
            )
        else:
            if _is_valid_category_id(category_id):
                return int(category_id)

    return None


def _ensure_link_category_id(main_window: Any, payload: dict[str, Any]) -> int | None:
    if not isinstance(payload, dict):
        return None
    category_id = _resolve_category_id(main_window, payload)
    if category_id is not None:
        payload["category_id"] = category_id
    return category_id


def _ensure_link_category_ids(
    main_window: Any, payloads: list[dict[str, Any]]
) -> tuple[set[int], bool]:
    affected_categories: set[int] = set()
    missing_category = False
    fallback_category_id = _resolve_category_id(main_window)
    for payload in payloads or []:
        if not isinstance(payload, dict):
            missing_category = True
            continue
        category_id = _resolve_category_id(main_window, payload)
        if category_id is None:
            category_id = fallback_category_id
        if category_id is None:
            missing_category = True
            continue
        payload["category_id"] = category_id
        affected_categories.add(category_id)
    return affected_categories, missing_category


def _validate_batch_link_restore_result(
    links: list[dict[str, Any]],
    restored_ids: list[int] | tuple[int, ...] | None,
) -> list[int]:
    restored = [int(link_id) for link_id in (restored_ids or []) if isinstance(link_id, int)]
    expected_count = len(list(links or []))
    if len(restored) != expected_count:
        raise RuntimeError(
            f"expected to restore {expected_count} links, restored {len(restored)}"
        )
    expected_ids = [
        int(link.get("id"))
        for link in (links or [])
        if isinstance(link, dict) and isinstance(link.get("id"), int)
    ]
    if len(expected_ids) == expected_count and set(restored) != set(expected_ids):
        raise RuntimeError(
            "restored link ids do not match expected deleted link ids"
        )
    return restored


def _apply_created_id_to_link(link: dict[str, Any], link_id: int | None) -> dict[str, Any]:
    payload = dict(link or {})
    if isinstance(link_id, int) and link_id > 0:
        payload["id"] = link_id
    return payload


def _extract_internal_link_flags(link: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(link, dict):
        return {}
    return {
        key: value
        for key, value in link.items()
        if isinstance(key, str) and key.startswith("_")
    }


def _should_enqueue_link_enrichment(link: dict[str, Any]) -> bool:
    if not isinstance(link, dict):
        return False
    return bool(
        link.get("_defer_enrichment") or link.get("_reparse_icon")
    )


def _enqueue_link_enrichment(main_window: Any, payload: dict[str, Any]) -> bool:
    try:
        from app.controllers.ui.links.icon_enrichment_service import (
            enqueue_link_icon_enrichment,
        )

        return bool(enqueue_link_icon_enrichment(main_window, payload))
    except Exception:
        logger.debug("Failed to enqueue link enrichment", exc_info=True)
        return False

class SaveLinkCmd(BaseCommand):
    def __init__(self, new_data: dict, old_data: dict | None, main_window):
        super().__init__("Save link", main_window)
        self.main = main_window
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
        self.new_data = dict(new_data) if new_data else {}
        self.old_data = dict(old_data) if old_data else None
        self.created_id: int | None = None
        self._in_flight = False

    def _merge_old_data(self):
        """Merge missing fields from old_data into new_data."""
        try:
            if self.old_data:
                for k in ("id", "category_id", "position", "favorite"):
                    if k not in self.new_data and k in self.old_data:
                        self.new_data[k] = self.old_data[k]
                for k in ("name", "url", "args", "icon_path"):
                    if k not in self.new_data and k in self.old_data:
                        self.new_data[k] = self.old_data[k]
        except Exception as exc:
            logger.exception("SaveLinkCmd.redo: failed to merge old/new data: %s", exc)

    def _save_link(self):
        """Save link via service layer."""
        if hasattr(self.main, "links_business") and self.main.links_business:
            result = self.main.links_business.links.create_or_update_link(self.new_data)
        else:
            result = _links_service_for(self).create_or_update_link(self.new_data)
        if result and not self.new_data.get("id"):
            self.new_data["id"] = result
            self.created_id = result
        return result

    def _refresh_saved_link_payload(self) -> None:
        link_id = self.new_data.get("id") or self.created_id
        if not isinstance(link_id, int) or link_id <= 0:
            return
        flags = _extract_internal_link_flags(self.new_data)
        try:
            if hasattr(self.main, "links_business") and self.main.links_business:
                refreshed = self.main.links_business.links.get_link_by_id(link_id)
            else:
                refreshed = _links_service_for(self).get_link_by_id(link_id)
        except Exception:
            logger.debug(
                "SaveLinkCmd: failed to refresh saved link payload",
                exc_info=True,
            )
            return
        if not isinstance(refreshed, dict) or not refreshed:
            return
        self.new_data = dict(refreshed)
        self.new_data.update(flags)

    def _emit_link_updated(self):
        """Emit link_updated signal."""
        if hasattr(self.main, "links_business") and self.main.links_business:
            try:
                self.main.links_business.link_updated.emit(self.new_data)
            except Exception as exc:
                logger.warning("SaveLinkCmd.redo: link_updated emit failed: %s", exc)

    def _reload_table_if_needed(self):
        """Reload table for current category if not suppressed."""
        try:
            if not getattr(self, "_suppress_ui", False):
                cat_id = self.new_data.get("category_id") or (self.old_data or {}).get(
                    "category_id"
                )
                if isinstance(cat_id, int) and cat_id > 0:
                    _reload_links_via_controller(self.main, {cat_id})
        except Exception as exc:
            logger.warning(
                "SaveLinkCmd.redo: reload failed: %s",
                exc,
            )

    def _emit_top_panels_refresh(self) -> None:
        link_ops = getattr(self.main, "link_operations", None)
        if link_ops is None:
            return
        try:
            link_ops.emit_top_panels_changed(favorites=True, recents=True)
        except Exception:
            logger.debug(
                "SaveLinkCmd: top panels refresh emit failed",
                exc_info=True,
            )

    def _invalidate_links_cache(self) -> None:
        links_business = getattr(self.main, "links_business", None)
        if links_business is None:
            return
        try:
            if hasattr(links_business, "invalidate_cache"):
                links_business.invalidate_cache()
            elif hasattr(links_business, "_invalidate_cache"):
                links_business._invalidate_cache()
        except Exception:
            logger.debug(
                "SaveLinkCmd: cache invalidation failed",
                exc_info=True,
            )

    def _notify_link_ops_after_save(self) -> None:
        link_ops = getattr(self.main, "link_operations", None)
        if link_ops is None:
            return
        try:
            cat_id = self.new_data.get("category_id") or (self.old_data or {}).get(
                "category_id"
            )
            if isinstance(cat_id, int) and cat_id > 0 and hasattr(
                link_ops, "emit_links_changed"
            ):
                link_ops.emit_links_changed(cat_id)
            if hasattr(link_ops, "emit_link_saved"):
                link_ops.emit_link_saved(dict(self.new_data))
        except Exception:
            logger.debug(
                "SaveLinkCmd: failed to notify LinkOperationsController after save",
                exc_info=True,
            )

    def _schedule_focus_if_created(self) -> None:
        link_id = self.created_id
        if not isinstance(link_id, int) or link_id <= 0:
            return
        links_actions = getattr(self.main, "links_actions", None)
        if links_actions is None or not hasattr(links_actions, "focus_on_link"):
            return
        try:
            delay_ms = get_table_selection_restore_delay_ms(100)
            schedule_selection_restore(
                lambda: links_actions.focus_on_link(link_id),
                link_id,
                delay=delay_ms,
            )
        except Exception:
            logger.debug(
                "SaveLinkCmd: failed to schedule focus for created link",
                exc_info=True,
            )

    def _enqueue_post_save_enrichment(self) -> None:
        try:
            payload = _apply_created_id_to_link(self.new_data, self.created_id)
            if not _should_enqueue_link_enrichment(payload):
                return
            _enqueue_link_enrichment(self.main, payload)
        except Exception:
            logger.debug(
                "SaveLinkCmd: failed to enqueue post-save enrichment",
                exc_info=True,
            )

    @log_command
    def redo(self):
        self._merge_old_data()
        category_id = _ensure_link_category_id(self.main, self.new_data)
        if category_id is None:
            logger.warning("SaveLinkCmd.redo skipped: missing category_id")
            self.set_obsolete(True)
            _show_links_command_error(
                self.main,
                "Save link failed",
                "Cannot save link because no category is selected.",
            )
            return
        if self._in_flight:
            logger.debug("SaveLinkCmd.redo ignored: operation already in flight")
            return

        # Compatibility path for non-GUI contexts (tests/scripts): execute inline.
        # In regular app runtime (QApplication exists), keep async behavior.
        if QCoreApplication.instance() is None:
            try:
                self._save_link()
                self._refresh_saved_link_payload()
                self._emit_link_updated()
                self._reload_table_if_needed()
                self._emit_top_panels_refresh()
                self._invalidate_links_cache()
                self._notify_link_ops_after_save()
                self._enqueue_post_save_enrichment()
                self._schedule_focus_if_created()
            except Exception as exc:
                logger.warning("SaveLinkCmd.redo sync fallback failed: %s", exc)
                _show_links_command_error(
                    self.main,
                    "Save link failed",
                    f"Failed to save link: {exc}",
                )
            return

        self._in_flight = True

        def _task() -> int | None:
            return self._save_link()

        def _on_finished(_result: int | None) -> None:
            try:
                self._refresh_saved_link_payload()
                self._emit_link_updated()
                self._reload_table_if_needed()
                self._emit_top_panels_refresh()
                self._invalidate_links_cache()
                self._notify_link_ops_after_save()
                self._enqueue_post_save_enrichment()
                self._schedule_focus_if_created()
            finally:
                self._in_flight = False

        def _on_error(exc: Exception) -> None:
            try:
                logger.warning("SaveLinkCmd.redo failed: %s", exc)
                _show_links_command_error(
                    self.main,
                    "Save link failed",
                    f"Failed to save link: {exc}",
                )
            finally:
                self._in_flight = False

        _run_links_db_command(
            _task,
            description="save_link_redo",
            on_finished=_on_finished,
            on_error=_on_error,
        )

    def _undo_new_link(self, link_id):
        """Delete newly created link."""
        if hasattr(self.main, "links_business") and self.main.links_business:
            self.main.links_business.links.delete_link(link_id)
        else:
            _links_service_for(self).delete_link(link_id)

    def _undo_update_link(self):
        """Restore old link data."""
        if self.old_data:
            if hasattr(self.main, "links_business") and self.main.links_business:
                self.main.links_business.links.create_or_update_link(self.old_data)
            else:
                _links_service_for(self).create_or_update_link(self.old_data)
            if hasattr(self.main, "links_business") and self.main.links_business:
                try:
                    self.main.links_business.link_updated.emit(self.old_data)
                except Exception as exc:
                    logger.warning(
                        "SaveLinkCmd.undo: link_updated emit failed: %s", exc
                    )

    def _reload_table_for_undo(self):
        """Reload table for corresponding category if not suppressed."""
        try:
            if not getattr(self, "_suppress_ui", False):
                cat_id = (self.old_data or {}).get("category_id") or self.new_data.get(
                    "category_id"
                )
                if isinstance(cat_id, int) and cat_id > 0:
                    _reload_links_via_controller(self.main, {cat_id})
        except Exception as exc:
            logger.warning(
                "SaveLinkCmd.undo: reload failed: %s",
                exc,
            )

    @log_command
    def undo(self):
        if self._in_flight:
            logger.debug("SaveLinkCmd.undo deferred: redo still in flight")
            return
        link_id = self.new_data.get("id")
        if self.old_data is None and link_id:
            self._undo_new_link(link_id)
        else:
            self._undo_update_link()
        self._reload_table_for_undo()
        self._emit_top_panels_refresh()
        self._invalidate_links_cache()


class BatchDeleteLinksCmd(BaseCommand):
    def __init__(self, links_to_delete: list[dict], main_window):
        super().__init__("Batch delete links", main_window)
        self.main = main_window
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
        # Keep the selected link payload as-is to avoid a large synchronous
        # copy on the UI thread before the async batch delete even starts.
        self.links: list[dict] = list(links_to_delete or [])
        self._first_redo = True

    def _emit_top_panels_refresh(self) -> None:
        link_ops = getattr(self.main, "link_operations", None)
        if link_ops is None:
            return
        try:
            link_ops.emit_top_panels_changed(favorites=True, recents=True)
        except Exception:
            logger.debug(
                "BatchDeleteLinksCmd: top panels refresh emit failed",
                exc_info=True,
            )

    def _invalidate_links_cache(self) -> None:
        links_business = getattr(self.main, "links_business", None)
        if links_business is None:
            return
        try:
            if hasattr(links_business, "invalidate_cache"):
                links_business.invalidate_cache()
            elif hasattr(links_business, "_invalidate_cache"):
                links_business._invalidate_cache()
        except Exception:
            logger.debug(
                "BatchDeleteLinksCmd: cache invalidation failed",
                exc_info=True,
            )

    @log_command
    def redo(self):
        ids = [x.get("id") for x in self.links if isinstance(x.get("id"), int)]
        if not ids:
            return

        affected_categories = {
            link.get("category_id")
            for link in self.links
            if isinstance(link.get("category_id"), int) and link.get("category_id") > 0
        }
        links_business = getattr(self.main, "links_business", None)
        skip_initial = (
            getattr(self, "_suppress_ui", False) and getattr(self, "_first_redo", False)
        )
        self._first_redo = False
        def _task() -> int:
            if links_business and hasattr(links_business, "links"):
                return int(links_business.links.batch_delete_links(ids))
            return int(_links_service_for(self).batch_delete_links(ids))

        def _on_finished(_count: int) -> None:
            try:
                if links_business and hasattr(links_business, "items_batch_deleted"):
                    links_business.items_batch_deleted.emit("link", ids)
            except Exception as exc:
                logger.debug(
                    "BatchDeleteLinksCmd.redo: items_batch_deleted emit failed: %s",
                    exc,
                    exc_info=True,
                )
            try:
                if affected_categories:
                    _reload_links_via_controller(self.main, affected_categories)
            except Exception as exc:
                logger.warning(
                    "BatchDeleteLinksCmd.redo: reload failed: %s",
                    exc,
                )
            self._emit_top_panels_refresh()
            self._invalidate_links_cache()

        def _on_error(exc: Exception) -> None:
            logger.warning("BatchDeleteLinksCmd.redo failed: %s", exc)
            _show_links_command_error(
                self.main,
                "Delete links failed",
                f"Batch delete links failed: {exc}",
            )

        _run_links_db_command(
            _task,
            description="batch_delete_links_redo",
            on_finished=_on_finished,
            on_error=_on_error,
        )

    @log_command
    def undo(self):
        links_business = getattr(self.main, "links_business", None)
        affected_categories = {
            link.get("category_id")
            for link in self.links
            if isinstance(link.get("category_id"), int) and link.get("category_id") > 0
        }

        def _task() -> list[int]:
            if links_business and hasattr(links_business, "links"):
                result = links_business.links.batch_create_or_update_links(self.links)
            else:
                result = _links_service_for(self).batch_create_or_update_links(self.links)
            return _validate_batch_link_restore_result(self.links, result)

        def _on_finished(_restored_ids: list[int]) -> None:
            try:
                if links_business and hasattr(links_business, "batch_updated"):
                    links_business.batch_updated.emit(True)
            except Exception as exc:
                logger.debug(
                    "BatchDeleteLinksCmd.undo: batch_updated emit failed: %s",
                    exc,
                    exc_info=True,
                )
            try:
                if affected_categories:
                    _reload_links_via_controller(self.main, affected_categories)
            except Exception as exc:
                logger.warning(
                    "BatchDeleteLinksCmd.undo: reload failed: %s",
                    exc,
                )
            self._emit_top_panels_refresh()
            self._invalidate_links_cache()

        def _on_error(exc: Exception) -> None:
            logger.warning("BatchDeleteLinksCmd.undo failed: %s", exc)
            _show_links_command_error(
                self.main,
                "Undo delete links failed",
                f"Batch restore links failed: {exc}",
            )

        _run_links_db_command(
            _task,
            description="batch_delete_links_undo",
            on_finished=_on_finished,
            on_error=_on_error,
        )


class DeleteLinkCmd(BaseCommand):
    def __init__(self, link_to_delete: dict, main_window):
        super().__init__("Delete link", main_window)
        self.main = main_window
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
        self.link = dict(link_to_delete) if link_to_delete else {}
        self._first_redo = True

    def _emit_top_panels_refresh(self) -> None:
        link_ops = getattr(self.main, "link_operations", None)
        if link_ops is None:
            return
        try:
            link_ops.emit_top_panels_changed(favorites=True, recents=True)
        except Exception:
            logger.debug(
                "DeleteLinkCmd: top panels refresh emit failed",
                exc_info=True,
            )

    def _invalidate_links_cache(self) -> None:
        links_business = getattr(self.main, "links_business", None)
        if links_business is None:
            return
        try:
            if hasattr(links_business, "invalidate_cache"):
                links_business.invalidate_cache()
            elif hasattr(links_business, "_invalidate_cache"):
                links_business._invalidate_cache()
        except Exception:
            logger.debug(
                "DeleteLinkCmd: cache invalidation failed",
                exc_info=True,
            )

    @log_command
    def redo(self):
        link_id = self.link.get("id")
        if link_id:
            # Delete via service layer if available
            links_business = getattr(self.main, "links_business", None)
            if links_business and hasattr(links_business, "links"):
                links_business.links.delete_link(link_id)
            else:
                # Fallback via service layer
                _links_service_for(self).delete_link(link_id)
            
            # Emit link_deleted signal
            try:
                if links_business and hasattr(links_business, "link_deleted"):
                    links_business.link_deleted.emit(link_id)
            except Exception as exc:
                logger.debug(
                    "DeleteLinkCmd.redo: link_deleted emit failed: %s",
                    exc,
                    exc_info=True,
                )
        
        skip_initial = (
            getattr(self, "_suppress_ui", False) and getattr(self, "_first_redo", False)
        )
        self._first_redo = False

        # After deletion, reload table for category (skip only on initial push if suppressed)
        try:
            if not skip_initial:
                cat_id = self.link.get("category_id")
                if isinstance(cat_id, int) and cat_id > 0:
                    _reload_links_via_controller(self.main, {cat_id})
        except Exception as exc:
            logger.warning(
                "DeleteLinkCmd.redo: reload failed: %s",
                exc,
            )
        self._emit_top_panels_refresh()
        self._invalidate_links_cache()

    @log_command
    def undo(self):
        # Restore deleted link
        if hasattr(self.main, "links_business") and self.main.links_business:
            self.main.links_business.links.create_or_update_link(self.link)
        else:
            # Fallback via service layer
            _links_service_for(self).create_or_update_link(self.link)
        if hasattr(self.main, "links_business") and self.main.links_business:
            try:
                self.main.links_business.link_updated.emit(self.link)
            except Exception as exc:
                logger.warning("DeleteLinkCmd.undo: link_updated emit failed: %s", exc)
        # Reload table after undo (ignore suppression for Undo)
        try:
            cat_id = self.link.get("category_id")
            if isinstance(cat_id, int) and cat_id > 0:
                _reload_links_via_controller(self.main, {cat_id})
        except Exception as exc:
            logger.warning(
                "DeleteLinkCmd.undo: reload failed: %s",
                exc,
            )
        self._emit_top_panels_refresh()
        self._invalidate_links_cache()


class BatchSaveLinksCmd(BaseCommand):
    def __init__(
        self, links_data: list[dict], _old_link_data: dict | None, main_window
    ):
        super().__init__("Batch save links", main_window)
        self.main = main_window
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
        self.links_data = [dict(x) for x in (links_data or [])]
        self.created_ids: list[int] = []

    def _emit_top_panels_refresh(self) -> None:
        link_ops = getattr(self.main, "link_operations", None)
        if link_ops is None:
            return
        try:
            link_ops.emit_top_panels_changed(favorites=True, recents=True)
        except Exception:
            logger.debug(
                "BatchSaveLinksCmd: top panels refresh emit failed",
                exc_info=True,
            )

    def _invalidate_links_cache(self) -> None:
        links_business = getattr(self.main, "links_business", None)
        if links_business is None:
            return
        try:
            if hasattr(links_business, "invalidate_cache"):
                links_business.invalidate_cache()
            elif hasattr(links_business, "_invalidate_cache"):
                links_business._invalidate_cache()
        except Exception:
            logger.debug(
                "BatchSaveLinksCmd: cache invalidation failed",
                exc_info=True,
            )

    def _enqueue_post_save_enrichment(self) -> None:
        if not self.links_data:
            return
        try:
            for index, link in enumerate(self.links_data):
                link_id = self.created_ids[index] if index < len(self.created_ids) else None
                payload = _apply_created_id_to_link(link, link_id)
                if not _should_enqueue_link_enrichment(payload):
                    continue
                _enqueue_link_enrichment(self.main, payload)
        except Exception:
            logger.debug(
                "BatchSaveLinksCmd: failed to enqueue post-save enrichment",
                exc_info=True,
            )

    @log_command
    def redo(self):
        self.created_ids.clear()
        affected_categories, missing_category = _ensure_link_category_ids(
            self.main, self.links_data
        )
        if missing_category:
            logger.warning("BatchSaveLinksCmd.redo skipped: missing category_id")
            self.set_obsolete(True)
            _show_links_command_error(
                self.main,
                "Save links failed",
                "Cannot save links because no category is selected.",
            )
            return
        
        # Выполняем пакетный upsert в одной транзакции через сервисный слой
        links_business = getattr(self.main, "links_business", None)
        if links_business and hasattr(links_business, "links"):
            created = links_business.links.batch_create_or_update_links(
                self.links_data
            )
        else:
            created = _links_service_for(self).batch_create_or_update_links(
                self.links_data
            )
        self.created_ids.extend(created or [])
        
        # Emit batch update signal
        try:
            if links_business and hasattr(links_business, "batch_updated"):
                links_business.batch_updated.emit(True)
        except Exception as exc:
            logger.debug(
                "BatchSaveLinksCmd.redo: batch_updated emit failed: %s",
                exc,
                exc_info=True,
            )
        
        # Reload UI for all affected categories if not suppressed
        try:
            if not getattr(self, "_suppress_ui", False) and affected_categories:
                _reload_links_via_controller(self.main, affected_categories)
        except Exception as exc:
            logger.warning(
                "BatchSaveLinksCmd.redo: reload failed: %s",
                exc,
            )
        self._emit_top_panels_refresh()
        self._invalidate_links_cache()
        self._enqueue_post_save_enrichment()

    @log_command
    def undo(self):
        # Collect all affected categories before deletion
        affected_categories = {
            link.get("category_id")
            for link in self.links_data
            if isinstance(link.get("category_id"), int) and link.get("category_id") > 0
        }
        
        # Удаляем созданные записи одним батчем
        ids = [lid for lid in self.created_ids if isinstance(lid, int) and lid > 0]
        if ids:
            links_business = getattr(self.main, "links_business", None)
            if links_business and hasattr(links_business, "links"):
                links_business.links.batch_delete_links(ids)
            else:
                _links_service_for(self).batch_delete_links(ids)
            
            # Emit batch deletion signal
            try:
                if links_business and hasattr(links_business, "items_batch_deleted"):
                    links_business.items_batch_deleted.emit("link", ids)
            except Exception as exc:
                logger.debug(
                    "BatchSaveLinksCmd.undo: items_batch_deleted emit failed: %s",
                    exc,
                    exc_info=True,
                )
        
        # Reload UI for all affected categories
        try:
            if affected_categories:
                _reload_links_via_controller(self.main, affected_categories)
        except Exception as exc:
            logger.warning(
                "BatchSaveLinksCmd.undo: reload failed: %s",
                exc,
            )
        self._emit_top_panels_refresh()
        self._invalidate_links_cache()
