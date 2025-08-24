# app/settings.py

from PyQt6.QtCore import QSettings

from .config_data import app_config


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

    def get_theme(self) -> str:
        return self._qs.value("Appearance/Theme", "light")

    def set_theme(self, theme: str):
        self._qs.setValue("Appearance/Theme", theme)
        self.theme = theme

    def get_max_backups(self) -> int:
        default_value = app_config.get_max_backups()
        return int(self._qs.value("Backup/MaxCopies", default_value))

    def set_max_backups(self, count: int):
        self._qs.setValue("Backup/MaxCopies", count)

    def get_font_size(self) -> int:
        default_value = app_config.get_default_font_size()
        return int(self._qs.value("UI/FontSize", default_value))

    def set_font_size(self, size: int):
        self._qs.setValue("UI/FontSize", size)

    def get_dpi_scale(self) -> int:
        return int(self._qs.value("UI/DPIScale", 100))

    def set_dpi_scale(self, pct: int):
        self._qs.setValue("UI/DPIScale", pct)

    def get_hotkey(self, action: str, default: str) -> str:
        return self._qs.value(f"Hotkeys/{action}", default)

    def set_hotkey(self, action: str, sequence: str):
        self._qs.setValue(f"Hotkeys/{action}", sequence)
