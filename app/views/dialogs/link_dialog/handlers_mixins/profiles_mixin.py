"""
Миксин для работы с выбором браузерных профилей в LinkDialogHandlers.
"""
import logging
from PyQt6.QtWidgets import QDialog

logger = logging.getLogger(__name__)


class ProfilesMixin:
    def _on_profile(self) -> None:
        """Обработчик кнопки выбора профиля."""
        try:
            from app.views.dialogs.browser_profile_dialog import BrowserProfileDialog
        except Exception as e:
            logger.error("Не удалось импортировать BrowserProfileDialog: %s", e)
            return

        dlg = BrowserProfileDialog(self.dialog)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.dialog.selected_profiles = dlg.get_selected_profiles()
            logger.debug(
                f"_on_profile: got {len(self.dialog.selected_profiles) if self.dialog.selected_profiles else 0} selected profiles"
            )
            if self.dialog.selected_profiles:
                # Сохраняем выбранные профили
                for i, profile in enumerate(self.dialog.selected_profiles):
                    logger.debug(
                        f"_on_profile: profile {i}: name={profile.get('name')}, browser_key={profile.get('browser_key')}"
                    )

                profile_btn = self.dialog.ui.get_widget("profile_btn")
                profile_btn.setText(
                    self.dialog._format_profile_text(self.dialog.selected_profiles)
                )
