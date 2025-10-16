# app/settings.py

import logging

from PyQt6.QtCore import QSettings

from .config_data import app_config

logger = logging.getLogger(__name__)


class AppSettings:
    def __init__(self):
        # Хранение настроек в формате INI в профиле пользователя
        self._qs = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            app_config.get_org_name(),
            app_config.get_app_name(),
        )
        self.theme = self.get_theme()

    @staticmethod
    def _as_int(raw, default_value: int, key_name: str) -> int:
        """Безопасно привести значение к int с логированием при ошибке.

        - Возвращает default_value, если raw None или пустая строка.
        - Логирует предупреждение при неудачном касте.
        """
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            return int(default_value)
        try:
            return int(raw)
        except (ValueError, TypeError) as e:
            logger.warning(
                "AppSettings: некорректное числовое значение для '%s' (%r), используется по умолчанию: %s. Ошибка: %s",
                key_name,
                raw,
                default_value,
                e,
            )
            return int(default_value)

    def get_theme(self) -> str:
        return self._qs.value("Appearance/Theme", "light")

    def set_theme(self, theme: str):
        self._qs.setValue("Appearance/Theme", theme)
        self.theme = theme

    def get_max_backups(self) -> int:
        default_value = app_config.get_max_backups()
        raw = self._qs.value("Backup/MaxCopies", default_value)
        return self._as_int(raw, default_value, "Backup/MaxCopies")

    def set_max_backups(self, count: int):
        self._qs.setValue("Backup/MaxCopies", count)

    def get_font_size(self) -> int:
        default_value = app_config.get_default_font_size()
        raw = self._qs.value("UI/FontSize", default_value)
        return self._as_int(raw, default_value, "UI/FontSize")

    def set_font_size(self, size: int):
        self._qs.setValue("UI/FontSize", size)

    def get_dpi_scale(self) -> int:
        default_value = 100
        raw = self._qs.value("UI/DPIScale", default_value)
        return self._as_int(raw, default_value, "UI/DPIScale")

    def set_dpi_scale(self, pct: int):
        self._qs.setValue("UI/DPIScale", pct)

    def get_hotkey(self, action: str, default: str) -> str:
        return self._qs.value(f"Hotkeys/{action}", default)

    def set_hotkey(self, action: str, sequence: str):
        self._qs.setValue(f"Hotkeys/{action}", sequence)
