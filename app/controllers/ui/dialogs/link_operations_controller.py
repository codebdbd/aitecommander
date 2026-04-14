# app/controllers/link_operations_controller.py

import logging
import time

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, QObject, pyqtSignal
from PyQt6.QtWidgets import QDialog

from app.controllers.ui.dialogs import DialogManager
from app.controllers.ui.state.task_scheduler import schedule_selection_restore
from app.config_data.runtime_config import get_table_selection_restore_delay_ms
from app.controllers.ui.undo.commands_links import (
    BatchDeleteLinksCmd,
    BatchSaveLinksCmd,
    DeleteLinkCmd,
    SaveLinkCmd,
)
from app.controllers.ui.undo.stack import UndoManager

_LINK_OPERATIONS_CONTEXT = "LinkOperations"
_MACRO_DELETE_LINKS_TEXT = QT_TRANSLATE_NOOP(
    _LINK_OPERATIONS_CONTEXT, "Deleting {count} links"
)
_CONFIRM_DELETE_LINKS_TITLE = QT_TRANSLATE_NOOP(
    _LINK_OPERATIONS_CONTEXT, "Confirm deletion"
)
_CONFIRM_DELETE_LINKS_MESSAGE = QT_TRANSLATE_NOOP(
    _LINK_OPERATIONS_CONTEXT,
    "{count} selected link(s) will be permanently deleted.\n\n"
    "Are you sure you want to continue?",
)
_CONFIRM_DELETE_LINKS_INFO = QT_TRANSLATE_NOOP(
    _LINK_OPERATIONS_CONTEXT, "This action is irreversible."
)

logger = logging.getLogger(__name__)


