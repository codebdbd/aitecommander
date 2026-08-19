"""Mixin collecting form data for `LinkDialog`."""

import logging
from typing import Any

from app.models import LinkType

logger = logging.getLogger(__name__)


class FormDataMixin:
    def _build_form_data(self) -> dict[str, Any]:
        """Build form data from UI components."""
        return self._collect_form_data()

    def _collect_form_data(self) -> dict[str, Any]:
        """Collect data from the form widgets."""
        collected_name = self.dialog._get_name_le().text().strip()
        try:
            from app.models import LinkType as _LT
            if _LT.from_value(self.dialog.link_type) == _LT.WEB:
                _cb = self.dialog.ui.widgets.get("args_cb")
                if _cb is not None:
                    data = _cb.currentData()
                    collected_args = str(data) if data is not None else _cb.currentText().strip()
                else:
                    collected_args = ""
            else:
                collected_args = self.dialog._get_args_le().text().strip()
        except Exception:
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
            "profiles_explicitly_changed": bool(
                getattr(self.dialog, "_profiles_explicitly_changed", False)
            ),
            "link_id": collected_link_id,
            "last_used": self.dialog.link.get("last_used")
            if self.dialog.link
            else None,
            "position": self.dialog.link.get("position", 0) if self.dialog.link else 0,
            "_reparse_icon": bool(
                getattr(self.dialog, "_reparse_icon_requested", False)
            ),
        }

        handlers = getattr(self.dialog, "handlers", None)
        is_processing = bool(getattr(handlers, "_is_processing", False))
        has_active_worker = bool(getattr(handlers, "_active_worker", None))
        link_type = LinkType.from_value(self.dialog.link_type)
        if link_type in (LinkType.WEB, LinkType.PROGRAM, LinkType.FILE) and (
            is_processing or has_active_worker
        ):
            form_data["_defer_enrichment"] = True

        # Add selected profiles if present
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
