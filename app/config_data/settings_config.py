"""Application settings configuration helpers."""

from __future__ import annotations

import platform
from typing import Any

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication

from .base_config import BaseConfig

_TR_CONTEXT = "SettingsConfig"


def _tr(text: str) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text)


_DEFAULT_ABOUT_TITLE = QT_TRANSLATE_NOOP(_TR_CONTEXT, "About")
_DEFAULT_ABOUT_TEXT = QT_TRANSLATE_NOOP(
    _TR_CONTEXT, "Link Manager\nVersion 1.0\n\u00a9 MyCompany"
)
_DEFAULT_LINK_TYPES = [
    ["web", QT_TRANSLATE_NOOP(_TR_CONTEXT, "Web Link")],
    ["file", QT_TRANSLATE_NOOP(_TR_CONTEXT, "File")],
    ["program", QT_TRANSLATE_NOOP(_TR_CONTEXT, "Program")],
    ["script", QT_TRANSLATE_NOOP(_TR_CONTEXT, "Script")],
    ["folder", QT_TRANSLATE_NOOP(_TR_CONTEXT, "Folder")],
]
_DEFAULT_QUICK_TYPES = [
    ["web", "web_icon.png", QT_TRANSLATE_NOOP(_TR_CONTEXT, "Web Link")],
    ["script", "script_icon.png", QT_TRANSLATE_NOOP(_TR_CONTEXT, "Script")],
    ["file", "documents_icon.png", QT_TRANSLATE_NOOP(_TR_CONTEXT, "File")],
    ["program", "program_icon.png", QT_TRANSLATE_NOOP(_TR_CONTEXT, "Program")],
    ["folder", "folder_icon.png", QT_TRANSLATE_NOOP(_TR_CONTEXT, "Folder")],
]
_DEFAULT_QUICK_TYPE_TOOLTIPS = {
    "web": QT_TRANSLATE_NOOP(_TR_CONTEXT, "Web Link"),
    "script": QT_TRANSLATE_NOOP(_TR_CONTEXT, "Script"),
    "file": QT_TRANSLATE_NOOP(_TR_CONTEXT, "File"),
    "program": QT_TRANSLATE_NOOP(_TR_CONTEXT, "Program"),
    "folder": QT_TRANSLATE_NOOP(_TR_CONTEXT, "Folder"),
}


