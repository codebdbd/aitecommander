# app/utils/system/undo/commands_structure.py
from __future__ import annotations

import logging

from app.controllers.ui.undo.base import BaseCommand, log_command
from app.services.structure_service import StructureService
from app.utils.ui.icon.cache_manager import clear_icon_cache

logger = logging.getLogger(__name__)


class SaveSectionCmd(BaseCommand):
    """Save (create/edit) section.
    Thin wrapper over DB with business-layer signal emission for UI.
    """

    def __init__(self, new_data: dict, old_data: dict | None, main_window):
        super().__init__("Save section", main_window)
        self.main = main_window
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
        self.structure_service = StructureService(self.db)
        self.new_data = dict(new_data) if new_data else {}
        self.old_data = dict(old_data) if old_data else None
        self.is_new = not bool(self.new_data.get("id"))
        self.new_id = self.new_data.get("id")

    def _emit_reload(self):
        try:
            business = getattr(self.main, "structure_business", None)
            if business:
                if self.is_new:
                    business.item_added.emit("section", self.new_id, self.new_data)
                else:
                    business.item_updated.emit("section", self.new_id, self.new_data)
                # Full reload is no longer required — model will update via signals
        except Exception as exc:
            logger.warning(
                "SaveSectionCmd._emit_reload: failed to emit update signals: %s",
                exc,
                exc_info=True,
            )

    @log_command
    def redo(self):
        # Global delete guard during sensitive operations (e.g., insert)
        try:
            if getattr(self.main, "_suppress_deletes", False):
                logger.debug(
                    "[DeleteGuard] DeleteSectionCmd.redo suppressed by _suppress_deletes flag"
                )
                return
        except Exception as exc:
            logger.debug("SaveSectionCmd.redo: delete guard check failed: %s", exc)
        if self.is_new:
            result = self.structure_service.create_section(self.new_data)
            if result:
                self.new_id = result
                self.new_data["id"] = result
        else:
            # update returns bool; ID is already known
            self.structure_service.update_section(
                self.new_data.get("id"), self.new_data
            )
            self.new_id = self.new_data.get("id")
        # Set focus to section via business logic
        try:
            business = getattr(self.main, "structure_business", None)
            if business:
                business.section_selected.emit(self.new_id)
        except Exception as exc:
            logger.warning("SaveCategoryCmd.redo: select_category failed: %s", exc)
        self._emit_reload()

    @log_command
    def undo(self):
        if self.is_new:
            # Cancel creation — delete section
            try:
                self.structure_service.delete_section(self.new_id)
            finally:
                try:
                    business = getattr(self.main, "structure_business", None)
                    if business:
                        business.item_deleted.emit("section", self.new_id)
                        # Incremental update — without full reload
                except Exception as exc:
                    logger.warning(
                        "SaveSectionCmd.undo: item_deleted emit failed: %s", exc
                    )
        else:
            # Rollback edit — restore previous data
            if self.old_data:
                self.structure_service.update_section(
                    self.old_data["id"], self.old_data
                )
                try:
                    business = getattr(self.main, "structure_business", None)
                    if business:
                        business.section_selected.emit(self.old_data["id"])
                except Exception as exc:
                    logger.warning(
                        "SaveSectionCmd.undo: select_section failed: %s", exc
                    )
                try:
                    business = getattr(self.main, "structure_business", None)
                    if business:
                        business.item_updated.emit(
                            "section", self.old_data["id"], self.old_data
                        )
                        # Incremental update — without full reload
                except Exception as exc:
                    logger.warning(
                        "SaveSectionCmd.undo: item_updated emit failed: %s", exc
                    )


