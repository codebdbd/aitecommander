# app/utils/system/undo/commands_links.py
from __future__ import annotations

import logging

from app.controllers.ui.undo.base import BaseCommand, log_command
from app.services import LinksService

logger = logging.getLogger(__name__)


class SaveLinkCmd(BaseCommand):
    def __init__(self, new_data: dict, old_data: dict | None, main_window):
        super().__init__("Save link", main_window)
        self.main = main_window
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
        self.new_data = dict(new_data) if new_data else {}
        self.old_data = dict(old_data) if old_data else None
        self.created_id: int | None = None

    @log_command
    def redo(self):
        # Fill missing fields from old_data if dialog returned partial payload
        try:
            if self.old_data:
                # Key fields required for correct update
                for k in (
                    "id",
                    "category_id",
                    "position",
                    "favorite",
                ):
                    if k not in self.new_data and k in self.old_data:
                        self.new_data[k] = self.old_data[k]
                # Base fields that may be unchanged and absent in new_data
                for k in ("name", "url", "args", "icon_path"):
                    if k not in self.new_data and k in self.old_data:
                        self.new_data[k] = self.old_data[k]
        except Exception as exc:
            logger.exception("SaveLinkCmd.redo: failed to merge old/new data: %s", exc)

        # Save link via service layer (UnitOfWork inside)
        if hasattr(self.main, "links_business") and self.main.links_business:
            result = self.main.links_business.links.create_or_update_link(self.new_data)
        else:
            # Fallback via service layer
            result = LinksService(self.db).create_or_update_link(self.new_data)
        if result and not self.new_data.get("id"):
            self.new_data["id"] = result
            self.created_id = result
        # UI update signal via LinksBusinessLogic, if available
        if hasattr(self.main, "links_business") and self.main.links_business:
            try:
                self.main.links_business.link_updated.emit(self.new_data)
            except Exception as exc:
                logger.warning("SaveLinkCmd.redo: link_updated emit failed: %s", exc)
            # Reload table for current category if not suppressed
            try:
                if not getattr(self, "_suppress_ui", False):
                    cat_id = self.new_data.get("category_id") or (
                        self.old_data or {}
                    ).get("category_id")
                    if isinstance(cat_id, int) and cat_id > 0:
                        ctrl = getattr(self.main, "links_table_controller", None)
                        if ctrl:
                            ctrl.reload(cat_id)
                        else:
                            # Fallback without direct UI: load data via business layer
                            links_business = getattr(self.main, "links_business", None)
                            if links_business:
                                try:
                                    links_business.load_links(cat_id)
                                except Exception as exc:
                                    logger.debug(
                                        "SaveLinkCmd.redo: links_business.load_links(%s) failed: %s",
                                        cat_id,
                                        exc,
                                        exc_info=True,
                                    )
            except Exception as exc:
                logger.warning(
                    "SaveLinkCmd.redo: reload failed: %s",
                    exc,
                )

    @log_command
    def undo(self):
        # If newly created — delete
        link_id = self.new_data.get("id")
        if self.old_data is None and link_id:
            if hasattr(self.main, "links_business") and self.main.links_business:
                self.main.links_business.links.delete_link(link_id)
            else:
                LinksService(self.db).delete_link(link_id)
        else:
            # Otherwise restore old data
            if self.old_data:
                if hasattr(self.main, "links_business") and self.main.links_business:
                    self.main.links_business.links.create_or_update_link(self.old_data)
                else:
                    LinksService(self.db).create_or_update_link(self.old_data)
                if hasattr(self.main, "links_business") and self.main.links_business:
                    try:
                        self.main.links_business.link_updated.emit(self.old_data)
                    except Exception as exc:
                        logger.warning(
                            "SaveLinkCmd.undo: link_updated emit failed: %s", exc
                        )
        # Reload table for corresponding category if not suppressed
        try:
            if not getattr(self, "_suppress_ui", False):
                cat_id = (self.old_data or {}).get("category_id") or self.new_data.get(
                    "category_id"
                )
                if isinstance(cat_id, int) and cat_id > 0:
                    ctrl = getattr(self.main, "links_table_controller", None)
                    if ctrl:
                        ctrl.reload(cat_id)
                    else:
                        links_business = getattr(self.main, "links_business", None)
                        if links_business:
                            try:
                                links_business.load_links(cat_id)
                            except Exception as exc:
                                logger.debug(
                                    "SaveLinkCmd.undo: links_business.load_links(%s) failed: %s",
                                    cat_id,
                                    exc,
                                    exc_info=True,
                                )
        except Exception as exc:
            logger.warning(
                "SaveLinkCmd.undo: reload failed: %s",
                exc,
            )