def _tr_link_ops(text: str) -> str:
    return QCoreApplication.translate(_LINK_OPERATIONS_CONTEXT, text)


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

    def emit_top_panels_changed(self, *, favorites: bool, recents: bool) -> None:
        """Emit top panel change signals in a single place to reduce duplication."""
        try:
            if favorites:
                self.emit_favorites_changed()
            if recents:
                self.emit_recents_changed()
        except Exception:
            logger.exception("emit_top_panels_changed: failed to emit signals")

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
            self.emit_top_panels_changed(favorites=False, recents=True)
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
            self.emit_top_panels_changed(favorites=True, recents=False)
            if isinstance(category_id, int) and category_id > 0:
                self.emit_links_changed(category_id)
        except Exception:
            logger.exception("on_favorite_toggled: failed to emit signals")

    def on_link_updated(self, updated_link: dict) -> None:
        """Call after link update (affects recent links and possibly table)."""
        try:
            self.emit_top_panels_changed(favorites=False, recents=True)
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
            self.emit_top_panels_changed(favorites=True, recents=True)
            # Per-link notifications are too expensive for bulk deletes and
            # trigger a synchronous UI storm before the DB task even starts.
            if len(links or []) == 1:
                payload = links[0]
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
                logger.debug(
                    "Failed to use cached spheres in LinkOperationsController: %s",
                    exc,
                    exc_info=True,
                )
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

    def _get_valid_category_id(self, category_id=None):
        """Get valid category ID, falling back to current or first available."""
        cat_id = category_id or self.main_window.get_current_category_id()
        if not cat_id:
            first_cat_id = self.db.categories.get_first_category_id()
            if first_cat_id:
                cat_id = first_cat_id
        return cat_id

    def _create_link_dialog(self, link, cat_id):
        """Create and configure link dialog."""
        from app.views.windows.dialogs.link_dialog.link_dialog import LinkDialog
        from .link_dialog_controller import LinkDialogController

        structure_business = getattr(self.main_window, "structure_business", None)
        link_controller = LinkDialogController(
            self.db,
            structure_business=structure_business,
        )

        init_data = link_controller.get_initialization_data(cat_id, link)

        dlg = LinkDialog(
            initialization_data=init_data,
            dialog_controller=self,
            link=link,
            category_id=cat_id,
            parent=self.main_window,
            link_controller=link_controller,
        )

        return dlg, link_controller

    def _handle_favorite_toggle(self, links_to_save):
        """Handle favorite toggle notification."""
        try:
            if any(isinstance(p, dict) and ("is_favorite" in p) for p in links_to_save):
                self.on_favorite_toggled(None)
        except Exception:
            logger.exception("show_link_dialog: on_favorite_toggled failed")

    def _schedule_focus_on_link(self, link_id, context=""):
        """Schedule focus on link after save."""
        if not link_id:
            logger.warning("No link ID available for focusing")
            return

        if not hasattr(self.main_window, "links_actions"):
            return

        if not hasattr(self.main_window.links_actions, "focus_on_link"):
            return

        try:
            delay_ms = get_table_selection_restore_delay_ms(100)
            schedule_selection_restore(
                lambda: self.main_window.links_actions.focus_on_link(link_id),
                link_id,
                delay=delay_ms,
            )
        except Exception:
            logger.exception(f"show_link_dialog({context}): schedule focus failed")

    def _emit_link_saved(self, data):
        """Emit link_saved signal."""
        try:
            if isinstance(data, dict):
                self.link_saved.emit(data)
        except Exception:
            logger.exception("show_link_dialog: emit link_saved failed")

    def _save_multiple_links(self, links_to_save, link):
        """Save multiple links using batch command."""
        logger.debug(
            f"show_link_dialog: using BatchSaveLinksCmd for {len(links_to_save)} links"
        )

        cmd = BatchSaveLinksCmd(
            links_data=links_to_save,
            _old_link_data=None,
            main_window=self.main_window,
        )
        # Avoid heavy synchronous table reload inside command.redo().
        # A single centralized reload is emitted by show_link_dialog() below.
        try:
            cmd._suppress_ui = True
        except Exception:
            logger.debug(
                "show_link_dialog(batch): failed to set _suppress_ui",
                exc_info=True,
            )
        self.undo_stack.push(cmd)

        # Handle favorite toggle
        self._handle_favorite_toggle(links_to_save)

        # Focus on first link
        first_link_id = (
            cmd.created_ids[0]
            if hasattr(cmd, "created_ids") and cmd.created_ids
            else None
        )
        if first_link_id:
            self._schedule_focus_on_link(first_link_id, "batch")

        # Avoid signal storms for large batches; table will be reloaded once.
        emit_limit = 20
        if len(links_to_save) <= emit_limit:
            for payload in links_to_save:
                self._emit_link_saved(payload)
        else:
            logger.debug(
                "show_link_dialog(batch): skipped per-item link_saved emits for %s items",
                len(links_to_save),
            )

    def _save_single_link(self, data, link):
        """Save single link using regular command."""
        logger.debug(
            f"show_link_dialog: using SaveLinkCmd for single link: name={data.get('name')}, browser_key={data.get('browser_key')}"
        )

        if data.get("_action") == "delete":
            cmd = DeleteLinkCmd(link_to_delete=data, main_window=self.main_window)
            self.undo_stack.push(cmd)
            return

        # Determine if update or create
        is_update_single = bool(data.get("id"))
        cmd = SaveLinkCmd(
            new_data=data,
            old_data=(link if is_update_single else None),
            main_window=self.main_window,
        )
        self.undo_stack.push(cmd)

        # Handle favorite toggle
        if isinstance(data, dict) and ("is_favorite" in data):
            try:
                self.on_favorite_toggled(None)
            except Exception:
                logger.exception("show_link_dialog(single): on_favorite_toggled failed")

        # Schedule focus
        logger.debug(
            f"Focus check: is_update={is_update_single}, has_links_actions={hasattr(self.main_window, 'links_actions')}"
        )
        link_id = cmd.created_id or data.get("id")
        if link_id:
            logger.info(
                f"Attempting to focus on link: cmd.created_id={cmd.created_id}, data.id={data.get('id')}, final_link_id={link_id}"
            )
            self._schedule_focus_on_link(link_id, "single")

        # SaveLinkCmd emits link_saved after actual DB completion.
        # Avoid duplicate early emit here (especially for newly created links).

    def show_link_dialog(self, link=None, category_id=None):
        """Show link creation/editing dialog."""
        # Get valid category ID
        cat_id = self._get_valid_category_id(category_id)

        # Create and show dialog
        dlg, link_controller = self._create_link_dialog(link, cat_id)
        result = dlg.exec() == QDialog.DialogCode.Accepted

        if not result:
            return False

        # Get data from controller
        links_to_save = link_controller.get_result_data()
        logger.debug(
            f"show_link_dialog: got {len(links_to_save) if links_to_save else 0} links to save"
        )

        if links_to_save:
            for i, link_data in enumerate(links_to_save):
                logger.debug(
                    f"show_link_dialog: link {i}: name={link_data.get('name')}, browser_key={link_data.get('browser_key')}"
                )

        if not links_to_save:
            return False

        # Save links (batch or single)
        if len(links_to_save) > 1:
            self._save_multiple_links(links_to_save, link)
        else:
            self._save_single_link(links_to_save[0], link)

        # Signal that category table needs reload
        try:
            if isinstance(cat_id, int) and cat_id > 0:
                self.links_changed.emit(cat_id)
        except Exception:
            logger.exception("show_link_dialog: emit links_changed failed")

        return result

    def delete_links_with_confirmation(self, links):
        """Delete links with a batch confirmation dialog.

        Single-link deletion keeps the existing immediate behavior.
        Batch deletion requires explicit user confirmation.
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

        message = _tr_link_ops(_CONFIRM_DELETE_LINKS_MESSAGE).format(count=len(links))
        if not DialogManager.ask_confirmation(
            self.main_window,
            message,
            _tr_link_ops(_CONFIRM_DELETE_LINKS_TITLE),
            informative_text=_tr_link_ops(_CONFIRM_DELETE_LINKS_INFO),
            details=f"links={len(links)}",
        ):
            return

        # Batch deletion — with confirmation, with Undo macro
        macro_text = _tr_link_ops(_MACRO_DELETE_LINKS_TEXT).format(count=len(links))
        with self.undo_stack.macro(macro_text):
            cmd = BatchDeleteLinksCmd(
                links_to_delete=links, main_window=self.main_window
            )
            # Internal UI suppressed, external reload performed once
            try:
                cmd._suppress_ui = True
            except Exception:
                pass
            self.undo_stack.push(cmd)
        # Batch path defers UI reload to async command completion to avoid
        # a synchronous UI stall before the delete operation actually starts.
