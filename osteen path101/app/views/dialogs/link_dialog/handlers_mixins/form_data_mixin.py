"""
Миксин для сбора данных формы LinkDialog.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class FormDataMixin:
    def _build_form_data(self) -> Dict[str, Any]:
        """Формирует данные формы из UI компонентов."""
        return self._collect_form_data()

    def _collect_form_data(self) -> Dict[str, Any]:
        """Сбор данных из формы."""
        collected_name = self.dialog._get_name_le().text().strip()
        collected_args = self.dialog._get_args_le().text().strip()
        collected_link_id = self.dialog.link.get("id") if self.dialog.link else None

        logger.debug("_collect_form_data: collected name from UI='%s'", collected_name)
        logger.debug("_collect_form_data: dialog.link=%s", self.dialog.link)
        logger.debug(
            "_collect_form_data: dialog.selected_profiles count=%s",
            len(self.dialog.selected_profiles) if self.dialog.selected_profiles else 0,
        )

        form_data = {
            "name": collected_name,
            "url": self.dialog._get_url_le().text().strip(),
            "link_type": self.dialog.link_type,
            "category_id": self.dialog._get_category_cb().currentData(),
            "args": collected_args,
            "is_favorite": self.dialog._get_fav_chk().isChecked(),
            "icon_name": self.dialog.icon_name,
            "notes": self.dialog._get_notes_te().toPlainText().strip(),
            "selected_profiles": self.dialog.selected_profiles,
            "link_id": collected_link_id,
            "last_used": self.dialog.link.get("last_used")
            if self.dialog.link
            else None,
            "position": self.dialog.link.get("position", 0) if self.dialog.link else 0,
        }

        # Добавляем выбранные профили, если есть
        if hasattr(self.dialog, "selected_profiles"):
            logger.debug(
                "_collect_form_data: selected_profiles count=%s",
                len(self.dialog.selected_profiles)
                if self.dialog.selected_profiles
                else 0,
            )
            if self.dialog.selected_profiles:
                for i, profile in enumerate(self.dialog.selected_profiles):
                    logger.debug(
                        "_collect_form_data: profile %s: name=%s, browser_key=%s",
                        i,
                        profile.get("name"),
                        profile.get("browser_key"),
                    )
        else:
            logger.debug("_collect_form_data: no selected_profiles attribute")

        logger.debug(
            "_collect_form_data: returning form_data with link_type=%s",
            form_data.get("link_type"),
        )
        return form_data