class DeleteSectionCmd(BaseCommand):
    """Delete section with full restore support (section+categories+links)."""

    def __init__(self, section_data: dict, main_window):
        super().__init__("Delete section", main_window)
        self.main = main_window
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
        self.structure_service = StructureService(self.db)
        self.section = dict(section_data) if section_data else {}
        # Backup full section tree
        self._backup_tree = self.structure_service.export_section_tree(
            self.section.get("id")
        )

    def redo(self):
        section_id = self.section.get("id")
        if section_id is None:
            return
        self.structure_service.delete_section(section_id)
        try:
            business = getattr(self.main, "structure_business", None)
            if business:
                business.item_deleted.emit("section", section_id)
                # Incremental update — without full reload
        except Exception as exc:
            logger.debug(
                "DeleteSectionCmd.redo: item_deleted emit failed: %s",
                exc,
                exc_info=True,
            )

    def undo(self):
        try:
            self.structure_service.import_section_tree(self._backup_tree)
            section_id = self._backup_tree["section"]["id"]
            # If restored categories exist — select the first one
            try:
                categories = self._backup_tree.get("categories") or []
                first_cat = None
                for item in categories:
                    cat = (item or {}).get("category") or {}
                    if cat.get("id") is not None:
                        first_cat = cat
                        break
                if first_cat is not None:
                    cat_id = first_cat.get("id")
                    try:
                        business = getattr(self.main, "structure_business", None)
                        if business:
                            business.select_category(cat_id)
                    except Exception as exc:
                        logger.debug(
                            "DeleteSectionCmd.undo: select_category failed: %s",
                            exc,
                            exc_info=True,
                        )
            except Exception as exc:
                logger.warning(
                    "DeleteSectionCmd.undo: categories handling failed: %s", exc
                )
            try:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.section_selected.emit(section_id)
            except Exception as exc:
                logger.warning("DeleteSectionCmd.undo: select_section failed: %s", exc)
            try:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.item_added.emit(
                        "section", section_id, self._backup_tree["section"]
                    )
                    # Incremental update — without full reload
            except Exception as exc:
                logger.debug(
                    "DeleteSectionCmd.undo: item_added emit failed: %s",
                    exc,
                    exc_info=True,
                )
            # Full structure reload not required: necessary signals were emitted above
        except Exception as exc:
            # On restore failure — leave as is without raising in UI
            logger.exception("DeleteSectionCmd.undo: restore failed: %s", exc)


class SaveCategoryCmd(BaseCommand):
    """Save (create/edit) category."""

    def __init__(
        self,
        new_data: dict,
        old_data: dict | None,
        main_window,
        *,
        skip_reload: bool = False,
    ):
        super().__init__("Save category", main_window)
        self.main = main_window
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
        self.structure_service = StructureService(self.db)
        self.new_data = dict(new_data) if new_data else {}
        self.old_data = dict(old_data) if old_data else None
        self.is_new = not bool(self.new_data.get("id"))
        self.new_id = self.new_data.get("id")
        self.skip_reload = skip_reload

    def _emit_reload(self):
        if self.skip_reload:
            return
        try:
            business = getattr(self.main, "structure_business", None)
            if business:
                # Category icons might have changed — clear cache so tiles redraw actual icons
                try:
                    clear_icon_cache()
                except Exception as exc:
                    logger.warning(
                        "SaveCategoryCmd._emit_reload: clear_icon_cache failed: %s", exc
                    )
                if self.is_new:
                    # For categories, second argument is parent_id (section_id)
                    parent_id = self.new_data.get("section_id")
                    business.item_added.emit("category", parent_id, self.new_data)
                else:
                    business.item_updated.emit("category", self.new_id, self.new_data)
                # Full reload is no longer required — model will update via signals
        except Exception as exc:
            logger.warning("SaveCategoryCmd._emit_reload: emit failed: %s", exc)

    @log_command
    def redo(self):
        if self.is_new:
            result = self.structure_service.create_category(self.new_data)
            if result:
                self.new_id = result
                self.new_data["id"] = result
        else:
            # Dialog may return a partial payload. For correct update
            # ensure presence of required fields.
            try:
                if self.old_data:
                    for k in ("id", "section_id", "position", "icon_path"):
                        if k not in self.new_data and k in self.old_data:
                            self.new_data[k] = self.old_data[k]
                    # Fill in name if dialog didn't return it
                    if "name" not in self.new_data and "name" in self.old_data:
                        self.new_data["name"] = self.old_data["name"]
            except Exception as exc:
                logger.debug(
                    "SaveCategoryCmd.redo: payload normalization failed: %s",
                    exc,
                    exc_info=True,
                )
            self.structure_service.update_category(
                self.new_data.get("id"), self.new_data
            )
            self.new_id = self.new_data.get("id")
        try:
            if not self.skip_reload:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.select_category(self.new_id)
        except Exception as exc:
            logger.warning("SaveCategoryCmd.redo: select_category failed: %s", exc)
        self._emit_reload()

    def _undo_new_category(self, section_id):
        """Undo creation of new category."""
        if self.new_id:
            self.structure_service.delete_category(self.new_id)
        try:
            if not self.skip_reload:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.section_selected.emit(section_id)
        except Exception as exc:
            logger.warning("SaveCategoryCmd.undo: select_section failed: %s", exc)
        try:
            business = getattr(self.main, "structure_business", None)
            if business:
                business.item_deleted.emit("category", self.new_id)
        except Exception as exc:
            logger.warning(
                "SaveCategoryCmd.undo: item_deleted emit failed: %s", exc
            )

    def _undo_update_category(self):
        """Undo update of existing category."""
        if not self.old_data:
            return
        self.structure_service.update_category(
            self.old_data["id"], self.old_data
        )
        try:
            if not self.skip_reload:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.select_category(self.old_data["id"])
        except Exception as exc:
            logger.warning(
                "SaveCategoryCmd.undo: select_category failed: %s", exc
            )
        try:
            business = getattr(self.main, "structure_business", None)
            if business:
                business.item_updated.emit(
                    "category", self.old_data["id"], self.old_data
                )
        except Exception as exc:
            logger.warning(
                "SaveCategoryCmd.undo: item_updated emit failed: %s", exc
            )

    @log_command
    def undo(self):
        if self.is_new:
            section_id = self.new_data.get("section_id")
            self._undo_new_category(section_id)
        else:
            self._undo_update_category()