class BatchDeleteLinksCmd(BaseCommand):
    def __init__(self, links_to_delete: list[dict], main_window):
        super().__init__("Batch delete links", main_window)
        self.main = main_window
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
        # Store full data for potential restore
        self.links: list[dict] = [dict(x) for x in (links_to_delete or [])]

    @log_command
    def redo(self):
        ids = [x.get("id") for x in self.links if isinstance(x.get("id"), int)]
        if not ids:
            return
        links_business = getattr(self.main, "links_business", None)
        if links_business and hasattr(links_business, "links"):
            try:
                links_business.links.batch_delete_links(ids)
            except Exception as exc:
                logger.warning(
                    "BatchDeleteLinksCmd.redo: links_business batch_delete failed, fallback to service: %s",
                    exc,
                )
                LinksService(self.db).batch_delete_links(ids)
        else:
            LinksService(self.db).batch_delete_links(ids)
        # Single table reload if not suppressed
        try:
            if not getattr(self, "_suppress_ui", False):
                cat_id = (self.links[0] if self.links else {}).get("category_id")
                if isinstance(cat_id, int) and cat_id > 0:
                    ctrl = getattr(self.main, "links_table_controller", None)
                    if ctrl:
                        ctrl.reload(cat_id)
                    else:
                        links_business = getattr(self.main, "links_business", None)
                        if links_business:
                            try:
                                links_business.load_links(cat_id)
                            except Exception:
                                pass
        except Exception as exc:
            logger.warning(
                "BatchDeleteLinksCmd.redo: reload failed: %s",
                exc,
            )

    @log_command
    def undo(self):
        # Restore all deleted records (batch upsert)
        links_business = getattr(self.main, "links_business", None)
        try:
            if links_business and hasattr(links_business, "links"):
                links_business.links.batch_create_or_update_links(self.links)
            else:
                LinksService(self.db).batch_create_or_update_links(self.links)
        except Exception as exc:
            # Fallback: per-link
            logger.warning(
                "BatchDeleteLinksCmd.undo: batch upsert failed, fallback to single: %s",
                exc,
            )
            for link in self.links:
                try:
                    if links_business and hasattr(links_business, "links"):
                        links_business.links.create_or_update_link(link)
                    else:
                        LinksService(self.db).create_or_update_link(link)
                except Exception as inner_exc:
                    # continue attempts for the rest
                    logger.debug(
                        "BatchDeleteLinksCmd.undo: per-link upsert failed for id=%s: %s",
                        link.get("id"),
                        inner_exc,
                        exc_info=True,
                    )
        # UI update after restore (ignore suppression for Undo)
        try:
            cat_id = (self.links[0] if self.links else {}).get("category_id")
            if isinstance(cat_id, int) and cat_id > 0:
                ctrl = getattr(self.main, "links_table_controller", None)
                if ctrl:
                    ctrl.reload(cat_id)
                else:
                    links_business = getattr(self.main, "links_business", None)
                    if links_business:
                        try:
                            links_business.load_links(cat_id)
                        except Exception:
                            pass
        except Exception as exc:
            logger.warning(
                "BatchDeleteLinksCmd.undo: reload failed: %s",
                exc,
            )


