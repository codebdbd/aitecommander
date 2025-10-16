"""Mixin updating sections/categories hierarchy inside `LinkDialogHandlers`."""

from typing import Any

from ..icon_utils import make_icon


class HierarchyMixin:
    def _get_sphere_cb(self) -> Any:
        """Return sphere combo box.

        Kept separate to avoid repetitive `self.dialog.ui.get_widget("sphere_cb")`
        calls and improve readability.
        """
        return self.dialog._get_sphere_cb()

    def _get_section_cb(self) -> Any:
        """Return section combo box."""
        return self.dialog._get_section_cb()

    def _get_category_cb(self) -> Any:
        """Return category combo box."""
        return self.dialog._get_category_cb()

    def _update_sections(self) -> None:
        """Update sections list."""
        sphere_cb = self._get_sphere_cb()
        section_cb = self._get_section_cb()

        section_cb.clear()
        sphere_id = sphere_cb.currentData()

        if sphere_id and self.dialog.dialog_controller:
            sections = self.dialog.dialog_controller.get_sections_for_sphere(sphere_id)
            for sec in sections:
                icon_path_val = self._extract_icon_path(sec)
                self._add_with_optional_icon(
                    section_cb, sec["name"], sec["id"], icon_path_val
                )

        self._update_categories()

    def _update_categories(self) -> None:
        """Update categories list."""
        section_cb = self._get_section_cb()
        category_cb = self._get_category_cb()

        category_cb.clear()
        section_id = section_cb.currentData()

        if section_id and self.dialog.dialog_controller:
            categories = self.dialog.dialog_controller.get_categories_for_section(
                section_id
            )
            for cat in categories:
                icon_path_val = self._extract_icon_path(cat)
                self._add_with_optional_icon(
                    category_cb, cat["name"], cat["id"], icon_path_val
                )

    def _add_with_optional_icon(
        self, combo: Any, name: str, item_id: Any, icon_path_val: str
    ) -> None:
        """Add combo box item with icon when valid, otherwise without icon.

        Same behaviour as before: try creating icon via `make_icon(icon_path_val)`
        then call `addItem(icon, name, id)` or fall back to `addItem(name, id)`.
        """
        icon = make_icon(icon_path_val)
        if icon:
            combo.addItem(icon, name, item_id)
        else:
            combo.addItem(name, item_id)

    def _extract_icon_path(self, item: Any) -> str:
        """Safely extract `icon_path` from dict-like object.

        Returns empty string when missing or object is not a dict. Mirrors the
        previous `hasattr(..., "keys")` behaviour.
        """
        try:
            if isinstance(item, dict):
                return item.get("icon_path", "")
            if hasattr(item, "keys") and "icon_path" in item.keys():
                return item["icon_path"]
        except (AttributeError, TypeError, KeyError):
            return ""
        return ""
