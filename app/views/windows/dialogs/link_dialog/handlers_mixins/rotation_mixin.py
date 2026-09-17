"""Mixin handling Chrome profile rotation inside ``LinkDialogHandlers``."""

import logging

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QDialog

logger = logging.getLogger(__name__)

_TR_CONTEXT = "LinkDialogUI"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


class RotationMixin:
    """Handles the Chrome rotation checkbox and rotation profile selection."""

    def _on_rotation_toggled(self, checked: bool) -> None:
        """Handle Chrome rotation checkbox state change.

        When checked:
        - Disables the Profile button (not hidden — to preserve layout)
        - Shows the rotation profiles selection button
        - Clears any regular selected profiles

        When unchecked:
        - Re-enables the Profile button
        - Hides the rotation profiles button
        - Clears rotation profiles
        """
        profile_btn = self.dialog._get_profile_btn()
        rotation_btn = self.dialog._get_rotation_profiles_btn()

        if checked:
            profile_btn.setEnabled(False)
            if rotation_btn is not None:
                rotation_btn.setEnabled(True)
                self._update_rotation_btn_text(rotation_btn, self.dialog.rotation_profiles, self.dialog)
            # Clear regular profiles — rotation takes over
            self.dialog.selected_profiles = []
            if hasattr(self.dialog, "_update_profile_button_state"):
                self.dialog._update_profile_button_state()
            elif hasattr(self.dialog, "_format_profile_text"):
                profile_btn.setText(self.dialog._format_profile_text([]))
            else:
                profile_btn.setText(QCoreApplication.translate("LinkDialog", "Profile"))
        else:
            profile_btn.setEnabled(True)
            if hasattr(self.dialog, "_update_profile_button_state"):
                self.dialog._update_profile_button_state()
            if rotation_btn is not None:
                rotation_btn.setEnabled(False)
                self._update_rotation_btn_text(rotation_btn, [], self.dialog)
            # Clear rotation profiles
            self.dialog.rotation_profiles = []

    def _on_rotation_select_profiles(self) -> None:
        """Open profile selection dialog for rotation profiles."""
        try:
            from app.views.windows.dialogs.browser_profile_dialog import (
                BrowserProfileDialog,
            )
        except ImportError as exc:
            logger.error("BrowserProfileDialog unavailable: %s", exc)
            try:
                self.dialog.show_warning(
                    QCoreApplication.translate("ProfilesMixin", "Profile selection module is unavailable."),
                    QCoreApplication.translate("ProfilesMixin", "Browser profiles"),
                    informative_text=QCoreApplication.translate(
                        "ProfilesMixin",
                        "Failed to load browser profile selection dialog. Ensure the component is installed and accessible.",
                    ),
                    details=str(exc),
                )
            except (AttributeError, RuntimeError):
                pass
            return

        # Build initial selection keys from current rotation profiles
        initial_keys = set()
        try:
            from app.utils.browser.profile_selection_state import (
                profile_selection_key,
            )

            for profile in (self.dialog.rotation_profiles or []):
                key = profile_selection_key(profile)
                if key:
                    initial_keys.add(key)
        except Exception:
            pass

        dlg = BrowserProfileDialog(
            self.dialog,
            initial_selected_profile_keys=initial_keys,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            profiles = dlg.get_selected_profiles()
            self.dialog.rotation_profiles = profiles

            rotation_btn = self.dialog._get_rotation_profiles_btn()
            if rotation_btn is not None:
                self._update_rotation_btn_text(rotation_btn, profiles, self.dialog)

            logger.debug(
                "_on_rotation_select_profiles: selected %d profiles for rotation",
                len(profiles) if profiles else 0,
            )

    @staticmethod
    def _format_rotation_text(profiles: list[dict]) -> str:
        """Format display text for rotation profiles button."""
        count = len(profiles) if profiles else 0
        if count == 0:
            return _tr("Profiles")
        return _tr("Profiles ({count})").format(count=count)

    @staticmethod
    def _format_rotation_tooltip(profiles: list[dict]) -> str:
        """Format detailed tooltip for rotation profiles button."""
        if not profiles:
            return _tr("Select profiles for rotation")
        names = [p.get("name") or p.get("email") or p.get("directory", "?") for p in profiles]
        lines = [_tr("Rotation order ({count}):").format(count=len(names))]
        for idx, n in enumerate(names, 1):
            lines.append(f"{idx}. {n}")
        lines.append(_tr("(Click to change)"))
        return "\n".join(lines)

    @classmethod
    def _update_rotation_btn_text(cls, btn, profiles: list[dict], dialog=None) -> None:
        """Update rotation profiles button text and tooltip based on selection."""
        if btn is None:
            return
        btn.setText(cls._format_rotation_text(profiles))
        btn.setToolTip(cls._format_rotation_tooltip(profiles))
        if dialog and hasattr(dialog, "ui") and hasattr(dialog.ui, "adjust_button_width"):
            dialog.ui.adjust_button_width(btn)