class DeleteCategoryCmd(BaseCommand):
    """Delete category with subtree restore (category+links)."""

    def __init__(
        self,
        category_data: dict,
        main_window,
        *,
        skip_reload: bool = False,
        lightweight_reload: bool = False,
    ):
        super().__init__("Delete category", main_window)
        self.main = main_window
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
        self.structure_service = StructureService(self.db)
        self.category = dict(category_data) if category_data else {}
        self.skip_reload = bool(skip_reload)
        self.lightweight_reload = bool(lightweight_reload)
        # Backup of category subtree
        self._backup_tree = self.structure_service.export_category_tree(
            self.category.get("id")
        )

    def _handle_skip_reload(self, business, category_id):
        """Handle deletion with skip_reload mode."""
        try:
            if business:
                business.item_deleted.emit("category", category_id)
        except Exception as exc:
            logger.warning(
                "DeleteCategoryCmd.redo(skip_reload): item_deleted emit failed: %s",
                exc,
            )

    def _handle_lightweight_reload(self, business, section_id, category_id):
        """Handle deletion with lightweight_reload mode."""
        try:
            if business:
                business.section_selected.emit(section_id)
        except Exception as exc:
            logger.warning(
                "DeleteCategoryCmd.redo(lightweight): select_section failed: %s",
                exc,
            )
        try:
            if business:
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

    def _handle_regular_reload(self, business, section_id, category_id):
        """Handle deletion with regular reload mode."""
        try:
            if business:
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

    @log_command
    def redo(self):
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
        category_id = self.category.get("id")
        if category_id is None:
            return
        self.structure_service.delete_category(category_id)
        section_id = self.category.get("section_id")
        business = getattr(self.main, "structure_business", None)

        if self.skip_reload:
            self._handle_skip_reload(business, category_id)
        elif self.lightweight_reload:
            self._handle_lightweight_reload(business, section_id, category_id)
        else:
            self._handle_regular_reload(business, section_id, category_id)

    @log_command
    def undo(self):
        try:
            self.structure_service.import_category_tree(self._backup_tree)
            category_id = self.category.get("id")
            # After restore select category via business logic (UI updates via subscribers)
            try:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.select_category(category_id)
            except Exception:
                pass
            try:
                business = getattr(self.main, "structure_business", None)
                if business:
                    # After restore clear cache to update restored category icons
                    try:
                        clear_icon_cache()
                    except Exception:
                        pass
                    # Set '__from_undo__' flag in payload so UI doesn't switch focus
                    cat_payload = dict(self._backup_tree.get("category") or {})
                    try:
                        cat_payload["__from_undo__"] = True
                    except Exception:
                        pass
                    business.item_added.emit(
                        "category",
                        self.category.get("section_id"),
                        cat_payload,
                    )
                    # Incremental update — without full reload
            except Exception:
                pass
            # Full structure reload not required: point signals and selections done above
        except Exception as exc:
            # On restore failure — leave as is
            logger.exception("DeleteCategoryCmd.undo: restore failed: %s", exc)


