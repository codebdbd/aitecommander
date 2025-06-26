# app/settings.py

from PyQt6.QtCore import QSettings
from app.config import ORG_NAME, APP_NAME

class AppSettings:
    def __init__(self):
        # Хранение настроек в формате INI в профиле пользователя
        self._qs = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            ORG_NAME,
            APP_NAME
        )

    def get_theme(self) -> str:
        return self._qs.value("Appearance/Theme", "light")

    def set_theme(self, theme: str):
        self._qs.setValue("Appearance/Theme", theme)

    def get_autosave_interval(self) -> int:
        return int(self._qs.value("Backup/Interval", 5))

    def set_autosave_interval(self, minutes: int):
        self._qs.setValue("Backup/Interval", minutes)

    def get_max_backups(self) -> int:
        return int(self._qs.value("Backup/MaxCopies", 1))

    def set_max_backups(self, count: int):
        self._qs.setValue("Backup/MaxCopies", count)

    def get_dpi_scale(self) -> int:
        return int(self._qs.value("UI/DPIScale", 100))

    def set_dpi_scale(self, pct: int):
        self._qs.setValue("UI/DPIScale", pct)

    def get_hotkey(self, action: str, default: str) -> str:
        return self._qs.value(f"Hotkeys/{action}", default)

    def set_hotkey(self, action: str, sequence: str):
        self._qs.setValue(f"Hotkeys/{action}", sequence)
