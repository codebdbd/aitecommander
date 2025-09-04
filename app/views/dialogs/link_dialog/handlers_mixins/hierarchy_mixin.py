"""
Миксин для обновления иерархии (разделы и категории) в LinkDialogHandlers.
"""
from ..icon_utils import make_icon


class HierarchyMixin:
    def _update_sections(self) -> None:
        """Обновляет список разделов."""
        sphere_cb = self.dialog.ui.get_widget("sphere_cb")
        section_cb = self.dialog.ui.get_widget("section_cb")

        section_cb.clear()
        sphere_id = sphere_cb.currentData()

        if sphere_id and self.dialog.dialog_controller:
            sections = self.dialog.dialog_controller.get_sections_for_sphere(sphere_id)
            for sec in sections:
                icon_path_val = (
                    sec["icon_path"]
                    if (hasattr(sec, "keys") and "icon_path" in sec.keys())
                    else ""
                )
                icon = make_icon(icon_path_val)
                if icon:
                    section_cb.addItem(icon, sec["name"], sec["id"])
                else:
                    section_cb.addItem(sec["name"], sec["id"])

        self._update_categories()

    def _update_categories(self) -> None:
        """Обновляет список категорий."""
        section_cb = self.dialog.ui.get_widget("section_cb")
        category_cb = self.dialog.ui.get_widget("category_cb")

        category_cb.clear()
        section_id = section_cb.currentData()

        if section_id and self.dialog.dialog_controller:
            categories = self.dialog.dialog_controller.get_categories_for_section(
                section_id
            )
            for cat in categories:
                icon_path_val = (
                    cat["icon_path"]
                    if (hasattr(cat, "keys") and "icon_path" in cat.keys())
                    else ""
                )
                icon = make_icon(icon_path_val)
                if icon:
                    category_cb.addItem(icon, cat["name"], cat["id"])
                else:
                    category_cb.addItem(cat["name"], cat["id"])
