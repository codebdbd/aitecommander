"""Mixin handling browser profile selection inside `LinkDialogHandlers`."""

import logging

from PyQt6.QtWidgets import QDialog

from app.models.types.link_type import LinkType
from app.utils.browser.profile_selection_state import (
    load_last_web_link_profile_keys,
    profile_selection_key,
    save_last_web_link_profile_keys,
)

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

        initial_keys = self._initial_profile_selection_keys()
        dlg = BrowserProfileDialog(
            self.dialog,
            initial_selected_profile_keys=initial_keys,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.dialog.selected_profiles = dlg.get_selected_profiles()
            self.dialog._profiles_explicitly_changed = True
            if self._is_web_link_dialog():
                save_last_web_link_profile_keys(self.dialog.selected_profiles)
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

    def _initial_profile_selection_keys(self) -> set[str]:
        current_profiles = getattr(self.dialog, "selected_profiles", []) or []
        current_keys = {profile_selection_key(profile) for profile in current_profiles}
        current_keys = {key for key in current_keys if key}
        if current_keys:
            return current_keys
        if self._is_web_link_dialog():
            return load_last_web_link_profile_keys()
        return set()

    def _is_web_link_dialog(self) -> bool:
        try:
            return (
                LinkType.from_value(getattr(self.dialog, "link_type", "web"))
                == LinkType.WEB
            )
        except Exception:
            return False