class DeleteLinkCmd(BaseCommand):
    def __init__(self, link_to_delete: dict, main_window):
        super().__init__("Delete link", main_window)
        self.main = main_window
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
        self.link = dict(link_to_delete) if link_to_delete else {}

    @log_command
    def redo(self):
        link_id = self.link.get("id")
        if link_id:
            # Delete via service layer if available
            if hasattr(self.main, "links_business") and self.main.links_business:
                self.main.links_business.links.delete_link(link_id)
            else:
                # Fallback via service layer
                LinksService(self.db).delete_link(link_id)
        # After deletion, reload table for category if not suppressed
        try:
            if not getattr(self, "_suppress_ui", False):
                cat_id = self.link.get("category_id")
                if isinstance(cat_id, int) and cat_id > 0:
                    ctrl = getattr(self.main, "links_table_controller", None)
                    if ctrl:
                        ctrl.reload(cat_id)
                    else:
                        links_business = getattr(self.main, "links_business", None)
                        if links_business:
                            try:
                                links_business.load_links(cat_id)
                            except Exception:
                                pass
        except Exception as exc:
            logger.warning(
                "DeleteLinkCmd.redo: reload failed: %s",
                exc,
            )

    @log_command
    def undo(self):
        # Restore deleted link
        if hasattr(self.main, "links_business") and self.main.links_business:
            self.main.links_business.links.create_or_update_link(self.link)
        else:
            # Fallback via service layer
            LinksService(self.db).create_or_update_link(self.link)
        if hasattr(self.main, "links_business") and self.main.links_business:
            try:
                self.main.links_business.link_updated.emit(self.link)
            except Exception as exc:
                logger.warning("DeleteLinkCmd.undo: link_updated emit failed: %s", exc)
            # Reload table after undo (ignore suppression for Undo)
            try:
                cat_id = self.link.get("category_id")
                if isinstance(cat_id, int) and cat_id > 0:
                    ctrl = getattr(self.main, "links_table_controller", None)
                    if ctrl:
                        ctrl.reload(cat_id)
                    else:
                        links_business = getattr(self.main, "links_business", None)
                        if links_business:
                            try:
                                links_business.load_links(cat_id)
                            except Exception:
                                pass
            except Exception as exc:
                logger.warning(
                    "DeleteLinkCmd.undo: reload failed: %s",
                    exc,
                )


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

    @log_command
    def redo(self):
        self.created_ids.clear()
        # Выполняем пакетный upsert в одной транзакции через сервисный слой
        if hasattr(self.main, "links_business") and self.main.links_business:
            created = self.main.links_business.links.batch_create_or_update_links(
                self.links_data
            )
        else:
            created = LinksService(self.db).batch_create_or_update_links(
                self.links_data
            )
        self.created_ids.extend(created or [])
        # Разовая перезагрузка таблицы по категории первой ссылки, если не подавлено
        try:
            if not getattr(self, "_suppress_ui", False):
                cat_id = (self.links_data[0] if self.links_data else {}).get(
                    "category_id"
                )
                if isinstance(cat_id, int) and cat_id > 0:
                    ctrl = getattr(self.main, "links_table_controller", None)
                    if ctrl:
                        ctrl.reload(cat_id)
                    else:
                        ui_state = getattr(self.main, "ui_state", None)
                        if ui_state:
                            ui_state.load_category(cat_id, source="undo/redo")
        except Exception as exc:
            logger.warning(
                "BatchSaveLinksCmd.redo: reload failed: %s",
                exc,
            )

    @log_command
    def undo(self):
        # Удаляем созданные записи одним батчем
        ids = [lid for lid in self.created_ids if isinstance(lid, int) and lid > 0]
        if ids:
            LinksService(self.db).batch_delete_links(ids)
        # Перезагрузить таблицу, если не подавлено
        try:
            if not getattr(self, "_suppress_ui", False):
                cat_id = (self.links_data[0] if self.links_data else {}).get(
                    "category_id"
                )
                if isinstance(cat_id, int) and cat_id > 0:
                    ctrl = getattr(self.main, "links_table_controller", None)
                    if ctrl:
                        ctrl.reload(cat_id)
                    else:
                        links_business = getattr(self.main, "links_business", None)
                        if links_business:
                            try:
                                links_business.load_links(cat_id)
                            except Exception:
                                pass
        except Exception as exc:
            logger.warning(
                "BatchSaveLinksCmd.undo: reload failed: %s",
                exc,
            )
