"""Mixin handling user icon selection in `LinkDialogHandlers`."""

import logging
from pathlib import Path

from PyQt6.QtGui import QIcon

from app.models import LinkType
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.selection import choose_icon_and_copy
from app.utils.ui.icon.ui_helpers import set_icon_to_button

logger = logging.getLogger(__name__)


class IconsMixin:
    def _on_choose_icon(self) -> None:
        """Open icon picker immediately; cancel resets to the type default."""
        user_icons_dir = self.dialog.get_user_icons_dir()
        # Filter is built dynamically via app_config.get_supported_icon_formats()
        fname, icon = choose_icon_and_copy(self.dialog, user_icons_dir)
        if not fname or not icon:
            self._reset_icon_to_default()
            return

        self.dialog.icon_name = fname
        btn = self.dialog._get_icon_btn()
        btn.setIcon(icon if icon else QIcon())

    def _reset_icon_to_default(self) -> None:
        """Reset to the default icon for the current link type."""
        self.dialog.icon_name = ""
        link_type = LinkType.from_value(self.dialog.link_type)
        try:
            default_path = resolve_icon_for_link(
                {"type": link_type.value, "icon_path": ""}
            )
        except Exception:
            logger.debug("Failed to resolve the default link icon", exc_info=True)
            default_path = ""

        button = self.dialog._get_icon_btn()
        if default_path and Path(default_path).exists():
            set_icon_to_button(button, default_path)
        else:
            button.setIcon(QIcon())