class SettingsConfig(BaseConfig):
    """Provide typed accessors for application settings and metadata."""

    # === Core application settings ===

    def get_app_name(self) -> str:
        """Return the application name."""
        return self.get("app.name", "Aite Commander")

    def get_org_name(self) -> str:
        """Return the organization name."""
        return self.get("app.org_name", "Codebdbd")

    def get_app_version(self) -> str:
        """Return the application version string."""
        # Prefer the new key ``app.version``; fall back to the legacy ``application.version``
        ver = self.get("app.version")
        if ver is None:
            ver = self.get("application.version", "1.1.0")
        return ver

    def is_debug_mode(self) -> bool:
        """Return whether debug mode is enabled."""
        return self.get("application.debug", False)

    def get_log_level(self) -> str:
        """Return the logging level name."""
        return self.get("application.log_level", "INFO")

    def get_about_title(self) -> str:
        """Return the title for the About dialog."""
        title = self.get("app.about_title")
        if title is None:
            title = self.get("application.about_title")
        return title if title is not None else _tr(_DEFAULT_ABOUT_TITLE)

    def get_about_text(self) -> str:
        """Return the body text for the About dialog."""
        text = self.get("app.about_text")
        if text is None:
            text = self.get("application.about_text")
        return text if text is not None else _tr(_DEFAULT_ABOUT_TEXT)

    # === Database ===

    def get_max_backups(self) -> int:
        """Return the maximum number of database backups to retain."""
        # Prefer ``limits.max_backups``; fall back to ``database.max_backups``
        val = self.get("limits.max_backups")
        if val is None:
            val = self.get("database.max_backups", 10)
        return val

    def is_backup_enabled(self) -> bool:
        """Return whether automatic backups are enabled."""
        return self.get("database.backup_enabled", True)

    def get_backup_interval_minutes(self) -> int:
        """Return the interval for automatic backups in minutes (default 30)."""
        val = self.get("database.backup_interval_minutes")
        if val is None:
            val = self.get("database.backup_interval", 30)
        return max(1, int(val))

    # === File formats and types ===

    def get_supported_icon_formats(self) -> list[str]:
        """Return the list of supported icon file extensions."""
        val = self.get("settings.supported_icon_formats")
        if val is None:
            val = self.get(
                "ui.supported_icon_formats",
                [
                    ".ico",
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".bmp",
                    ".gif",
                    ".svg",
                    ".svgz",
                    ".webp",
                ],
            )
        return list(val)

    def get_valid_themes(self) -> list[str]:
        """Return the list of acceptable UI themes."""
        val = self.get("settings.valid_themes")
        if val is None:
            val = self.get("ui.valid_themes", ["light", "dark"])
        return list(val)

    # === Link types ===

    def get_link_types(self) -> list[list[Any]]:
        """Return the list of link type descriptors."""
        val = self.get("settings.link_types")
        if val is None:
            val = self.get("ui.link_types")
        if val is None:
            val = _DEFAULT_LINK_TYPES
            return [[key, _tr(label)] for key, label in val]
        return [list(item) for item in val]

    def get_default_icons(self) -> dict:
        """Return the mapping of default icons per entity type."""
        val = self.get("settings.default_icons")
        if val is None:
            val = self.get(
                "ui.default_icons",
                {
                    "folder": "folder_icon.png",
                    "web": "web_icon.png",
                    "program": "program_icon.png",
                    "script": "script_icon.png",
                    "chrome": "chrome_icon.png",
                    "file": "documents_icon.png",
                    "category": "category.png",
                    "section": "section.png",
                    "ai": "ai_icon.png",
                    "work": "work_icon.png",
                    "study": "study_icon.png",
                    "personal": "personal_icon.png",
                },
            )
        return dict(val)

    def get_quick_types(self) -> list[list[Any]]:
        """Return the list of quick link type descriptors."""
        val = self.get("settings.quick_types")
        if val is None:
            val = self.get("ui.quick_types")
        if val is None:
            val = _DEFAULT_QUICK_TYPES
            return [[t, icon, _tr(label)] for t, icon, label in val]
        return [list(item) for item in val]

    def get_quick_type_tooltips(self) -> dict[str, str]:
        """Return tooltips for quick link types keyed by type name."""
        val = self.get("settings.quick_type_tooltips")
        if val is None:
            val = self.get("ui.quick_type_tooltips")
        if val is None:
            return {key: _tr(text) for key, text in _DEFAULT_QUICK_TYPE_TOOLTIPS.items()}
        return dict(val)

    def get_default_browse_paths(self) -> dict[str, str]:
        """Return default filesystem locations for browse dialogs."""
        val = self.get("settings.default_browse_paths")
        if val is None:
            val = self.get(
                "ui.default_browse_paths",
                {
                    "file": "%USERPROFILE%",
                    "folder": "",
                    "program": "%PROGRAMDATA%\\Microsoft\\Windows\\Start Menu\\Programs",
                    "script": "",
                },
            )
        return dict(val)

    # === Browser support ===

    def get_browser_profile_settings(self) -> dict[str, Any]:
        """Return configuration for browser profiles (raw mapping)."""
        val = self.get("settings.browser_profile_settings")
        if val is None:
            val = self.get(
                "ui.browser_profile_settings",
                {
                    "supported_browsers": [
                        "chrome",
                        "firefox",
                        "edge",
                        "brave",
                        "vivaldi",
                        "opera",
                        "yandex",
                    ]
                },
            )
        return dict(val)

    def get_supported_browsers(self) -> list[str]:
        """Return the list of supported browsers identifiers."""
        val = self.get("settings.browser_profile_settings.supported_browsers")
        if val is None:
            val = self.get(
                "ui.browser_profile_settings.supported_browsers",
                ["chrome", "firefox", "edge", "brave", "vivaldi", "opera", "yandex"],
            )
        return list(val)

    def get_browser_config(self) -> dict[str, Any]:
        """Return browser launch configuration for the current OS."""
        os_type = "windows" if platform.system() == "Windows" else "other"
        cfg = self.get(f"settings.browser_config.{os_type}")
        if cfg is None:
            cfg = self.get(f"ui.browser_config.{os_type}", {})
        return dict(cfg)

    # === MIME types ===

    def get_mime_types(self) -> dict[str, Any]:
        """Return the MIME type mapping configured for the app."""
        val = self.get("settings.mime_types")
        if val is None:
            val = self.get("ui.mime_types", {})
        return dict(val)

    def get_link_mime_type(self) -> str:
        """Return the MIME type string used for serialized links."""
        val = self.get("settings.mime_types.link")
        if val is None:
            val = self.get("ui.mime_types.link", "application/x-link-id")
        return val

    def get_category_mime_type(self) -> str:
        """Return the MIME type string used for categories."""
        val = self.get("settings.mime_types.category")
        if val is None:
            val = self.get("ui.mime_types.category", "application/x-category-id")
        return val

    # === Parser network settings / external services ===
    @property
    def ENABLE_CLOUDSCRAPER_FALLBACK(self) -> bool:
        """Flag enabling cloudscraper fallback in the parser HTTP client.

        Source: ``settings.enable_cloudscraper_fallback``; defaults to ``True``.
        Accessible via ``app_config.ENABLE_CLOUDSCRAPER_FALLBACK`` because of
        :meth:`AppConfig.__getattr__` delegation.
        """
        try:
            return bool(self.get("settings.enable_cloudscraper_fallback", True))
        except Exception:
            return True

    @property
    def REQUIRE_SUSPEND_UPDATES(self) -> bool:
        """Require ``suspend_updates`` for batch UI updates after theme changes.

        Source: ``settings.require_suspend_updates``; defaults to ``False``. When
        enabled and ``suspend_updates`` is unavailable, the theme controller logs
        an issue instead of performing potentially glitchy updates.
        """
        try:
            return bool(self.get("settings.require_suspend_updates", False))
        except Exception:
            return False

    # === Favicon cache file locking ===
    @property
    def FAVICON_LOCK_TIMEOUT(self) -> float:
        """Return the inter-process cache lock timeout in seconds (default 5.0)."""
        try:
            return float(self.get("settings.favicon_lock_timeout", 5.0))
        except Exception:
            return 5.0

    @property
    def FAVICON_LOCK_BACKEND(self) -> str:
        """Return the lock backend; one of ``auto`` | ``portalocker`` | ``filelock``."""
        try:
            v = self.get("settings.favicon_lock_backend", "auto")
            if not isinstance(v, str):
                return "auto"
            v = v.strip().lower()
            if v in {"auto", "portalocker", "filelock"}:
                return v
            return "auto"
        except Exception:
            return "auto"

    # === HTTP client retry parameters ===
    @property
    def HTTP_RETRIES(self) -> int:
        """Return the retry count for HTTP requests (default 2)."""
        try:
            v = int(self.get("settings.http_retries", 2))
            return max(0, v)
        except Exception:
            return 2

    @property
    def HTTP_RETRY_BACKOFF(self) -> float:
        """Return the exponential backoff factor for retries in seconds (default 0.5)."""
        try:
            v = float(self.get("settings.http_retry_backoff", 0.5))
            return max(0.0, v)
        except Exception:
            return 0.5

    @property
    def FAVICON_CACHE_PERSISTENT(self) -> bool:
        """Return whether to keep the shelve DB open for persistent favicon cache."""
        try:
            return bool(self.get("settings.favicon_cache_persistent", False))
        except Exception:
            return False

    @property
    def HTTP_POOL_CONNECTIONS(self) -> int:
        """Return ``pool_connections`` value for the HTTP adapter (default 10)."""
        try:
            v = int(self.get("settings.http_pool_connections", 10))
            return max(1, v)
        except Exception:
            return 10

    @property
    def HTTP_POOL_MAXSIZE(self) -> int:
        """Return ``pool_maxsize`` value for the HTTP adapter (default 20)."""
        try:
            v = int(self.get("settings.http_pool_maxsize", 20))
            return max(1, v)
        except Exception:
            return 20

    # === Favicon cache parameters ===
    def get_favicon_cache_max_size(self) -> int:
        """Return the persistent favicon cache capacity (default 5000 records)."""
        try:
            v = int(self.get("settings.favicon_cache_max_size", 5000))
            return max(1, v)
        except Exception:
            return 5000

    def get_favicon_cache_cleanup_interval(self) -> float:
        """Return the periodic cleanup interval in seconds (default 300, minimum 30)."""
        try:
            v = float(self.get("settings.favicon_cache_cleanup_interval", 300.0))
            return max(30.0, v)
        except Exception:
            return 300.0

    # === Internationalization ===

    def get_preferred_locale(self) -> str | None:
        """Return the preferred locale code (e.g., ``ru_RU``) or ``None``."""
        return self.get("settings.i18n.preferred_locale")

    def get_fallback_locale(self) -> str | None:
        """Return the fallback locale used when loading translations fails."""
        return self.get("settings.i18n.fallback_locale")

    def get_qt_translator_base(self) -> str | None:
        """Return the base name for Qt translation files (``.qm``)."""
        return self.get("settings.i18n.qt_translator_base")
