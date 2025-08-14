"""Конфигурация путей и директорий."""
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .base_config import BaseConfig


class PathConfig(BaseConfig):
    """Конфигурация путей к файлам и директориям."""
    
    def get_base_path(self) -> Path:
        """Базовый путь приложения (учитывает PyInstaller)."""
        if getattr(sys, 'frozen', False):
            return Path(sys._MEIPASS)
        else:
            return Path(__file__).parent.parent
    
    def get_ui_icons_dir(self) -> Path:
        """Директория UI-иконок, резолв конфиг-пути относительно base_path."""
        rel = self.get("settings.paths.ui_icons", "views/resources/ui_icons")
        p = Path(rel)
        return p if p.is_absolute() else self.get_base_path() / p

    def get_db_path(self) -> Path:
        """Путь к файлу базы данных в %APPDATA%/Org/App/links.db."""
        org_name = self.get("app.org_name", "Codebdbd")
        app_name = self.get("app.name", "Aite Commander")
        appdata = os.getenv('APPDATA')
        if not appdata:
            appdata = Path.home() / "AppData" / "Roaming"
        return Path(appdata) / org_name / app_name / "links.db"

    def get_link_icons_dir(self) -> Path:
        """Директория пользовательских иконок в %APPDATA%/Org/App/icons."""
        org_name = self.get("app.org_name", "Codebdbd")
        app_name = self.get("app.name", "Aite Commander")
        appdata = os.getenv('APPDATA')
        if not appdata:
            appdata = Path.home() / "AppData" / "Roaming"
        return Path(appdata) / org_name / app_name / "icons"

    def get_user_data_dir(self) -> Path:
        """Базовая директория данных пользователя (родитель файла БД)."""
        return self.get_db_path().parent

    def get_backups_dir(self) -> Path:
        """Директория автоматических резервных копий."""
        return self.get_user_data_dir() / "backups"

    def get_db_backup_path(self) -> Path:
        """Путь к одиночной резервной копии БД (links.db.bak)."""
        return self.get_user_data_dir() / "links.db.bak"

    def get_logs_dir(self) -> Path:
        """Директория логов пользователя."""
        return self.get_user_data_dir() / "logs"

    def get_config_dir(self) -> Path:
        """Директория конфигурации пользователя."""
        return self.get_user_data_dir() / "config"

    def ensure_user_data_dirs(self) -> None:
        """Создает необходимые пользовательские директории, если их нет."""
        base = self.get_user_data_dir()
        base.mkdir(parents=True, exist_ok=True)
        self.get_backups_dir().mkdir(parents=True, exist_ok=True)
        self.get_logs_dir().mkdir(parents=True, exist_ok=True)
        self.get_config_dir().mkdir(parents=True, exist_ok=True)
        self.get_link_icons_dir().mkdir(parents=True, exist_ok=True)

    # Ресурсы приложения (относительные пути резолвятся к base_path)

    def get_qss_path(self) -> str:
        """Строковый путь к директории QSS (как в конфиге)."""
        return self.get("settings.paths.qss", "views/resources/qss")

    def get_qss_dir(self) -> Path:
        """Директория QSS, резолв относительно base_path при необходимости."""
        rel = self.get("settings.paths.qss", "views/resources/qss")
        p = Path(rel)
        return p if p.is_absolute() else self.get_base_path() / p

    def get_themes_manifest_path(self) -> Path:
        """Путь к файлу манифеста тем, резолв относительно base_path при необходимости."""
        rel = self.get("paths.themes_manifest", "themes/manifest.json")
        p = Path(rel)
        return p if p.is_absolute() else self.get_base_path() / p
    
    # Пути профилей браузеров (Windows) — возвращаем Optional[Path]

    def get_chrome_profiles_dir(self) -> Optional[Path]:
        """Директория профилей Chrome или None."""
        localappdata = os.getenv('LOCALAPPDATA')
        if localappdata:
            chrome_path = Path(localappdata) / 'Google' / 'Chrome' / 'User Data'
            if chrome_path.exists():
                return chrome_path
        conf = self.get("paths.chrome_profiles_dir")
        if conf:
            p = Path(conf)
            return p if p.is_absolute() else self.get_base_path() / p
        return None

    def get_firefox_profiles_dir(self) -> Optional[Path]:
        """Директория профилей Firefox или None."""
        appdata = os.getenv('APPDATA', '')
        path = Path(appdata) / 'Mozilla' / 'Firefox'
        if appdata and path.exists():
            return path
        conf = self.get("paths.firefox_profiles_dir")
        if conf:
            p = Path(conf)
            return p if p.is_absolute() else self.get_base_path() / p
        return None

    def get_edge_profiles_dir(self) -> Optional[Path]:
        """Директория профилей Edge или None."""
        localappdata = os.getenv('LOCALAPPDATA', '')
        path = Path(localappdata) / 'Microsoft' / 'Edge' / 'User Data'
        if localappdata and path.exists():
            return path
        conf = self.get("paths.edge_profiles_dir")
        if conf:
            p = Path(conf)
            return p if p.is_absolute() else self.get_base_path() / p
        return None

    def get_brave_profiles_dir(self) -> Optional[Path]:
        """Директория профилей Brave или None."""
        localappdata = os.getenv('LOCALAPPDATA', '')
        path = Path(localappdata) / 'BraveSoftware' / 'Brave-Browser' / 'User Data'
        if localappdata and path.exists():
            return path
        conf = self.get("paths.brave_profiles_dir")
        if conf:
            p = Path(conf)
            return p if p.is_absolute() else self.get_base_path() / p
        return None

    def get_vivaldi_profiles_dir(self) -> Optional[Path]:
        """Директория профилей Vivaldi или None."""
        localappdata = os.getenv('LOCALAPPDATA', '')
        path = Path(localappdata) / 'Vivaldi' / 'User Data'
        if localappdata and path.exists():
            return path
        conf = self.get("paths.vivaldi_profiles_dir")
        if conf:
            p = Path(conf)
            return p if p.is_absolute() else self.get_base_path() / p
        return None

    def get_opera_profiles_dir(self) -> Optional[Path]:
        """Директория профилей Opera или None."""
        appdata = os.getenv('APPDATA', '')
        path = Path(appdata) / 'Opera Software' / 'Opera Stable'
        if appdata and path.exists():
            return path
        conf = self.get("paths.opera_profiles_dir")
        if conf:
            p = Path(conf)
            return p if p.is_absolute() else self.get_base_path() / p
        return None

    def get_yandex_profiles_dir(self) -> Optional[Path]:
        """Директория профилей Yandex или None."""
        localappdata = os.getenv('LOCALAPPDATA', '')
        path = Path(localappdata) / 'Yandex' / 'YandexBrowser' / 'User Data'
        if localappdata and path.exists():
            return path
        conf = self.get("paths.yandex_profiles_dir")
        if conf:
            p = Path(conf)
            return p if p.is_absolute() else self.get_base_path() / p
        return None
