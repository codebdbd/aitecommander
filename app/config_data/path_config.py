"""Конфигурация путей и директорий."""

import os
import sys
from pathlib import Path
from typing import Optional

from .base_config import BaseConfig


class PathConfig(BaseConfig):
    """Конфигурация путей к файлам и директориям."""

    def get_base_path(self) -> Path:
        """Базовый путь приложения (учитывает PyInstaller)."""
        if getattr(sys, "frozen", False):
            base = getattr(sys, "_MEIPASS", None)
            try:
                return Path(str(base))
            except Exception:
                # Fallback на директорию проекта, если PyInstaller переменная недоступна
                return Path(__file__).parent.parent
        else:
            return Path(__file__).parent.parent

    def get_ui_icons_dir(self) -> Path:
        """Директория UI-иконок, резолв конфиг-пути относительно base_path."""
        # Новый ключ: paths.ui_icons_dir; обратная совместимость: settings.paths.ui_icons
        rel = self.get("paths.ui_icons_dir")
        if rel is None:
            rel = self.get("settings.paths.ui_icons", "views/resources/ui_icons")
        p = Path(rel)
        return p if p.is_absolute() else self.get_base_path() / p

    def __get_appdata_subpath(self, sub: str) -> Path:
        """Вычисляет поддиректорию в %APPDATA%/org_name/app_name/sub.

        Извлекает org_name и app_name из конфигурации, находит APPDATA
        (или использует Path.home()/"AppData"/"Roaming" как запасной вариант)
        и возвращает итоговый путь.
        """
        org_name = self.get("app.org_name", "Codebdbd")
        app_name = self.get("app.name", "Aite Commander")
        appdata_env = os.getenv("APPDATA")
        if appdata_env:
            root = Path(appdata_env)
        else:
            root = Path.home() / "AppData" / "Roaming"
        return root / org_name / app_name / sub

    def get_db_path(self) -> Path:
        """Путь к файлу базы данных в %APPDATA%/Org/App/links.db."""
        return self.__get_appdata_subpath("links.db")

    def get_link_icons_dir(self) -> Path:
        """Директория пользовательских иконок в %APPDATA%/Org/App/icons."""
        # Разрешаем переопределение через paths.user_icons_dir (относительно user_data_dir)
        conf = self.get("paths.user_icons_dir")
        if conf:
            p = Path(conf)
            return p if p.is_absolute() else self.get_user_data_dir() / p
        return self.__get_appdata_subpath("icons")

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
        # Поддержка конфигурационного переопределения
        conf = self.get("paths.logs_dir")
        if conf:
            p = Path(conf)
            return p if p.is_absolute() else self.get_user_data_dir() / p
        return self.get_user_data_dir() / "logs"

    def get_config_dir(self) -> Path:
        """Директория конфигурации пользователя."""
        # Поддержка конфигурационного переопределения
        conf = self.get("paths.config_dir")
        if conf:
            p = Path(conf)
            return p if p.is_absolute() else self.get_user_data_dir() / p
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
        # Новый ключ: paths.qss_dir; обратная совместимость: settings.paths.qss
        val = self.get("paths.qss_dir")
        if val is None:
            val = self.get("settings.paths.qss", "views/resources/qss")
        return val

    def get_qss_dir(self) -> Path:
        """Директория QSS, резолв относительно base_path при необходимости."""
        # Новый ключ: paths.qss_dir; обратная совместимость: settings.paths.qss
        rel = self.get("paths.qss_dir")
        if rel is None:
            rel = self.get("settings.paths.qss", "views/resources/qss")
        p = Path(rel)
        return p if p.is_absolute() else self.get_base_path() / p

    # Пути профилей браузеров (Windows) — возвращаем Optional[Path]

    # Универсальный справочник параметров профилей браузеров
    # key: имя браузера, value: (ENV_VAR, относительный путь от ENV, ключ конфига)
    __BROWSER_PARAMS = {
        "chrome": (
            "LOCALAPPDATA",
            Path("Google") / "Chrome" / "User Data",
            "paths.chrome_profiles_dir",
        ),
        "firefox": (
            "APPDATA",
            Path("Mozilla") / "Firefox",
            "paths.firefox_profiles_dir",
        ),
        "edge": (
            "LOCALAPPDATA",
            Path("Microsoft") / "Edge" / "User Data",
            "paths.edge_profiles_dir",
        ),
        "brave": (
            "LOCALAPPDATA",
            Path("BraveSoftware") / "Brave-Browser" / "User Data",
            "paths.brave_profiles_dir",
        ),
        "vivaldi": (
            "LOCALAPPDATA",
            Path("Vivaldi") / "User Data",
            "paths.vivaldi_profiles_dir",
        ),
        "opera": (
            "APPDATA",
            Path("Opera Software") / "Opera Stable",
            "paths.opera_profiles_dir",
        ),
        "yandex": (
            "LOCALAPPDATA",
            Path("Yandex") / "YandexBrowser" / "User Data",
            "paths.yandex_profiles_dir",
        ),
    }

    def __get_browser_dir(
        self, env_var: str, vendor_path: Path, config_key: str
    ) -> Optional[Path]:
        """Универсальный резолвер директории профилей браузера.

        Порядок: ENV[env_var] -> ENV/vendor_path если существует -> конфиг по ключу config_key
        (относительный путь резолвится от base_path).
        """
        root = os.getenv(env_var, "")
        if root:
            candidate = Path(root) / vendor_path
            if candidate.exists():
                return candidate
        conf = self.get(config_key)
        if conf:
            p = Path(conf)
            return p if p.is_absolute() else self.get_base_path() / p
        return None

    def get_browser_profiles_dir(self, browser: str) -> Optional[Path]:
        """Возвращает директорию профилей указанного браузера или None.

        Допустимые значения browser: ключи из справочника `__BROWSER_PARAMS`
        ("chrome", "firefox", "edge", "brave", "vivaldi", "opera", "yandex").

        Для обратной совместимости специализированные методы `get_*_profiles_dir`
        делегируют в этот универсальный метод.
        """
        params = self.__BROWSER_PARAMS.get(browser)
        if not params:
            return None
        env, vendor, key = params
        return self.__get_browser_dir(env, vendor, key)

    def get_chrome_profiles_dir(self) -> Optional[Path]:
        """Директория профилей Chrome или None (обертка над get_browser_profiles_dir)."""
        return self.get_browser_profiles_dir("chrome")

    def get_firefox_profiles_dir(self) -> Optional[Path]:
        """Директория профилей Firefox или None (обертка над get_browser_profiles_dir)."""
        return self.get_browser_profiles_dir("firefox")

    def get_edge_profiles_dir(self) -> Optional[Path]:
        """Директория профилей Edge или None (обертка над get_browser_profiles_dir)."""
        return self.get_browser_profiles_dir("edge")

    def get_brave_profiles_dir(self) -> Optional[Path]:
        """Директория профилей Brave или None (обертка над get_browser_profiles_dir)."""
        return self.get_browser_profiles_dir("brave")

    def get_vivaldi_profiles_dir(self) -> Optional[Path]:
        """Директория профилей Vivaldi или None (обертка над get_browser_profiles_dir)."""
        return self.get_browser_profiles_dir("vivaldi")

    def get_opera_profiles_dir(self) -> Optional[Path]:
        """Директория профилей Opera или None (обертка над get_browser_profiles_dir)."""
        return self.get_browser_profiles_dir("opera")

    def get_yandex_profiles_dir(self) -> Optional[Path]:
        """Директория профилей Yandex или None (обертка над get_browser_profiles_dir)."""
        return self.get_browser_profiles_dir("yandex")
