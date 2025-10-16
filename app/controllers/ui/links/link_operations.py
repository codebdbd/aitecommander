# app/controllers/links_ui/link_operations.py

import logging
from datetime import datetime
from typing import Dict

from PyQt6.QtWidgets import QDialog

from app.controllers.ui.undo.commands_links import SaveLinkCmd
from app.utils.links.link_utils import LinkInfo, LinkOpener
from app.views.windows.dialogs.entity_dialogs import NoteDialog

from .base_component import BaseLinksUIComponent
from .exceptions import CategoryNotFoundError, DatabaseError, LinkValidationError

logger = logging.getLogger(__name__)


class LinksUILinkOperations(BaseLinksUIComponent):
    """Link operations for LinksUIController."""

    def quick_add_link(self, link_type: str, category_id: int = None):
        """Quick add link."""
        # Always try to open dialog, even if no category is selected
        # The dialog will handle the case when no category is available
        cat_id = self._validate_category_exists(category_id)

        # Create dialog controller
        from PyQt6.QtWidgets import QDialog

        from app.controllers.ui.dialogs import LinkDialogController
        from app.views.windows.dialogs.link_dialog.link_dialog import LinkDialog

        link_controller = LinkDialogController(self.business.db)
        init_data = link_controller.get_initialization_data(cat_id, None)

        dlg = LinkDialog(
            initialization_data=init_data,
            dialog_controller=link_controller,
            link=None,
            category_id=cat_id,
            parent=self.main,
            link_controller=link_controller,
        )

        # Set link type
        dlg.set_link_type(link_type)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            links_to_save = link_controller.get_result_data()
            if links_to_save:
                for data in links_to_save:
                    cmd = SaveLinkCmd(
                        new_data=data, old_data=None, main_window=self.main
                    )
                    self.main.undo_stack.push(cmd)

    def show_note_dialog(self, link: Dict):
        """Show note dialog for link."""
        if not link:
            return

        # Create link copy for safety
        link_copy = link.copy()

        dlg = NoteDialog(link_copy, parent=self.main)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Update link via business logic
            try:
                # Business layer emits link_updated itself inside save_link()
                self.business.save_link(link_copy)
                logger.debug("Note saved for link: %s", link_copy.get("name"))
            except DatabaseError as e:
                logger.error("Database error saving note: %s", e)
                self._show_error(f"{self.get_message('database_error')}: {str(e)}")
            except Exception as e:
                logger.error("Unexpected error saving note: %s", e)
                self._show_error(f"{self.get_message('error_saving')}: {str(e)}")

    def _open_link(self, link: Dict):
        """Open link using LinkOpener."""
        logger.debug("Opening link: type=%s, url=%s", link.get("type"), link.get("url"))

        success = False
        try:
            # Create LinkInfo from dict
            logger.debug("_open_link: link dict=%s", link)
            link_info = LinkInfo.from_dict(link)
            logger.info("_open_link: link_info=%s", link_info)
            logger.debug(
                "_open_link: link_info created with browser_key=%s",
                link_info.browser_key,
            )

            # Use LinkOpener to open
            opener = LinkOpener()
            opener.open_link(link_info)

            success = True
        except LinkValidationError as e:
            logger.error("Link validation error: %s", e)
            self._show_error(f"{self.get_message('validation_error')}: {str(e)}")
        except ValueError as e:
            # User-friendly unsafe URL handling without popup errors
            msg = str(e)
            if msg.startswith("Unsafe URL:"):
                from app.controllers.ui.dialogs import DialogManager

                safe_msg = self.get_message(
                    "unsafe_url_info",
                    "This link cannot be opened for security reasons.",
                )
                details = msg  # so reason text is available when details enabled
                logger.warning("Blocked unsafe URL: %s", msg)
                DialogManager.show_info(
                    parent=self.main,
                    title=self.get_message("warning_title", "Warning"),
                    message=safe_msg,
                    informative_text=self.get_message(
                        "unsafe_url_hint",
                        "Check link address or edit it.",
                    ),
                    details=details,
                    silent=True,
                )
            else:
                # Other ValueError — as error
                logger.error(
                    "Error opening link %s: %s", link.get("url", link), e, exc_info=True
                )
                self._show_error(f"Failed to open link: {str(e)}")
        except Exception as e:
            logger.error(
                "Error opening link %s: %s", link.get("url", link), e, exc_info=True
            )
            self._show_error(f"Failed to open link: {str(e)}")

        # Update recent links counter only on successful open
        if success:
            link_data = link.copy()
            link_data["last_used"] = datetime.now().isoformat()

            # Asynchronously save to DB (old behavior)
            self.business.save_link(link_data)

            # Centralized signal emission via LinkOperationsController
            try:
                self.link_operations.on_link_opened(link_data)
            except Exception as e:
                logger.debug("Failed to emit signals after opening link: %s", e)

    def _toggle_fav(self, link: Dict = None):
        """Toggle favorite status."""
        if not link:
            selected_links = self.controller.get_selected_links()
            if not selected_links:
                return
            link = selected_links[0]

        self.business.toggle_favorite(link)
