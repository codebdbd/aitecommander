# app/controllers/ui/links/links_actions.py

from __future__ import annotations

from typing import Any, Callable, Optional, Protocol, Union

from app.controllers.ui.state.task_scheduler import schedule_selection_restore
from app.services import share_service


class LinksActions:
    """Facade for UI link actions.
    Delegates operations to existing controllers: `LinksUIController` and `LinkOperationsController`.
    """

    def __init__(self, main_window, links, link_ops):
        """Create link actions facade.

        Required dependencies passed explicitly:
        - links: `LinksUIController` instance
        - link_ops: `LinkOperationsController` instance

        Dynamic getattr excluded — throw ValueError if dependencies missing.
        """
        self.main = main_window
        self.links = links
        self.link_ops = link_ops
        if self.links is None or self.link_ops is None:
            raise ValueError(
                "LinksActions requires explicit 'links' and 'link_ops' instances"
            )

    # --- Link dialog ---
    def show_link_dialog(
        self, link: dict | None = None, category_id: int | None = None
    ) -> bool:
        if not self.link_ops:
            return False
        return bool(self.link_ops.show_link_dialog(link=link, category_id=category_id))

    def delete_links_with_confirmation(self, links: list[dict]):
        if not self.link_ops:
            return
        return self.link_ops.delete_links_with_confirmation(links)

    # --- Link actions ---
    def open_link(self, link: dict):
        if self.links:
            self.links.open_link(link)

    def toggle_link_favorite(self, link: dict | None = None):
        if self.links:
            self.links.toggle_favorite(link)

    def copy_selected_links(self):
        if self.links:
            self.links.copy_selected_links()

    def paste_links(self):
        if self.links:
            self.links.paste_links()

    def cut_selected_links(self):
        if self.links:
            self.links.cut_selected_links()

    def delete_selected_links(self):
        if self.links:
            self.links.delete_selected_links()

    def show_note_dialog(self, link: dict):
        if self.links:
            self.links.show_note_dialog(link)

    # --- Share link ---
    def share_via_telegram(self, link: dict) -> bool:
        return self._share(link, share_service.share_via_telegram)

    def share_via_whatsapp(self, link: dict) -> bool:
        return self._share(link, share_service.share_via_whatsapp)

    def share_via_viber(self, link: dict) -> bool:
        return self._share(link, share_service.share_via_viber)

    def share_via_email(self, link: dict) -> bool:
        return self._share(link, share_service.share_via_email)

    def share_via_email_client(self, link: dict) -> bool:
        return self._share(link, share_service.share_via_email_client)

    def share_via_email_gmail(self, link: dict) -> bool:
        return self._share(link, share_service.share_via_email_gmail)

    def copy_email_template(self, link: dict) -> bool:
        return self._share(link, share_service.copy_email_template)

    # --- Internal helpers ---
    class _ShareHandler(Protocol):
        def __call__(self, name: Optional[str], url: str) -> Union[
            bool, tuple[bool, Optional[str]]
        ]:
            ...

    def _share(self, link: dict, handler: _ShareHandler) -> bool:
        """Extract name/url and call the provided share handler.

        Returns False when link is missing or url is empty.
        """
        if not link:
            return False
        name = link.get("name")
        url = link.get("url") or link.get("href")
        if not url:
            return False
        result = handler(name, url)
        if isinstance(result, tuple):
            success, _message = result
            return bool(success)
        return bool(result)

    # --- Social networks: X(Twitter), Facebook, LinkedIn ---
    def share_via_x(self, link: dict) -> bool:
        return self._share(link, share_service.share_via_x)

    def share_via_facebook(self, link: dict) -> bool:
        return self._share(link, share_service.share_via_facebook)

    def share_via_linkedin(self, link: dict) -> bool:
        return self._share(link, share_service.share_via_linkedin)

    def share_via_pinterest(self, link: dict) -> bool:
        return self._share(link, share_service.share_via_pinterest)

    # --- Search and restore selection ---
    def on_search(self, text: str):
        if self.links:
            self.links.on_search(text)

    def restore_selection(self, link_id: int):
        if self.links and hasattr(self.links, "focus_on_link"):
            self.links.focus_on_link(link_id)

    def focus_on_link(self, link_id: int):
        """Alias for compatibility: focus on link by ID."""
        self.restore_selection(link_id)

    def schedule_restore_selection(self, link_id: int) -> None:
        """Schedule selection/focus restore on link.

        Encapsulates task scheduler usage so calls from MainWindow
        don't depend on import and don't use getattr/lambda.
        """
        key = f"table_selection_{link_id}"
        # Pass explicit callback to controller method
        schedule_selection_restore(lambda: self.restore_selection(link_id), key)

    # --- Access to link widget data / selection ---
    def get_link_at(self, row: int):
        if not self.links:
            return None
        return self.links.get_link_at(row)

    def get_selected_rows(self):
        if not self.links:
            return []
        return self.links.get_selected_rows()

    def current_row(self) -> int | None:
        if not self.links or not hasattr(self.links, "current_row"):
            return None
        return self.links.current_row()

    def get_selected_links(self):
        if not self.links or not hasattr(self.links, "get_selected_links"):
            return []
        return self.links.get_selected_links()

    # --- Edit current link ---
    def edit_selected_link(self) -> bool:
        row = self.current_row()
        if row is None:
            return False
        # Use current API to get link by row
        link = self.get_link_at(row)
        if not link:
            return False
        # Show dialog via existing API, MainWindow will update statusbar
        result = self.show_link_dialog(link=link)
        if result:
            # Notify statusbar via MainWindow
            if hasattr(self.main, "update_statusbar"):
                self.main.update_statusbar()
            return True
        return False

    # --- Unified action handler for new panel widgets ---
    def on_action_requested(self, action_data: dict[str, Any] | None) -> None:
        """Handler for unified actions from top panels.

        action_data contract (dict):
        - type: str — action type.
            - "open_link": open link from panel.
            - "quick_add": quickly add link of specified type.
        - link: dict | None — link (for type == "open_link").
        - link_type: str | None — quick link type (for type == "quick_add").
        - category_id: int | None — target category (optional; if not specified,
          current category via LinksUIController is used).

        Behavior:
        - open_link: delegates to self.open_link(link).
        - quick_add: delegates to LinksUIController.quick_add_link(link_type, category_id).
        """
        if not isinstance(action_data, dict):
            return

        action_type = action_data.get("type")
        if action_type == "open_link":
            link = action_data.get("link")
            if link:
                self.open_link(link)
        elif action_type == "quick_add":
            # Delegate to LinksUIController for unified behavior
            link_type = action_data.get("link_type")
            category_id = action_data.get("category_id")
            if self.links and hasattr(self.links, "quick_add_link"):
                self.links.quick_add_link(link_type, category_id)

    # --- Delegates for passive widgets (Recent/Favorites) ---
    def on_recent_refresh_requested(self, limit: int):
        if self.links and hasattr(self.links, "on_recent_refresh_requested"):
            return self.links.on_recent_refresh_requested(limit)

    def on_favorites_refresh_requested(self):
        if self.links and hasattr(self.links, "on_favorites_refresh_requested"):
            return self.links.on_favorites_refresh_requested()

    def on_favorites_clear_requested(self):
        if self.links and hasattr(self.links, "on_favorites_clear_requested"):
            return self.links.on_favorites_clear_requested()
