"""Mixin updating sections/categories hierarchy inside `LinkDialogHandlers`."""

from typing import Any

from app.utils.ui.qt.combo_helpers import add_combo_item

from ..icon_utils import get_cached_icon


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

    def _update_sections(self, with_icons: bool = True) -> None:
        """Update sections list."""
        sphere_cb = self._get_sphere_cb()
        section_cb = self._get_section_cb()

        section_cb.clear()
        sphere_id = sphere_cb.currentData()

        if sphere_id and self.dialog.dialog_controller:
            sections = self.dialog.dialog_controller.get_sections_for_sphere(sphere_id)
            for sec in sections:
                icon_path_val = self._extract_icon_path(sec)
                self._add_item(section_cb, sec["name"], sec["id"], icon_path_val, with_icons)

        self._update_categories(with_icons=with_icons)

    def _update_categories(self, with_icons: bool = True) -> None:
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
                self._add_item(category_cb, cat["name"], cat["id"], icon_path_val, with_icons)

    def _add_item(
        self, combo: Any, name: str, item_id: Any, icon_path_val: str, with_icons: bool
    ) -> None:
        """Add combo item, optionally applying an icon."""
        if not with_icons:
            add_combo_item(combo, name, item_id)
            return
        self._add_with_optional_icon(combo, name, item_id, icon_path_val)

    def _add_with_optional_icon(
        self, combo: Any, name: str, item_id: Any, icon_path_val: str
    ) -> None:
        """Add combo box item with cached icon when available."""
        icon = get_cached_icon(icon_path_val or "")
        add_combo_item(combo, name, item_id, icon=icon)

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
