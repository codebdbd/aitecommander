# app/controllers/links_ui/clipboard.py

import logging

from app.controllers.ui.undo.commands_links import (
    BatchDeleteLinksCmd,
    BatchSaveLinksCmd,
    DeleteLinkCmd,
    SaveLinkCmd,
)
from app.utils.ui.clipboard import copy_link_to_clipboard, get_link_from_clipboard

from .base_component import BaseLinksUIComponent
from .exceptions import CategoryNotFoundError, DatabaseError

logger = logging.getLogger(__name__)


class LinksUIClipboard(BaseLinksUIComponent):
    """Clipboard logic for LinksUIController."""

    def cut_link(self):
        """Cut selected links."""
        self._process_clipboard_operation(is_cut=True)

    def copy_link(self):
        """Copy selected links."""
        self._process_clipboard_operation(is_cut=False)

    def _process_clipboard_operation(self, is_cut: bool = False):
        """Common logic for copying/cutting links."""
        links = self.get_selected_links()
        if not links:
            return

        success = copy_link_to_clipboard(links[0] if len(links) == 1 else links)
        if is_cut and success:
            self.delete_links(links)

    def paste_link(self):
        """Paste links from clipboard."""
        try:
            current_category_id = self._validate_category_exists(None)
        except CategoryNotFoundError as e:
            self._show_warning(str(e))
            return

        try:
            links = self._validate_clipboard_data()
            if not links:
                return

            # Get existing links for duplicate checking
            existing = self.business.get_links(current_category_id)

            # Optimized duplicate filtering using set
            new_links = self._filter_duplicates_optimized(
                links, existing, current_category_id
            )

            if not new_links:
                return  # All links are duplicates

            # Вставка ссылок
            self._insert_links(new_links)

        except Exception as e:
            logger.error("Error pasting links: %s", e, exc_info=True)
            self._show_error(f"Failed to paste links: {str(e)}")

    def delete_links(self, links: list[dict]):
        """Delete links."""
        if not links:
            return

        category_id = links[0].get("category_id")

        if len(links) > 1:
            # Batch command: one transaction and one external reload
            with self.main.undo_stack.macro(f"Deleting {len(links)} links"):
                command = BatchDeleteLinksCmd(
                    links_to_delete=links, main_window=self.main
                )
                setattr(command, '_suppress_ui', True)  # type: ignore[attr-defined]
                self.main.undo_stack.push(command)
        else:
            for link in links:
                cmd = DeleteLinkCmd(link_to_delete=link, main_window=self.main)
                setattr(cmd, '_suppress_ui', True)  # type: ignore[attr-defined]
                self.main.undo_stack.push(cmd)

        # Update display (command suppresses internal UI, here — one reload)
        if category_id is not None:
            try:
                self._update_category_safe(category_id)
            except DatabaseError as e:
                logger.error("Failed to update category after deletion: %s", e)
        # Centralized signal emission through LinkOperationsController
        try:
            self.link_operations.on_links_deleted(links)
        except Exception as e:
            logger.debug("Failed to emit signals after delete_links: %s", e)

    def get_selected_links(self) -> list[dict]:
        """Get selected links through single source of truth (LinksUIController)."""
        try:
            return self.controller.get_selected_links()
        except Exception:
            # In rare cases when controller is unavailable, return empty list
            logger.debug(
                "clipboard.get_selected_links: controller unavailable", exc_info=True
            )
            return []

    def _validate_clipboard_data(self) -> list[dict]:
        """Validate clipboard data."""
        links = get_link_from_clipboard()
        if not links:
            return []

        # Нормализация к списку
        if isinstance(links, dict):
            links = [links]
        elif not isinstance(links, list):
            raise ValueError("Incorrect clipboard data format")

        return links

    def _prepare_link_data(self, link: dict, category_id: int) -> dict:
        """Prepare link data for insertion."""
        new_data = dict(link)
        new_data.pop("id", None)  # Remove old ID
        new_data["category_id"] = category_id
        return new_data

    def _insert_links(self, links: list[dict]):
        """Insert list of links with undo support."""
        if len(links) > 1:
            # Batch insertion: one transaction, one reload in command
            with self.main.undo_stack.macro(f"Inserting {len(links)} links"):
                cmd = BatchSaveLinksCmd(
                    links_data=links,
                    _old_link_data=None,
                    main_window=self.main,
                )
                # Command will perform single reload; external updates not needed
                self.main.undo_stack.push(cmd)
        else:
            for link_data in links:
                self.main.undo_stack.push(
                    SaveLinkCmd(
                        new_data=link_data, old_data=None, main_window=self.main
                    )
                )

    def _filter_duplicates_optimized(
        self, links: list[dict], existing_links: list[dict], category_id: int
    ) -> list[dict]:
        """Optimized duplicate filtering using set for O(n) complexity."""
        # Create set of existing keys for fast lookup
        existing_keys = set()
        for link in existing_links:
            link_dict = dict(link) if not isinstance(link, dict) else link
            key = (
                link_dict.get("url", ""),
                link_dict.get("type", ""),
                link_dict.get("args", ""),
                link_dict.get(
                    "name", ""
                ),  # Учитываем name, как в UNIQUE(category_id,name,url,args)
            )
            existing_keys.add(key)

        new_links = []
        filtered_count = 0
        for link in links:
            new_data = self._prepare_link_data(link, category_id)
            candidate_key = (
                new_data.get("url", ""),
                new_data.get("type", ""),
                new_data.get("args", ""),
                new_data.get("name", ""),
            )

            if candidate_key not in existing_keys:
                new_links.append(new_data)
                existing_keys.add(candidate_key)  # Add for next checks
            else:
                filtered_count += 1

        if filtered_count:
            logger.info(
                "[Paste] Filtered duplicates: %s out of %s by key (url,type,args,name)",
                filtered_count,
                len(links),
            )
        return new_links

    def _is_duplicate(self, candidate: dict, links: list[dict]) -> bool:
        """Check if link is duplicate (preserved for backward compatibility)."""
        candidate_key = (
            candidate.get("url", ""),
            candidate.get("type", ""),
            candidate.get("args", ""),
        )

        for link in links:
            link_dict = dict(link) if not isinstance(link, dict) else link
            link_key = (
                link_dict.get("url", ""),
                link_dict.get("type", ""),
                link_dict.get("args", ""),
            )
            if candidate_key == link_key:
                return True
        return False
