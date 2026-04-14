"""Mixin handling browser profile selection inside `LinkDialogHandlers`."""

import logging

from PyQt6.QtWidgets import QDialog

logger = logging.getLogger(__name__)


class ProfilesMixin:
    def _on_profile(self) -> None:
        """Handle profile selection button."""
        try:
            from app.views.windows.dialogs.browser_profile_dialog import (
                BrowserProfileDialog,
            )
        except ImportError as exc:
            # Log root cause and show friendly message to user
            logger.error("BrowserProfileDialog unavailable: %s", exc)
            try:
                self.dialog.show_warning(
                    self.dialog.tr("Profile selection module is unavailable."),
                    self.dialog.tr("Browser profiles"),
                    informative_text=self.dialog.tr(
                        "Failed to load browser profile selection dialog. Ensure the component is installed and accessible."
                    ),
                    details=str(exc),
                )
            except (AttributeError, RuntimeError):
                # If show_warning is unavailable just exit quietly
                pass
            return

        dlg = BrowserProfileDialog(self.dialog)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.dialog.selected_profiles = dlg.get_selected_profiles()
            self.dialog._profiles_explicitly_changed = True
            logger.debug(
                f"_on_profile: got {len(self.dialog.selected_profiles) if self.dialog.selected_profiles else 0} selected profiles"
            )
            if self.dialog.selected_profiles:
                # Persist selected profiles
                for i, profile in enumerate(self.dialog.selected_profiles):
                    logger.debug(
                        f"_on_profile: profile {i}: name={profile.get('name')}, browser_key={profile.get('browser_key')}"
                    )

                profile_btn = self.dialog._get_profile_btn()
                profile_btn.setText(
                    self.dialog._format_profile_text(self.dialog.selected_profiles)
                )
