"""
Миксин для работы с выбором браузерных профилей в LinkDialogHandlers.
"""
import logging
from PyQt6.QtWidgets import QDialog

logger = logging.getLogger(__name__)

# Пытаемся импортировать диалог профилей на этапе загрузки модуля.
# Если зависимость отсутствует или импорт завершается ошибкой, сохраняем
# исключение и используем дружелюбный запасной механизм при обращении к функционалу.
try:  # переносим импорт на верхний уровень для явного выражения зависимостей
    from app.views.dialogs.browser_profile_dialog import BrowserProfileDialog  # type: ignore
    _BPD_IMPORT_ERROR: Exception | None = None
except Exception as _e:  # не прерываем импорт модуля, чтобы остальной функционал был доступен
    BrowserProfileDialog = None  # type: ignore[assignment]
    _BPD_IMPORT_ERROR = _e


class ProfilesMixin:
    def _on_profile(self) -> None:
        """Обработчик кнопки выбора профиля."""
        if BrowserProfileDialog is None:
            # Логируем первопричину и показываем дружелюбное сообщение пользователю
            logger.error("BrowserProfileDialog недоступен: %s", _BPD_IMPORT_ERROR)
            try:
                # Показываем понятное сообщение, если у диалога есть такой метод
                self.dialog.show_warning(
                    "Модуль выбора профилей недоступен.",
                    "Профили браузера",
                    informative_text=(
                        "Не удалось загрузить диалог выбора профилей браузера."
                        " Убедитесь, что компонент установлен и доступен."
                    ),
                    details=str(_BPD_IMPORT_ERROR) if _BPD_IMPORT_ERROR else None,
                )
            except Exception:
                # На случай отсутствия show_warning просто тихо выходим
                pass
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

                profile_btn = self.dialog._get_profile_btn()
                profile_btn.setText(
                    self.dialog._format_profile_text(self.dialog.selected_profiles)
                )
