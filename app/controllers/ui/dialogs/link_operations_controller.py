# app/controllers/link_operations_controller.py

import logging

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QDialog

from app.controllers.ui.state.task_scheduler import schedule_selection_restore
from app.controllers.ui.undo.commands_links import (
    BatchDeleteLinksCmd,
    BatchSaveLinksCmd,
    DeleteLinkCmd,
    SaveLinkCmd,
)
from app.controllers.ui.undo.stack import UndoManager
from app.views.windows.dialogs.link_dialog.link_dialog import LinkDialog

# Constants for undo/redo macros
MACRO_DELETE_LINKS_TEXT = "Deleting {count} links"


logger = logging.getLogger(__name__)


class LinkOperationsController(QObject):
    """Controller for link operations: creation, editing, deletion.

    Signal subscribers must be correct and not throw exceptions.
    Any subscriber errors will be logged via logger.exception, but should not
    rely on exception suppression within the controller.
    """

    def __init__(self, db, undo_stack: UndoManager, main_window):
        super().__init__()
        self.db = db
        self.undo_stack = undo_stack
        self.main_window = main_window

    # --- Signals to external listeners ---
    # Signal that link data in category has changed and table reload is required
    links_changed = pyqtSignal(int)  # category_id
    # Signal that favorite state has changed (requires top panel refresh)
    favorites_changed = pyqtSignal()
    # New signal: recent links list changed (e.g., when link is opened)
    recents_changed = pyqtSignal()
    # New signal: specific link created/updated (payload with category_id, id, etc.)
    link_saved = pyqtSignal(dict)
    # New signal: link deleted (payload with category_id, id, etc.)
    link_deleted = pyqtSignal(dict)

    # --- Centralized signal emission methods ---
    def emit_links_changed(self, category_id: int) -> None:
        """Notify subscribers that links for category have changed.

        Requirement: subscribers must not throw exceptions. Errors will
        be logged for diagnostics, but not suppressed silently.
        """
        try:
            if isinstance(category_id, int) and category_id > 0:
                self.links_changed.emit(category_id)
        except Exception:
            logger.exception("emit_links_changed: failed to emit signal")

    def emit_favorites_changed(self) -> None:
        """Notify about favorite state change.

        Requirement: subscribers must not throw exceptions. Errors will
        be logged via logger.exception.
        """
        try:
            self.favorites_changed.emit()
        except Exception:
            logger.exception("emit_favorites_changed: failed to emit signal")

    def emit_recents_changed(self) -> None:
        """Notify about recent links list change.

        Requirement: subscribers must not throw exceptions. Errors will
        be logged via logger.exception.
        """
        try:
            self.recents_changed.emit()
        except Exception:
            logger.exception("emit_recents_changed: failed to emit signal")

    def emit_link_saved(self, payload: dict) -> None:
        try:
            if isinstance(payload, dict):
                self.link_saved.emit(payload)
        except Exception:
            logger.exception("emit_link_saved: failed to emit signal")

    def emit_link_deleted(self, payload: dict) -> None:
        try:
            if isinstance(payload, dict):
                self.link_deleted.emit(payload)
        except Exception:
            logger.exception("emit_link_deleted: failed to emit signal")

    # --- Centralized operation event handlers ---
    def on_link_opened(self, link_data: dict) -> None:
        """Call after successful link opening (updates recent links and category table)."""
        try:
            self.emit_recents_changed()
            cat_id = (
                link_data.get("category_id") if isinstance(link_data, dict) else None
            )
            if isinstance(cat_id, int) and cat_id > 0:
                self.emit_links_changed(cat_id)
        except Exception:
            logger.exception("on_link_opened: failed to emit signals")

    def on_favorite_toggled(self, category_id: int | None) -> None:
        """Call after favorite toggle operation completion."""
        try:
            self.emit_favorites_changed()
            if isinstance(category_id, int) and category_id > 0:
                self.emit_links_changed(category_id)
        except Exception:
            logger.exception("on_favorite_toggled: failed to emit signals")

    def on_link_updated(self, updated_link: dict) -> None:
        """Call after link update (affects recent links and possibly table)."""
        try:
            self.emit_recents_changed()
            cat_id = (
                updated_link.get("category_id")
                if isinstance(updated_link, dict)
                else None
            )
            if isinstance(cat_id, int) and cat_id > 0:
                self.emit_links_changed(cat_id)
        except Exception:
            logger.exception("on_link_updated: failed to emit signals")

    def on_links_deleted(self, links: list[dict]) -> None:
        """Call after link deletion (batch/single)."""
        try:
            # Update table by first link's category (as before)
            cat_id = (links[0] if links else {}).get("category_id")
            if isinstance(cat_id, int) and cat_id > 0:
                self.emit_links_changed(cat_id)
            # Deletion may affect recent links
            self.emit_recents_changed()
            # Emit point deletion events
            for payload in links or []:
                if isinstance(payload, dict):
                    self.emit_link_deleted(payload)
        except Exception:
            logger.exception("on_links_deleted: failed to emit signals")

    def get_dialog_initialization_data(self, category_id=None):
        """Get data for link dialog initialization."""
        data = {"spheres": self._prepare_spheres_data(), "category_hierarchy": None}

        if category_id:
            data["category_hierarchy"] = self._get_category_hierarchy(category_id)

        return data

    def _prepare_spheres_data(self):
        """Prepare sphere data for dialog."""
        structure_business = getattr(self.main_window, "structure_business", None)
        if structure_business is not None:
            try:
                spheres = structure_business.get_cached_spheres()
                if spheres:
                    return spheres
            except Exception as exc:
                logger.debug("Failed to use cached spheres in LinkOperationsController: %s", exc, exc_info=True)
        return self.db.spheres.get_spheres()

    def _get_category_hierarchy(self, category_id):
        """Get category hierarchy (sphere -> section -> category)."""
        return self.db.categories.get_category_hierarchy(category_id)

    def get_sections_for_sphere(self, sphere_id):
        """Get sections for sphere."""
        structure_business = getattr(self.main_window, "structure_business", None)
        if structure_business is not None:
            try:
                sections = structure_business.get_cached_sections(sphere_id)
                if sections:
                    return sections
            except Exception as exc:
                logger.debug(
                    "Failed to use cached sections for sphere %s: %s",
                    sphere_id,
                    exc,
                    exc_info=True,
                )
        return self.db.sections.get_sections(sphere_id)

    def get_categories_for_section(self, section_id):
        """Get categories for section."""
        structure_business = getattr(self.main_window, "structure_business", None)
        if structure_business is not None:
            try:
                categories = structure_business.get_cached_categories(section_id)
                if categories:
                    return categories
            except Exception as exc:
                logger.debug(
                    "Failed to use cached categories for section %s: %s",
                    section_id,
                    exc,
                    exc_info=True,
                )
        return self.db.categories.get_categories(section_id)

    def get_database(self):
        """Get database reference for validation."""
        return self.db

    def show_link_dialog(self, link=None, category_id=None):
        """Show link creation/editing dialog."""
        # Guarantee that we always pass a valid category_id
        cat_id = category_id or self.main_window.get_current_category_id()
        if not cat_id:
            # Try to get first available category from database
            first_cat_id = self.db.categories.get_first_category_id()
            if first_cat_id:
                cat_id = first_cat_id

        # Create controller for dialog
        from .link_dialog_controller import LinkDialogController

        structure_business = getattr(self.main_window, "structure_business", None)
        link_controller = LinkDialogController(
            self.db,
            structure_business=structure_business,
        )

        # Get initialization data through controller
        init_data = link_controller.get_initialization_data(cat_id, link)

        dlg = LinkDialog(
            initialization_data=init_data,
            dialog_controller=self,
            link=link,
            category_id=cat_id,
            parent=self.main_window,
            link_controller=link_controller,
        )

        result = dlg.exec() == QDialog.DialogCode.Accepted
        if result:
            # Get data through controller
            links_to_save = link_controller.get_result_data()
            logger.debug(
                f"show_link_dialog: got {len(links_to_save) if links_to_save else 0} links to save"
            )
            if links_to_save:
                for i, link in enumerate(links_to_save):
                    logger.debug(
                        f"show_link_dialog: link {i}: name={link.get('name')}, browser_key={link.get('browser_key')}"
                    )

            if not links_to_save:
                return False
            # IMPORTANT: determine update/creation by results themselves, not by edit fact
            # If result contains id, this is updating existing record; otherwise — creating new

            # Use batch command for multiple links
            if len(links_to_save) > 1:
                # For multiple links (profiles) always create new records
                logger.debug(
                    f"show_link_dialog: using BatchSaveLinksCmd for {len(links_to_save)} links"
                )
                cmd = BatchSaveLinksCmd(
                    links_data=links_to_save,
                    old_link_data=None,  # Always None for multiple links
                    main_window=self.main_window,
                )
                self.undo_stack.push(cmd)

                # If any saved links have favorite flag change — notify UI centrally
                # (e.g., if link was marked as favorite, notify UI to update favorite count)
                try:
                    if any(
                        isinstance(p, dict) and ("is_favorite" in p)
                        for p in links_to_save
                    ):
                        # Pass None to avoid duplicating final links_changed below
                        self.on_favorite_toggled(None)
                except Exception:
                    logger.exception("show_link_dialog: on_favorite_toggled failed")

                # Set focus on first added link through scheduler
                if hasattr(self.main_window, "links_actions") and hasattr(
                    self.main_window.links_actions, "focus_on_link"
                ):
                    first_link_id = (
                        cmd.created_ids[0]
                        if hasattr(cmd, "created_ids") and cmd.created_ids
                        else None
                    )
                    if first_link_id:
                        try:
                            schedule_selection_restore(
                                lambda: self.main_window.links_actions.focus_on_link(
                                    first_link_id
                                ),
                                first_link_id,
                            )
                        except Exception:
                            logger.exception(
                                "show_link_dialog(batch): schedule focus failed"
                            )
                # Emit events about saved links (batch)
                try:
                    for payload in links_to_save:
                        if isinstance(payload, dict):
                            self.link_saved.emit(payload)
                except Exception:
                    logger.exception("show_link_dialog: emit link_saved failed")
            else:
                # For single links use regular command
                data = links_to_save[0]
                logger.debug(
                    f"show_link_dialog: using SaveLinkCmd for single link: name={data.get('name')}, browser_key={data.get('browser_key')}"
                )
                if data.get("_action") == "delete":
                    # Use Undo command that delegates deletion to service layer
                    cmd = DeleteLinkCmd(
                        link_to_delete=data, main_window=self.main_window
                    )
                    self.undo_stack.push(cmd)
                else:
                    # Override update flag for single result:
                    # if data has no id — this is creating new link, don't pass old_data
                    is_update_single = bool(data.get("id"))
                    cmd = SaveLinkCmd(
                        new_data=data,
                        old_data=(link if is_update_single else None),
                        main_window=self.main_window,
                    )
                    self.undo_stack.push(cmd)

                    # If record contains is_favorite field — notify centrally
                    try:
                        if isinstance(data, dict) and ("is_favorite" in data):
                            # Pass None to avoid duplicating final links_changed below
                            self.on_favorite_toggled(None)
                    except Exception:
                        logger.exception(
                            "show_link_dialog(single): on_favorite_toggled failed"
                        )

                    # Schedule focus restoration on link (for new and updated)
                    logger.debug(
                        f"Focus check: is_update={is_update_single}, has_links_actions={hasattr(self.main_window, 'links_actions')}"
                    )
                    if hasattr(self.main_window, "links_actions"):
                        logger.debug(
                            f"LinksActions exists, has_focus_method={hasattr(self.main_window.links_actions, 'focus_on_link')}"
                        )

                    if hasattr(self.main_window, "links_actions") and hasattr(
                        self.main_window.links_actions, "focus_on_link"
                    ):
                        link_id = cmd.created_id or data.get("id")
                        logger.info(
                            f"Attempting to focus on link: cmd.created_id={cmd.created_id}, data.id={data.get('id')}, final_link_id={link_id}"
                        )
                        if link_id:
                            try:
                                schedule_selection_restore(
                                    lambda: self.main_window.links_actions.focus_on_link(
                                        link_id
                                    ),
                                    link_id,
                                )
                            except Exception:
                                logger.exception(
                                    "show_link_dialog(single): schedule focus failed"
                                )
                        else:
                            logger.warning("No link ID available for focusing")
                    # Emit event about single link save
                    try:
                        if isinstance(data, dict):
                            self.link_saved.emit(data)
                    except Exception:
                        logger.exception(
                            "show_link_dialog(single): emit link_saved failed"
                        )

            # Signal that current category table needs to be reloaded
            try:
                if isinstance(cat_id, int) and cat_id > 0:
                    self.links_changed.emit(cat_id)
            except Exception:
                logger.exception("show_link_dialog: emit links_changed failed")

        return result

    def delete_links_with_confirmation(self, links):
        """Delete links WITHOUT confirmation.

        Bring behavior to unified scenario: like in context menu —
        perform immediate deletion. For multiple links use
        batch command, for single — single command. No confirmation
        dialogs anymore.
        """
        if not links:
            return

        # Single deletion — without confirmation
        if len(links) == 1:
            cmd = DeleteLinkCmd(link_to_delete=links[0], main_window=self.main_window)
            # Suppress internal UI updates, external reloader/statusbar already called
            try:
                cmd._suppress_ui = True
            except Exception:
                logger.exception(
                    "delete_links_with_confirmation(single): failed to set _suppress_ui"
                )
            self.undo_stack.push(cmd)
            # Centralized signal emission
            try:
                self.on_links_deleted(links)
            except Exception:
                logger.exception(
                    "delete_links_with_confirmation(single): on_links_deleted failed"
                )
            return

        # Batch deletion — without confirmation, with Undo macro
        with self.undo_stack.macro(MACRO_DELETE_LINKS_TEXT.format(count=len(links))):
            cmd = BatchDeleteLinksCmd(
                links_to_delete=links, main_window=self.main_window
            )
            # Internal UI suppressed, external reload performed once
            try:
                cmd._suppress_ui = True
            except Exception:
                pass
            self.undo_stack.push(cmd)
        # After batch deletion centrally notify listeners
        try:
            self.on_links_deleted(links)
        except Exception:
            logger.exception(
                "delete_links_with_confirmation(batch): on_links_deleted failed"
            )
