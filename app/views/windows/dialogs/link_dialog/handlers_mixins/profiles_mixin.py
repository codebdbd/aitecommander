"""Mixin handling browser profile modes and selection inside `LinkDialogHandlers`."""

import logging
from typing import Any

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QDialog

from app.models.types.link_type import LinkType
from app.utils.browser.profile_selection_state import (
    load_last_web_link_profile_keys,
    profile_selection_key,
    save_last_web_link_profile_keys,
)

logger = logging.getLogger(__name__)


class ProfilesMixin:
    def init_profile_modes(self) -> None:
        """Initialize profile line edit and UI state."""
        profile_le = getattr(self.dialog, "_get_profile_le", lambda: None)()
        if profile_le is not None:
            try:
                profile_le.textChanged.connect(self._on_profile_text_changed)
            except Exception:
                pass
        self._update_profile_ui_state()

    def _on_profile_text_changed(self, text: str) -> None:
        """Handle clearing the profile line edit via its clear button."""
        if not text:
            self.dialog.profile_mode = "none"
            self.dialog.selected_profiles = []
            self.dialog.rotation_profiles = []
            self.dialog._profiles_explicitly_changed = True
            self._update_profile_ui_state()

    def sync_profile_mode_to_ui(self) -> None:
        """Synchronize dialog.profile_mode to the UI states."""
        self._update_profile_ui_state()

    def _on_select_profile_clicked(self) -> None:
        """Open profile selection dialog."""
        self._open_profile_dialog()

    def _open_profile_dialog(self) -> None:
        """Open BrowserProfileDialog."""
        try:
            from app.views.windows.dialogs.browser_profile_dialog import (
                BrowserProfileDialog,
            )
        except ImportError as exc:
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
            except Exception:
                pass
            return

        current_mode = getattr(self.dialog, "profile_mode", "none")
        target_mode = "single" if current_mode == "none" else current_mode

        if target_mode == "rotation":
            profiles = getattr(self.dialog, "rotation_profiles", [])
        else:
            profiles = getattr(self.dialog, "selected_profiles", [])

        initial_keys = {profile_selection_key(p) for p in (profiles or []) if p}
        if not initial_keys and self._is_web_link_dialog():
            initial_keys = self._initial_profile_selection_keys()

        dlg = BrowserProfileDialog(
            self.dialog,
            initial_selected_profile_keys=initial_keys,
            mode="single" if target_mode == "single" else "multi",
            allow_mode_change=True,
            profile_mode=target_mode,
            allow_batch=True,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            results = dlg.get_selected_profiles()
            chosen_mode = dlg.get_profile_mode()
            self.dialog.profile_mode = chosen_mode
            self.dialog._profiles_explicitly_changed = True

            if chosen_mode == "single":
                self.dialog.selected_profiles = results[:1]
                self.dialog.rotation_profiles = []
                if self._is_web_link_dialog() and self.dialog.selected_profiles:
                    save_last_web_link_profile_keys(self.dialog.selected_profiles)
            elif chosen_mode == "rotation":
                self.dialog.rotation_profiles = results
                self.dialog.selected_profiles = []
            elif chosen_mode == "batch":
                self.dialog.selected_profiles = results
                self.dialog.rotation_profiles = []

            self._update_profile_ui_state()

    def _update_profile_ui_state(self) -> None:
        """Update line edit, button text, and tooltips based on current profile mode and selections."""
        mode = getattr(self.dialog, "profile_mode", "none")
        btn = getattr(self.dialog, "_get_profile_select_btn", lambda: None)()
        le = getattr(self.dialog, "_get_profile_le", lambda: None)()

        if btn is not None:
            btn.setEnabled(True)
            btn.setText(QCoreApplication.translate("LinkDialogUI", "Select"))
            btn.setToolTip(
                QCoreApplication.translate("LinkDialogUI", "Select browser profile")
            )
            if hasattr(self.dialog, "ui") and hasattr(self.dialog.ui, "adjust_button_width"):
                self.dialog.ui.adjust_button_width(btn)

        if le is None:
            return

        le.blockSignals(True)
        if mode == "none":
            le.clear()
            le.setToolTip("")
        elif mode == "single":
            profiles = getattr(self.dialog, "selected_profiles", [])
            if profiles:
                p = profiles[0]
                b_name = (p.get("browser_key") or "Browser").title()
                p_name = p.get("name") or p.get("email") or p.get("directory", "?")
                display_text = f"{b_name}: {p_name}"
                le.setText(display_text)
                le.setToolTip(f"{b_name} - {p_name}")
            else:
                le.clear()
                le.setToolTip("")
        elif mode == "rotation":
            profiles = getattr(self.dialog, "rotation_profiles", [])
            count = len(profiles)
            if count == 0:
                le.clear()
                le.setToolTip("")
            else:
                rot_title = QCoreApplication.translate("LinkDialogUI", "Rotation")
                le.setText(f"{rot_title} ({count})")
                names = [
                    f"{(p.get('browser_key') or 'Browser').title()}: {p.get('name') or p.get('email') or p.get('directory', '?')}"
                    for p in profiles
                ]
                lines = [
                    QCoreApplication.translate(
                        "LinkDialogUI", "Rotation order ({count}):"
                    ).format(count=len(names))
                ]
                for idx, n in enumerate(names, 1):
                    lines.append(f"{idx}. {n}")
                le.setToolTip("\n".join(lines))
        elif mode == "batch":
            profiles = getattr(self.dialog, "selected_profiles", [])
            count = len(profiles)
            if count == 0:
                le.clear()
                le.setToolTip("")
            else:
                batch_title = QCoreApplication.translate(
                    "LinkDialogUI", "Create for each profile"
                )
                le.setText(f"{batch_title} ({count})")
                names = [
                    f"{(p.get('browser_key') or 'Browser').title()}: {p.get('name') or p.get('email') or p.get('directory', '?')}"
                    for p in profiles
                ]
                lines = [
                    QCoreApplication.translate(
                        "LinkDialogUI", "Selected profiles ({count}):"
                    ).format(count=len(names))
                ]
                for n in names:
                    lines.append(f"• {n}")
                le.setToolTip("\n".join(lines))
        le.blockSignals(False)

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
