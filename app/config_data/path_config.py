"""Configuration helpers for file system paths and directories."""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from app.core.paths.path_manager import PathManager

from .base_config import BaseConfig

logger = logging.getLogger(__name__)


class PathConfig(BaseConfig):
    """Provide strongly typed accessors for application path settings."""

    def get_base_path(self) -> Path:
        """Return the application base path."""
        return PathManager.app_root()

    def get_ui_icons_dir(self) -> Path:
        """Return the directory containing UI icons relative to ``base_path``."""
        # New key: ``paths.ui_icons_dir``; backwards compatibility: ``settings.paths.ui_icons``
        rel = self.get("paths.ui_icons_dir")
        if rel is None:
            rel = self.get("settings.paths.ui_icons", "resources/ui_icons")
        p = Path(rel)
        return p if p.is_absolute() else self.get_base_path() / p

    def __get_appdata_subpath(self, sub: str) -> Path:
        """Compute `%APPDATA%/org_name/app_name/sub` incorporating fallbacks."""
        org_name = self.get("app.org_name", PathManager.DEFAULT_ORG_NAME)
        app_name = self.get("app.name", PathManager.DEFAULT_APP_NAME)
        return PathManager.user_data_root(org_name, app_name) / sub

    def get_db_path(self) -> Path:
        """Return the `%APPDATA%/Org/App/links.db` database path."""
        return self.__get_appdata_subpath("links.db")

    def get_link_icons_dir(self) -> Path:
        """Return the user icon directory under `%APPDATA%/Org/App/icons`."""
        # Allow overrides via ``paths.user_icons_dir`` (relative to ``user_data_dir``)
        conf = self.get("paths.user_icons_dir")
        if conf:
            p = Path(conf)
            return p if p.is_absolute() else self.get_user_data_dir() / p
        return self.__get_appdata_subpath("icons")

    def get_user_themes_dir(self) -> Path:
        """Return the user themes directory (default `%APPDATA%/Codebdbd/Aite Commander/themes`)."""
        conf = self.get("paths.user_themes_dir")
        if conf:
            expanded = os.path.expandvars(str(conf))
            p = Path(expanded)
            return p if p.is_absolute() else self.get_user_data_dir() / p
        return self.__get_appdata_subpath("themes")

    def get_user_data_dir(self) -> Path:
        """Return the root user data directory (the database file's parent)."""
        return self.get_db_path().parent

    def get_backups_dir(self) -> Path:
        """Return the directory used for automatic backups."""
        return self.get_user_data_dir() / "backups"

    def get_db_backup_path(self) -> Path:
        """Return the path to the standalone ``links.db.bak`` backup file."""
        return self.get_user_data_dir() / "links.db.bak"

    def get_logs_dir(self) -> Path:
        """Return the directory used for user logs."""
        # Support configuration overrides
        conf = self.get("paths.logs_dir")
        if conf:
            p = Path(conf)
            return p if p.is_absolute() else self.get_user_data_dir() / p
        return self.get_user_data_dir() / "logs"

    def get_config_dir(self) -> Path:
        """Return the directory that stores user configuration files."""
        # Support configuration overrides
        conf = self.get("paths.config_dir")
        if conf:
            p = Path(conf)
            return p if p.is_absolute() else self.get_user_data_dir() / p
        return self.get_user_data_dir() / "config"

    def ensure_user_data_dirs(self) -> None:
        """Ensure all required user-facing directories exist."""
        base = self.get_user_data_dir()
        base.mkdir(parents=True, exist_ok=True)
        self.get_backups_dir().mkdir(parents=True, exist_ok=True)
        self.get_logs_dir().mkdir(parents=True, exist_ok=True)
        self.get_config_dir().mkdir(parents=True, exist_ok=True)
        self.get_link_icons_dir().mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_user_themes_dir()
        self.get_user_themes_dir().mkdir(parents=True, exist_ok=True)

    def _get_legacy_user_themes_dir(self) -> Path:
        """Return the legacy themes directory (%APPDATA%/AiteCommander/themes)."""
        appdata_str = os.getenv("APPDATA")
        if not appdata_str:
            appdata_path = Path.home() / "AppData" / "Roaming"
        else:
            appdata_path = Path(appdata_str)
        return appdata_path / "AiteCommander" / "themes"

    def _migrate_legacy_user_themes_dir(self) -> None:
        """Move themes from legacy folder into the current profile-based location."""
        legacy_dir = self._get_legacy_user_themes_dir()
        new_dir = self.get_user_themes_dir()
        if legacy_dir.resolve() == new_dir.resolve():
            return
        if not legacy_dir.exists() or not legacy_dir.is_dir():
            return
        try:
            new_dir.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Failed to create themes parent folder: %s", exc)
            return

        try:
            if new_dir.exists():
                for entry in legacy_dir.iterdir():
                    dest = new_dir / entry.name
                    if dest.exists():
                        continue
                    shutil.move(str(entry), str(dest))
            else:
                shutil.move(str(legacy_dir), str(new_dir))
            try:
                if legacy_dir.exists():
                    legacy_dir.rmdir()
            except OSError:
                pass
        except OSError as exc:
            logger.warning("Failed to migrate legacy themes: %s", exc)

    # Application resources (relative paths are resolved against ``base_path``)

    def get_qss_path(self) -> str:
        """Return the QSS directory path as configured."""
        # New key: ``paths.qss_dir``; backwards compatibility: ``settings.paths.qss``
        val = self.get("paths.qss_dir")
        if val is None:
            val = self.get("settings.paths.qss", "resources/qss")
        return val

    def get_qss_dir(self) -> Path:
        """Return the QSS directory, resolving relative paths against ``base_path``."""
        # New key: ``paths.qss_dir``; backwards compatibility: ``settings.paths.qss``
        rel = self.get("paths.qss_dir")
        if rel is None:
            rel = self.get("settings.paths.qss", "resources/qss")
        p = Path(rel)
        return p if p.is_absolute() else self.get_base_path() / p

    def get_themes_dir(self) -> Path:
        """Return the bundled themes directory (theme.json manifests)."""
        rel = self.get("paths.themes_dir", "resources/themes")
        p = Path(rel)
        return p if p.is_absolute() else self.get_base_path() / p

    # Browser profile paths (Windows) - each accessor returns ``Optional[Path]``

    # Universal registry of browser profile parameters
    # key: browser name, value: (ENV_VAR, relative path from ENV, config key)
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
        """Resolve a browser profile directory using environment variables and config.

        Lookup order: ``ENV[env_var]`` -> ``ENV/vendor_path`` (if existing) -> configuration
        value referenced by ``config_key``. Relative paths are resolved against ``base_path``.
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
        """Return the profile directory for the requested browser or ``None``.

        Accepted values for ``browser`` are the keys defined in ``__BROWSER_PARAMS``:
        ``"chrome"``, ``"firefox"``, ``"edge"``, ``"brave"``, ``"vivaldi"``,
        ``"opera"``, ``"yandex"``. Specialized ``get_*_profiles_dir`` methods are
        thin wrappers around this universal resolver for backward compatibility.
        """
        params = self.__BROWSER_PARAMS.get(browser)
        if not params:
            return None
        env, vendor, key = params
        return self.__get_browser_dir(env, vendor, key)

    def get_chrome_profiles_dir(self) -> Optional[Path]:
        """Return Chrome profile directory or ``None`` (wrapper over ``get_browser_profiles_dir``)."""
        return self.get_browser_profiles_dir("chrome")

    def get_firefox_profiles_dir(self) -> Optional[Path]:
        """Return Firefox profile directory or ``None`` (wrapper over ``get_browser_profiles_dir``)."""
        return self.get_browser_profiles_dir("firefox")

    def get_edge_profiles_dir(self) -> Optional[Path]:
        """Return Edge profile directory or ``None`` (wrapper over ``get_browser_profiles_dir``)."""
        return self.get_browser_profiles_dir("edge")

    def get_brave_profiles_dir(self) -> Optional[Path]:
        """Return Brave profile directory or ``None`` (wrapper over ``get_browser_profiles_dir``)."""
        return self.get_browser_profiles_dir("brave")

    def get_vivaldi_profiles_dir(self) -> Optional[Path]:
        """Return Vivaldi profile directory or ``None`` (wrapper over ``get_browser_profiles_dir``)."""
        return self.get_browser_profiles_dir("vivaldi")

    def get_opera_profiles_dir(self) -> Optional[Path]:
        """Return Opera profile directory or ``None`` (wrapper over ``get_browser_profiles_dir``)."""
        return self.get_browser_profiles_dir("opera")

    def get_yandex_profiles_dir(self) -> Optional[Path]:
        """Return Yandex profile directory or ``None`` (wrapper over ``get_browser_profiles_dir``)."""
        return self.get_browser_profiles_dir("yandex")
