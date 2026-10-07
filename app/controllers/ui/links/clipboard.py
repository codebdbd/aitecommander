# app/controllers/links_ui/clipboard.py

import logging

from app.controllers.ui.undo.commands_links import (
    BatchDeleteLinksCmd,
    BatchSaveLinksCmd,
    DeleteLinkCmd,
    SaveLinkCmd,
)
from app.utils.ui.dnd.links_command import MoveLinksCommand
from app.utils.ui.clipboard import copy_link_to_clipboard, get_link_from_clipboard

from .base_component import BaseLinksUIComponent
from .exceptions import CategoryNotFoundError

logger = logging.getLogger(__name__)


class LinksUIClipboard(BaseLinksUIComponent):
    """Clipboard logic for LinksUIController."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._clipboard_is_cut: bool = False
        self._cut_link_ids: set[int] = set()

    def cut_link(self):
        """Cut selected links (pending cut / dimmed state)."""
        links = self.get_selected_links()
        if not links:
            return

        success = copy_link_to_clipboard(links[0] if len(links) == 1 else links)
        if success:
            self._clipboard_is_cut = True
            self._cut_link_ids = {
                int(l["id"]) for l in links if isinstance(l, dict) and l.get("id") is not None
            }
            if hasattr(self.table, "set_cut_link_ids"):
                self.table.set_cut_link_ids(self._cut_link_ids)

    def copy_link(self):
        """Copy selected links."""
        self.cancel_cut()
        links = self.get_selected_links()
        if not links:
            return
        copy_link_to_clipboard(links[0] if len(links) == 1 else links)

    def cancel_cut(self):
        """Cancel pending cut state."""
        self._clipboard_is_cut = False
        if self._cut_link_ids:
            self._cut_link_ids.clear()
            if hasattr(self.table, "set_cut_link_ids"):
                self.table.set_cut_link_ids(set())

    def paste_link(self, target_category_id: int | None = None):
        """Paste links from clipboard."""
        try:
            current_category_id = self._validate_category_exists(target_category_id)
        except CategoryNotFoundError as e:
            self._show_warning(str(e))
            return

        if not current_category_id:
            return

        if self._clipboard_is_cut and self._cut_link_ids:
            cut_ids = list(self._cut_link_ids)
            existing = self.business.get_links(current_category_id) or []
            existing_links = [dict(r) for r in existing]
            existing_by_name = {
                str(l.get("name", "")).strip().lower(): dict(l)
                for l in existing_links
                if str(l.get("name", "")).strip()
            }
            existing_names = [str(l.get("name", "")) for l in existing_links]
            name_overrides: dict[int, str] = {}
            replacements: dict[int, int] = {}
            to_move_ids: list[int] = []
            links_service = getattr(self.business, "links", None)
            conflicts = [
                cid for cid in cut_ids
                if (
                    ld := ((links_service.get_link_by_id(cid) if links_service else {}) or {}),
                    str(ld.get("name", "")).strip().lower() in existing_by_name
                )[1]
            ]
            from app.controllers.ui.conflict_resolution_session import ConflictResolutionSession
            session = ConflictResolutionSession(self.main, operation="paste", total_conflicts=len(conflicts))
            for cid in cut_ids:
                link_data = (links_service.get_link_by_id(cid) if links_service else {}) or {}
                c_name = str(link_data.get("name", "")).strip()
                if c_name.lower() in existing_by_name:
                    target_match = existing_by_name[c_name.lower()]
                    action, copy_name = session.resolve(
                        "link",
                        c_name,
                        existing_names,
                        existing_info=target_match,
                        incoming_info=link_data,
                    )
                    if action == "cancel":
                        return
                    if action == "skip":
                        continue
                    if action == "copy":
                        name_overrides[cid] = copy_name
                        existing_names.append(copy_name)
                    elif action == "merge":
                        if target_match and target_match.get("id"):
                            replacements[cid] = int(target_match["id"])
                to_move_ids.append(cid)
            if not to_move_ids:
                return
            self.cancel_cut()
            try:
                cmd = MoveLinksCommand(
                    link_ids=to_move_ids,
                    new_category_id=current_category_id,
                    main_window=self.main,
                    name_overrides=name_overrides,
                    replacements=replacements,
                )
                self.main.undo_stack.push(cmd)
            except Exception as e:
                logger.error("Error moving links on paste: %s", e, exc_info=True)
                self._show_error(f"Failed to move links: {str(e)}")
            return

        try:
            links = self._validate_clipboard_data()
            if not links:
                return

            is_cut = self._clipboard_is_cut
            self._clipboard_is_cut = False

            # Get existing links for duplicate checking
            existing = self.business.get_links(current_category_id)

            # Optimized duplicate filtering using set
            new_links = self._filter_duplicates_optimized(
                links, existing, current_category_id
            )

            if not new_links:
                return  # All links are duplicates

            # Вставка ссылок
            self._insert_links(new_links, is_cut=is_cut)

        except Exception as e:
            logger.error("Error pasting links: %s", e, exc_info=True)
            self._show_error(f"Failed to paste links: {str(e)}")

    def delete_links(self, links: list[dict], *, is_cut: bool = False):
        """Delete links."""
        if not links:
            return

        if len(links) > 1:
            # Batch command: one transaction and one external reload
            command = BatchDeleteLinksCmd(
                links_to_delete=links, main_window=self.main, is_cut=is_cut
            )
            command._suppress_ui = True  # type: ignore[attr-defined]
            self.main.undo_stack.push(command)
        else:
            for link in links:
                cmd = DeleteLinkCmd(
                    link_to_delete=link, main_window=self.main, is_cut=is_cut
                )
                cmd._suppress_ui = True  # type: ignore[attr-defined]
                self.main.undo_stack.push(cmd)

        if self._cut_link_ids:
            del_ids = {
                int(l["id"])
                for l in links
                if isinstance(l, dict) and l.get("id") is not None
            }
            self._cut_link_ids.difference_update(del_ids)
            if not self._cut_link_ids:
                self.cancel_cut()
            elif hasattr(self.table, "set_cut_link_ids"):
                self.table.set_cut_link_ids(self._cut_link_ids)

        # Centralized signal emission through LinkOperationsController
        try:
            if len(links) <= 1:
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

    def _insert_links(self, links: list[dict], *, is_cut: bool = False):
        """Insert list of links with undo support."""
        if not links:
            return
        replaced_links = {
            int(l["id"]): l.pop("_old_link_snapshot")
            for l in links
            if "_old_link_snapshot" in l and l.get("id")
        }
        cmd = BatchSaveLinksCmd(
            links_data=links,
            _old_link_data=None,
            main_window=self.main,
            is_cut=is_cut,
            replaced_links=replaced_links,
        )
        self.main.undo_stack.push(cmd)

    def _filter_duplicates_optimized(
        self, links: list[dict], existing_links: list[dict], category_id: int
    ) -> list[dict]:
        """Optimized duplicate filtering with conflict resolution."""
        existing_by_name = {
            str(l.get("name", "")).strip().lower(): dict(l)
            for l in existing_links
            if str(l.get("name", "")).strip()
        }
        existing_names = [str(l.get("name", "")) for l in existing_links]

        new_links = []
        conflict_count = sum(
            1 for l in links
            if str(l.get("name", "")).strip().lower() in existing_by_name
        )
        from app.controllers.ui.conflict_resolution_session import ConflictResolutionSession
        session = ConflictResolutionSession(self.main, operation="paste", total_conflicts=conflict_count)

        for link in links:
            new_data = self._prepare_link_data(link, category_id)
            c_name = str(new_data.get("name", "")).strip()

            if c_name.lower() in existing_by_name:
                matching_link = existing_by_name[c_name.lower()]
                action, copy_name = session.resolve(
                    "link",
                    c_name,
                    existing_names,
                    existing_info=matching_link,
                    incoming_info=new_data,
                )
                if action == "cancel":
                    return []
                if action == "skip":
                    continue
                if action == "copy":
                    new_data["name"] = copy_name
                    existing_names.append(copy_name)
                    existing_by_name[copy_name.strip().lower()] = new_data
                elif action == "merge":
                    if matching_link and matching_link.get("id"):
                        new_data["id"] = matching_link["id"]
                        new_data["_old_link_snapshot"] = dict(matching_link)
            else:
                if c_name:
                    existing_names.append(c_name)
                    existing_by_name[c_name.lower()] = new_data
            new_links.append(new_data)

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
