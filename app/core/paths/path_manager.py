"""Standalone path resolver for application resources and user data."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_RESOURCES_SUBDIR = "resources"
_CONFIG_DATA_SUBDIR = "config_data"
_UI_ICONS_SUBDIR = "ui_icons"
_QSS_SUBDIR = "qss"
_THEMES_SUBDIR = "themes"
_LOGO_SUBDIR = "logo"
_LOGO_FILE_NAME = "logo.png"

_USER_ICONS_SUBDIR = "icons"
_USER_THEMES_SUBDIR = "themes"
_USER_LOGS_SUBDIR = "logs"
_USER_BACKUPS_SUBDIR = "backups"
_DB_FILE_NAME = "links.db"
_DB_BACKUP_FILE_NAME = "links.db.bak"


class PathManager:
    """Centralized, dependency-free path accessors."""

    DEFAULT_ORG_NAME = "Codebdbd"
    DEFAULT_APP_NAME = "Aite Commander"
    APP_DIR_NAME = "app"

    @classmethod
    def base_root(cls) -> Path:
        """Return base root for resolving the app root."""
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)  # type: ignore[attr-defined]
        return Path(__file__).parents[3]

    @classmethod
    def app_root(cls) -> Path:
        """Return the root directory of the application package."""
        base = cls.base_root()
        app_dir = base / cls.APP_DIR_NAME
        return app_dir if app_dir.exists() else base

    @classmethod
    def resources_root(cls) -> Path:
        """Return the bundled resources root."""
        return cls.app_root() / _RESOURCES_SUBDIR

    @classmethod
    def config_data_root(cls) -> Path:
        """Return the config_data directory."""
        return cls.app_root() / _CONFIG_DATA_SUBDIR

    @classmethod
    def ui_icons_dir(cls) -> Path:
        """Return the UI icons directory."""
        return cls.resources_root() / _UI_ICONS_SUBDIR

    @classmethod
    def qss_dir(cls) -> Path:
        """Return the QSS themes directory."""
        return cls.resources_root() / _QSS_SUBDIR

    @classmethod
    def themes_dir(cls) -> Path:
        """Return the bundled themes directory."""
        return cls.resources_root() / _THEMES_SUBDIR

    @classmethod
    def logo_dir(cls) -> Path:
        """Return the logo directory under resources."""
        return cls.resources_root() / _LOGO_SUBDIR

    @classmethod
    def logo_file(cls) -> Path:
        """Return the default logo file path."""
        return cls.logo_dir() / _LOGO_FILE_NAME

    @classmethod
    def get_resource_path(cls, relative_path: str | Path) -> Path:
        """Return a resolved path under the resources root."""
        p = Path(relative_path)
        if p.is_absolute():
            return p
        return cls.resources_root() / p

    @classmethod
    def user_data_root(
        cls,
        org_name: str | None = None,
        app_name: str | None = None,
    ) -> Path:
        """Return user data root (%APPDATA%/Org/App)."""
        org = org_name or cls.DEFAULT_ORG_NAME
        app = app_name or cls.DEFAULT_APP_NAME
        appdata_str = os.getenv("APPDATA")
        if not appdata_str:
            appdata_path = Path.home() / "AppData" / "Roaming"
        else:
            appdata_path = Path(appdata_str)
        return appdata_path / org / app

    @classmethod
    def get_app_data_path(
        cls,
        relative_path: str | Path | None = None,
        org_name: str | None = None,
        app_name: str | None = None,
    ) -> Path:
        """Return a path under the user data root."""
        base = cls.user_data_root(org_name, app_name)
        if relative_path is None:
            return base
        return base / Path(relative_path)

    @classmethod
    def user_icons_dir(
        cls,
        org_name: str | None = None,
        app_name: str | None = None,
    ) -> Path:
        """Return user icons directory."""
        return cls._resolve_user_subdir(_USER_ICONS_SUBDIR, org_name, app_name)

    @classmethod
    def user_themes_dir(
        cls,
        org_name: str | None = None,
        app_name: str | None = None,
    ) -> Path:
        """Return user themes directory."""
        return cls._resolve_user_subdir(_USER_THEMES_SUBDIR, org_name, app_name)

    @classmethod
    def logs_dir(
        cls,
        org_name: str | None = None,
        app_name: str | None = None,
    ) -> Path:
        """Return logs directory."""
        return cls._resolve_user_subdir(_USER_LOGS_SUBDIR, org_name, app_name)

    @classmethod
    def backups_dir(
        cls,
        org_name: str | None = None,
        app_name: str | None = None,
    ) -> Path:
        """Return backups directory."""
        return cls._resolve_user_subdir(_USER_BACKUPS_SUBDIR, org_name, app_name)

    @classmethod
    def db_path(
        cls,
        org_name: str | None = None,
        app_name: str | None = None,
    ) -> Path:
        """Return user database file path."""
        return cls._resolve_user_subdir(_DB_FILE_NAME, org_name, app_name)

    @classmethod
    def db_backup_path(
        cls,
        org_name: str | None = None,
        app_name: str | None = None,
    ) -> Path:
        """Return user database backup file path."""
        return cls._resolve_user_subdir(_DB_BACKUP_FILE_NAME, org_name, app_name)

    @staticmethod
    def as_str(path: Path) -> str:
        """Return path as string for APIs that require str."""
        return str(path)

    @classmethod
    def _resolve_user_subdir(
        cls,
        name: str,
        org_name: str | None,
        app_name: str | None,
    ) -> Path:
        return cls.user_data_root(org_name, app_name) / name
