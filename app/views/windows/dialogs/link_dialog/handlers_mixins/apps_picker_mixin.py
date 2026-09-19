"""Mixin handling installed Windows applications selection inside `LinkDialogHandlers`."""

import logging
from pathlib import Path

from PyQt6.QtWidgets import QDialog

from app.utils.links.link_parser import parse_lnk
from app.utils.system.installed_apps_service import cache_app_icon
from app.utils.ui.icon.ui_helpers import set_icon_to_button
from app.views.windows.dialogs.installed_apps_dialog import InstalledAppsDialog

logger = logging.getLogger(__name__)


class AppsPickerMixin:
    """Mixin providing the installed applications picker for LinkDialog."""

    def _on_apps_picker(self) -> None:
        """Handle the "Apps..." button click to pick from installed Windows applications."""
        try:
            dlg = InstalledAppsDialog(self.dialog)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                app_info = dlg.get_selected_app()
                if not app_info:
                    return

                # 1. Set URL / Path field
                self.dialog.ui.set_widget_value("url_le", app_info.path)

                # 2. Set Name field if empty or default
                name_widget = self.dialog._get_name_le()
                if not name_widget.text().strip():
                    self.dialog.ui.set_widget_value("name_le", app_info.name)

                # 3. Extract and cache application icon
                icon_file = None
                try:
                    icon_file = cache_app_icon(app_info)
                    if icon_file and Path(icon_file).exists():
                        self.dialog.icon_name = Path(icon_file).name
                        set_icon_to_button(self.dialog._get_icon_btn(), icon_file)
                except Exception as icon_err:
                    logger.warning(
                        "Failed to apply icon for selected app '%s': %s",
                        app_info.name,
                        icon_err,
                    )
                self.dialog._processing_timer.stop()
                if not icon_file:
                    self.trigger_link_processing(app_info.path)

                # 4. If application has arguments, populate args field
                args_widget = self.dialog._get_args_le()
                if not args_widget.text().strip():
                    if getattr(app_info, "args", ""):
                        self.dialog.ui.set_widget_value("args_le", app_info.args)
                    elif app_info.path.lower().endswith(".lnk"):
                        try:
                            lnk_info = parse_lnk(app_info.path)
                            if lnk_info.get("args"):
                                self.dialog.ui.set_widget_value("args_le", lnk_info["args"])
                        except Exception as lnk_err:
                            logger.debug("Failed to parse shortcut arguments: %s", lnk_err)

        except Exception as e:
            logger.error("Error opening InstalledAppsDialog: %s", e, exc_info=True)
