# app/controllers/links_ui/link_operations.py

import logging
from datetime import datetime

from PyQt6.QtWidgets import QDialog

from app.controllers.ui.undo.commands_links import SaveLinkCmd
from app.utils.links.link_utils import (
    LinkInfo,
    LinkOpener,
    sanitize_link_dict_for_log,
    sanitize_url_for_logging,
)
from app.views.windows.dialogs.entity_dialogs import NoteDialog

from .base_component import BaseLinksUIComponent
from .exceptions import DatabaseError, LinkValidationError

logger = logging.getLogger(__name__)


class LinksUILinkOperations(BaseLinksUIComponent):
    """Link operations for LinksUIController."""

    def quick_add_link(self, link_type: str, category_id: int | None = None):
        """Quick add link."""
        # Always try to open dialog, even if no category is selected
        # The dialog will handle the case when no category is available
        cat_id = self._validate_category_exists(category_id)

        # Create dialog controller
        from PyQt6.QtWidgets import QDialog

        from app.controllers.ui.dialogs import LinkDialogController
        from app.views.windows.dialogs.link_dialog.link_dialog import LinkDialog

        link_controller = LinkDialogController(
            self.business.db,
            structure_business=getattr(self.main, "structure_business", None),
        )
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

    def show_note_dialog(self, link: dict):
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

    def _prepare_rotated_link(self, link: dict) -> dict:
        """Prepare link copy with args and browser_key set to next rotated Chrome profile."""
        import json

        profiles = []
        try:
            raw_profiles = link.get("rotation_profiles")
            if isinstance(raw_profiles, str):
                profiles = json.loads(raw_profiles)
            elif isinstance(raw_profiles, list):
                profiles = raw_profiles
        except Exception as e:
            logger.error("Failed to parse rotation_profiles JSON: %s", e)
            profiles = []

        if not profiles:
            return link

        current_index = int(link.get("rotation_index", 0) or 0) % len(profiles)
        profile = profiles[current_index]

        rotated_link = link.copy()
        profile_dir = profile.get("directory", "")
        rotated_link["args"] = f'--profile-directory="{profile_dir}"'
        rotated_link["browser_key"] = profile.get("browser_key", "chrome")

        # Advance rotation index for next open
        next_index = (current_index + 1) % len(profiles)
        link["rotation_index"] = next_index
        rotated_link["rotation_index"] = next_index

        link_id = link.get("id")
        if isinstance(link_id, int):
            update_rot = getattr(self.business, "update_rotation_index", None)
            if callable(update_rot):
                try:
                    update_rot(link_id, next_index)
                except Exception as e:
                    logger.error("Error updating rotation index for link %s: %s", link_id, e)

        return rotated_link

    def _open_link(self, link: dict):
        """Open link using LinkOpener."""
        target_link = link
        if link.get("chrome_rotation") and link.get("rotation_profiles"):
            target_link = self._prepare_rotated_link(link)

        safe_url = sanitize_url_for_logging(target_link.get("url", ""))
        logger.debug("Opening link: type=%s, url=%s", target_link.get("type"), safe_url)

        success = False
        try:
            # Create LinkInfo from dict
            logger.debug("_open_link: link dict=%s", sanitize_link_dict_for_log(target_link))
            link_info = LinkInfo.from_dict(target_link)
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
                raw_url = msg.split(":", 1)[-1].strip() if ":" in msg else msg
                logger.warning("Blocked unsafe URL: %s", sanitize_url_for_logging(raw_url))
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

            # Update last_used asynchronously when possible, with safe fallbacks
            try:
                link_id = link_data.get("id")
                update_last_used = getattr(self.business, "update_link_last_used", None)
                if callable(update_last_used) and isinstance(link_id, int):
                    update_last_used(link_id)
                else:
                    save_async = getattr(self.business, "save_link_async", None)
                    if callable(save_async):
                        save_async(link_data)
                    else:
                        self.business.save_link(link_data)
            except DatabaseError as e:
                logger.error("Database error updating last_used: %s", e)
            except Exception as e:
                logger.error("Unexpected error updating last_used: %s", e)

            # Centralized signal emission via LinkOperationsController
            try:
                self.link_operations.on_link_opened(link_data)
            except Exception as e:
                logger.debug("Failed to emit signals after opening link: %s", e)

    def _toggle_fav(self, link: dict | None = None):
        """Toggle favorite status."""
        if not link:
            selected_links = self.controller.get_selected_links()
            if not selected_links:
                return
            link = selected_links[0]

        self.business.toggle_favorite(link)
