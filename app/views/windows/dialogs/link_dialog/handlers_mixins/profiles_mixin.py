"""Mixin handling browser profile selection inside `LinkDialogHandlers`."""

import logging

from PyQt6.QtWidgets import QDialog

logger = logging.getLogger(__name__)

# Try importing profile dialog at module load time.
# If dependency is missing or import fails, store the exception and fall back to a
# user-friendly mechanism when functionality is invoked.
try:  # keep import at top level to express dependency explicitly
    from app.views.windows.dialogs.browser_profile_dialog import (
        BrowserProfileDialog,  # type: ignore
    )

    _BPD_IMPORT_ERROR: Exception | None = None
except (
    ImportError
) as _e:  # keep module importable so other functionality remains available
    BrowserProfileDialog = None  # type: ignore[assignment]
    _BPD_IMPORT_ERROR = _e


class ProfilesMixin:
    def _on_profile(self) -> None:
        """Handle profile selection button."""
        if BrowserProfileDialog is None:
            # Log root cause and show friendly message to user
            logger.error("BrowserProfileDialog unavailable: %s", _BPD_IMPORT_ERROR)
            try:
                self.dialog.show_warning(
                    self.dialog.tr("Profile selection module is unavailable."),
                    self.dialog.tr("Browser profiles"),
                    informative_text=self.dialog.tr(
                        "Failed to load browser profile selection dialog. Ensure the component is installed and accessible."
                    ),
                    details=str(_BPD_IMPORT_ERROR) if _BPD_IMPORT_ERROR else None,
                )
            except (AttributeError, RuntimeError):
                # If show_warning is unavailable just exit quietly
                pass
            return

        dlg = BrowserProfileDialog(self.dialog)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.dialog.selected_profiles = dlg.get_selected_profiles()
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