class DeleteCategoriesBatchCmd(BaseCommand):
    """Batch delete multiple categories in one operation.

    - Deletes categories by list of IDs via service in one transaction without intermediate UI reloads
    - Does not emit per-item deletion events; performs a single final UI/tiles refresh
    - Supports undo by restoring saved subtree backups
    """

    def __init__(self, categories_data: list[dict], main_window):
        super().__init__("Delete categories (batch)", main_window)
        self.main = main_window
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
        self.structure_service = StructureService(self.db)
        # Save flat list of category data and their backups for undo
        self.categories = [dict(c) for c in (categories_data or [])]
        self._backups = []
        for cat in self.categories:
            try:
                backup = self.structure_service.export_category_tree(cat.get("id"))
            except Exception as exc:
                logger.warning(
                    "DeleteCategoriesBatchCmd.__init__: export backup failed: %s", exc
                )
                backup = None
            self._backups.append(backup)

    def _suppress_ui_signals(self):
        """Suppress selection and tree signals during batch operations."""
        struct = getattr(self.main, "structure", None)
        tree = getattr(struct, "tree", None)
        selection = getattr(struct, "selection_handler", None)
        if selection is not None:
            try:
                selection.begin_suppress_selection()
            except Exception as exc:
                logger.debug(
                    "DeleteCategoriesBatchCmd: begin_suppress_selection failed: %s",
                    exc,
                    exc_info=True,
                )
        if tree is not None:
            tree.blockSignals(True)
        return tree, selection

    def _restore_ui_signals(self, tree, selection):
        """Restore selection and tree signals after batch operations."""
        if tree is not None:
            try:
                tree.blockSignals(False)
            except Exception:
                pass
        if selection is not None:
            try:
                selection.end_suppress_selection()
            except Exception:
                pass

    def _perform_batch_delete(self, business, ids, touched_sections):
        """Perform batch delete operation."""
        batch_started = False
        if (
            business
            and hasattr(business, "begin_batch")
            and callable(business.begin_batch)
        ):
            try:
                business.begin_batch()
                batch_started = True
                if touched_sections:
                    business.event_service.replace_touched_sections(
                        set(touched_sections)
                    )
            except Exception as exc:
                logger.debug(
                    "DeleteCategoriesBatchCmd.redo: begin_batch failed: %s",
                    exc,
                    exc_info=True,
                )
        try:
            self.structure_service.delete_categories_bulk(ids)
            logger.debug(
                "[BatchRedo:deleted] cmd_id=%s bulk_ok ids=%s",
                hex(id(self)),
                len(ids),
            )
        except Exception:
            # If bulk failed, try per-item as fallback
            for cid in ids:
                try:
                    self.structure_service.delete_category(cid)
                except Exception as exc2:
                    logger.warning(
                        "DeleteCategoriesBatchCmd.redo: delete_category failed for %s: %s",
                        cid,
                        exc2,
                    )
        return batch_started

    def _finalize_batch_delete(self, business, batch_started, section_id_for_focus):
        """Finalize batch delete with UI updates."""
        if batch_started:
            try:
                business.end_batch()
            except Exception:
                pass
        try:
            clear_icon_cache()
        except Exception:
            pass
        try:
            if section_id_for_focus is not None and business:
                business.section_selected.emit(section_id_for_focus)
        except Exception as exc:
            logger.debug(
                "DeleteCategoriesBatchCmd.redo: select_section failed: %s",
                exc,
                exc_info=True,
            )
        try:
            if business:
                business._schedule_structure_reload(0)
                logger.debug(
                    "[BatchRedo:reload] cmd_id=%s section_focus=%s",
                    hex(id(self)),
                    section_id_for_focus,
                )
        except Exception as exc:
            logger.debug(
                "DeleteCategoriesBatchCmd.redo: schedule reload failed: %s",
                exc,
                exc_info=True,
            )

    @log_command
    def redo(self):
        try:
            if getattr(self.main, "_suppress_deletes", False):
                logger.debug(
                    "[DeleteGuard] DeleteCategoriesBatchCmd.redo suppressed by _suppress_deletes flag"
                )
                return
        except Exception:
            pass
        business = getattr(self.main, "structure_business", None)
        section_id_for_focus = None
        try:
            ids_dbg = [c.get("id") for c in self.categories if c.get("id") is not None]
            logger.debug(
                "[BatchRedo:start] cmd_id=%s items=%s", hex(id(self)), len(ids_dbg)
            )
        except Exception as exc:
            logger.debug(
                "DeleteCategoriesBatchCmd.redo: start logging failed: %s",
                exc,
                exc_info=True,
            )
        tree, selection = self._suppress_ui_signals()
        try:
            ids = [c.get("id") for c in self.categories if c.get("id") is not None]
            touched_sections = {
                int(cat.get("section_id"))
                for cat in self.categories
                if isinstance(cat.get("section_id"), int) and cat.get("section_id") > 0
            }
            for cat in self.categories:
                sid = cat.get("section_id")
                if sid is not None:
                    section_id_for_focus = sid
            batch_started = self._perform_batch_delete(business, ids, touched_sections)
        finally:
            self._restore_ui_signals(tree, selection)
        self._finalize_batch_delete(business, batch_started, section_id_for_focus)
        logger.debug(
            "[BatchRedo:done] cmd_id=%s section_focus=%s",
            hex(id(self)),
            section_id_for_focus,
        )

    def _restore_backups(self):
        """Restore categories from backups."""
        try:
            self.structure_service.import_category_trees_bulk(self._backups)
            logger.debug(
                "[BatchUndo:imported] cmd_id=%s backups=%s",
                hex(id(self)),
                len(self._backups),
            )
        except Exception as exc:
            logger.warning(
                "DeleteCategoriesBatchCmd.undo: import bulk failed: %s", exc
            )

    def _determine_focus_section(self):
        """Determine section for final focus from backups."""
        for backup in self._backups:
            if backup and backup.get("category"):
                section_id = backup["category"].get("section_id")
                if section_id is not None:
                    return section_id
        return None

    def _update_section_focus(self, business, section_id_for_focus):
        """Update section focus and cache."""
        try:
            if section_id_for_focus is not None and business:
                business.section_selected.emit(section_id_for_focus)
        except Exception as exc:
            logger.debug(
                "DeleteCategoriesBatchCmd.undo: select_section failed: %s",
                exc,
                exc_info=True,
            )

        try:
            if business and section_id_for_focus is not None:
                try:
                    business._invalidate_categories_cache(section_id_for_focus)
                except Exception as exc:
                    logger.debug(
                        "DeleteCategoriesBatchCmd.undo: invalidate cache failed: %s",
                        exc,
                        exc_info=True,
                    )
                business.section_selected.emit(section_id_for_focus)
        except Exception as exc:
            logger.debug(
                "DeleteCategoriesBatchCmd.undo: final updates failed: %s",
                exc,
                exc_info=True,
            )

    def _update_category_focus(self, business, category_id_for_focus):
        """Update category focus."""
        try:
            if business and category_id_for_focus is not None:
                business.select_category(category_id_for_focus)
        except Exception as exc:
            logger.debug(
                "DeleteCategoriesBatchCmd.undo: select_category failed: %s",
                exc,
                exc_info=True,
            )

    def _emit_batch_signals(self, business, section_id_for_focus, category_id_for_focus):
        """Emit batch deletion signals and schedule reload."""
        try:
            if business:
                try:
                    business.items_batch_deleted.emit(
                        "category",
                        [
                            c.get("id")
                            for c in self.categories
                            if c.get("id") is not None
                        ],
                    )
                except Exception as exc:
                    logger.debug(
                        "DeleteCategoriesBatchCmd.undo: items_batch_deleted emit failed: %s",
                        exc,
                        exc_info=True,
                    )
                business._schedule_structure_reload(0)
                logger.debug(
                    "[BatchUndo:reload] cmd_id=%s section_focus=%s category_focus=%s",
                    hex(id(self)),
                    section_id_for_focus,
                    category_id_for_focus,
                )
        except Exception as exc:
            logger.debug(
                "DeleteCategoriesBatchCmd.undo: schedule reload failed: %s",
                exc,
                exc_info=True,
            )

    def _finalize_batch_undo(self, business, section_id_for_focus, category_id_for_focus):
        """Finalize batch undo with UI updates."""
        try:
            clear_icon_cache()
        except Exception:
            pass
        self._update_section_focus(business, section_id_for_focus)
        self._update_category_focus(business, category_id_for_focus)
        self._emit_batch_signals(business, section_id_for_focus, category_id_for_focus)

    @log_command
    def undo(self):
        business = getattr(self.main, "structure_business", None)
        section_id_for_focus = None
        category_id_for_focus = None
        try:
            restored_cnt = len([b for b in self._backups if b])
            logger.debug(
                "[BatchUndo:start] cmd_id=%s backups=%s", hex(id(self)), restored_cnt
            )
        except Exception as exc:
            logger.debug(
                "DeleteCategoriesBatchCmd.undo: start logging failed: %s",
                exc,
                exc_info=True,
            )
        tree, selection = self._suppress_ui_signals()
        try:
            self._restore_backups()
            section_id_for_focus = self._determine_focus_section()
        finally:
            self._restore_ui_signals(tree, selection)
        self._finalize_batch_undo(business, section_id_for_focus, category_id_for_focus)
        logger.debug(
            "[BatchUndo:done] cmd_id=%s section_focus=%s category_focus=%s",
            hex(id(self)),
            section_id_for_focus,
            category_id_for_focus,
        )
