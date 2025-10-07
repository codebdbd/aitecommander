# app/settings.py

import logging

from PyQt6.QtCore import QSettings

from .config_data import app_config

logger = logging.getLogger(__name__)


class AppSettings:
    def __init__(self):
        # Store settings in INI format under the user's profile
        self._qs = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            app_config.get_org_name(),
            app_config.get_app_name(),
        )
        self.theme = self.get_theme()

    @staticmethod
    def _as_int(raw, default_value: int, key_name: str) -> int:
        """Safely cast a value to int with error logging.

        - Returns default_value if raw is None or empty string.
        - Logs a warning on failed cast.
        """
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            return int(default_value)
        try:
            return int(raw)
        except (ValueError, TypeError) as e:
            logger.warning(
                "AppSettings: invalid numeric value for '%s' (%r), using default: %s. Error: %s",
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
