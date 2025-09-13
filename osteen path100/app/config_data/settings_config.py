"""
Конфигурация настроек приложения.
"""

import platform

from .base_config import BaseConfig


class SettingsConfig(BaseConfig):
    """Конфигурация настроек и параметров приложения."""

    # === Основные настройки приложения ===

    def get_app_name(self) -> str:
        """Получение названия приложения."""
        return self.get("app.name", "Aite Commander")

    def get_org_name(self) -> str:
        """Получение названия организации."""
        return self.get("app.org_name", "Codebdbd")

    def get_app_version(self) -> str:
        """Получение версии приложения."""
        # Предпочитаем новый ключ: app.version; обратная совместимость: application.version
        ver = self.get("app.version")
        if ver is None:
            ver = self.get("application.version", "1.0.0")
        return ver

    def is_debug_mode(self) -> bool:
        """Получение признака режима отладки."""
        return self.get("application.debug", False)

    def get_log_level(self) -> str:
        """Получение уровня логирования."""
        return self.get("application.log_level", "INFO")

    def get_about_title(self) -> str:
        """Получение заголовка диалога 'О программе'."""
        # Предпочитаем новый ключ: app.about_title; обратная совместимость: application.about_title
        title = self.get("app.about_title")
        if title is None:
            title = self.get("application.about_title", "О программе")
        return title

    def get_about_text(self) -> str:
        """Получение текста диалога 'О программе'."""
        # Предпочитаем новый ключ: app.about_text; обратная совместимость: application.about_text
        text = self.get("app.about_text")
        if text is None:
            text = self.get(
                "application.about_text", "Link Manager\nВерсия 1.0\n© MyCompany"
            )
        return text

    # === База данных ===

    def get_max_backups(self) -> int:
        """Получение максимального количества резервных копий базы данных."""
        # Новый источник: limits.max_backups; обратная совместимость: database.max_backups
        val = self.get("limits.max_backups")
        if val is None:
            val = self.get("database.max_backups", 10)
        return val

    def is_backup_enabled(self) -> bool:
        """Получение признака включения резервного копирования."""
        return self.get("database.backup_enabled", True)

    # === Форматы и типы файлов ===

    def get_supported_icon_formats(self) -> list:
        """Получение списка поддерживаемых форматов файлов иконок."""
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
        return val

    def get_valid_themes(self) -> list:
        """Получение списка допустимых тем оформления."""
        val = self.get("settings.valid_themes")
        if val is None:
            val = self.get("ui.valid_themes", ["light", "dark"])
        return val

    # === Типы ссылок ===

    def get_link_types(self) -> list:
        """Получение справочника поддерживаемых типов ссылок."""
        val = self.get("settings.link_types")
        if val is None:
            val = self.get(
                "ui.link_types",
                [
                    ["web", "Веб-ссылка"],
                    ["file", "Файл"],
                    ["program", "Программа"],
                    ["script", "Скрипт"],
                    ["chromeapp", "Chrome App"],
                    ["folder", "Папка"],
                ],
            )
        return val

    def get_default_icons(self) -> dict:
        """Получение иконок по умолчанию для различных типов элементов."""
        val = self.get("settings.default_icons")
        if val is None:
            val = self.get(
                "ui.default_icons",
                {
                    "default": "default.ico",
                    "folder": "folder_icon.png",
                    "web": "web_icon.png",
                    "program": "program_icon.png",
                    "script": "script_icon.png",
                    "chrome": "chrome_icon.png",
                    "chromeapp": "chrome_icon.png",
                    "file": "documents_icon.png",
                    "category": "category.png",
                    "section": "section.png",
                    "ai": "ai_icon.png",
                    "work": "work_icon.png",
                    "study": "study_icon.png",
                    "personal": "personal_icon.png",
                },
            )
        return val

    def get_quick_types(self) -> list:
        """Получение списка быстрых типов ссылок."""
        val = self.get("settings.quick_types")
        if val is None:
            val = self.get(
                "ui.quick_types",
                [
                    ["web", "web_icon.png", "Веб-ссылка"],
                    ["file", "documents_icon.png", "Файл"],
                    ["program", "program_icon.png", "Программа"],
                    ["script", "script_icon.png", "Скрипт"],
                    ["chromeapp", "chrome_icon.png", "Chrome App"],
                ],
            )
        return val

    def get_quick_type_tooltips(self) -> dict:
        """Получение подсказок для быстрых типов ссылок."""
        val = self.get("settings.quick_type_tooltips")
        if val is None:
            val = self.get(
                "ui.quick_type_tooltips",
                {
                    "web": "Веб-ссылка",
                    "file": "Файл",
                    "program": "Программа",
                    "script": "Скрипт",
                    "chromeapp": "Chrome App",
                },
            )
        return val

    def get_default_browse_paths(self) -> dict:
        """Получение путей по умолчанию для диалогов выбора файлов/папок."""
        val = self.get("settings.default_browse_paths")
        if val is None:
            val = self.get(
                "ui.default_browse_paths",
                {
                    "file": "%USERPROFILE%",
                    "folder": "",
                    "program": "%PROGRAMDATA%\\Microsoft\\Windows\\Start Menu\\Programs",
                    "script": "",
                    "chromeapp": "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Приложения Chrome",
                },
            )
        return val

    # === Браузеры ===

    def get_browser_profile_settings(self) -> dict:
        """Получение настроек профилей браузеров."""
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
        return val

    def get_supported_browsers(self) -> list:
        """Получение списка поддерживаемых браузеров."""
        val = self.get("settings.browser_profile_settings.supported_browsers")
        if val is None:
            val = self.get(
                "ui.browser_profile_settings.supported_browsers",
                ["chrome", "firefox", "edge", "brave", "vivaldi", "opera", "yandex"],
            )
        return val

    def get_browser_config(self) -> dict:
        """Получение конфигурации браузеров для текущей ОС."""
        os_type = "windows" if platform.system() == "Windows" else "other"
        cfg = self.get(f"settings.browser_config.{os_type}")
        if cfg is None:
            cfg = self.get(f"ui.browser_config.{os_type}", {})
        return cfg

    # === MIME типы ===

    def get_mime_types(self) -> dict:
        """Получение MIME-типов приложения."""
        val = self.get("settings.mime_types")
        if val is None:
            val = self.get("ui.mime_types", {})
        return val

    def get_link_mime_type(self) -> str:
        """Получение MIME-типа для ссылок."""
        val = self.get("settings.mime_types.link")
        if val is None:
            val = self.get("ui.mime_types.link", "application/x-link-id")
        return val

    def get_category_mime_type(self) -> str:
        """Получение MIME-типа для категорий."""
        val = self.get("settings.mime_types.category")
        if val is None:
            val = self.get("ui.mime_types.category", "application/x-category-id")
        return val

    # === Сетевые настройки парсера / внешние сервисы ===
    @property
    def ENABLE_CLOUDSCRAPER_FALLBACK(self) -> bool:
        """Глобальный флаг: разрешать ли fallback на cloudscraper в HTTP-клиенте парсера.

        Источник: settings.enable_cloudscraper_fallback (bool), по умолчанию True.
        Доступен как атрибут у app_config благодаря делегированию __getattr__.
        """
        try:
            return bool(self.get("settings.enable_cloudscraper_fallback", True))
        except Exception:
            return True

    @property
    def REQUIRE_SUSPEND_UPDATES(self) -> bool:
        """Требовать ли suspend_updates для пакетных UI-обновлений после смены темы.

        Источник: settings.require_suspend_updates (bool), по умолчанию False.
        Если True и утилита suspend_updates недоступна, ThemeController не будет выполнять
        массовые обновления (чтобы не вызывать визуальные артефакты), а лишь залогирует проблему.
        """
        try:
            return bool(self.get("settings.require_suspend_updates", False))
        except Exception:
            return False

    # === Параметры файловой блокировки кэша фавиконок ===
    @property
    def FAVICON_LOCK_TIMEOUT(self) -> float:
        """Таймаут межпроцессной блокировки кэша (секунды). По умолчанию 5.0."""
        try:
            return float(self.get("settings.favicon_lock_timeout", 5.0))
        except Exception:
            return 5.0

    @property
    def FAVICON_LOCK_BACKEND(self) -> str:
        """Бэкенд блокировки: 'auto'|'portalocker'|'filelock'. По умолчанию 'auto'."""
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

    # === HTTP клиент: параметры ретраев ===
    @property
    def HTTP_RETRIES(self) -> int:
        """Количество повторов HTTP-запроса (Retry.total/connect/read). По умолчанию 2."""
        try:
            v = int(self.get("settings.http_retries", 2))
            return max(0, v)
        except Exception:
            return 2

    @property
    def HTTP_RETRY_BACKOFF(self) -> float:
        """Коэффициент экспоненциального бэкоффа для Retry (сек). По умолчанию 0.5."""
        try:
            v = float(self.get("settings.http_retry_backoff", 0.5))
            return max(0.0, v)
        except Exception:
            return 0.5

    @property
    def HTTP_RETRY_ON_STATUS(self) -> bool:
        """Включать ли ретраи по статусам 429/5xx (по умолчанию False)."""
        try:
            return bool(self.get("settings.http_retry_on_status", False))
        except Exception:
            return False

    @property
    def HTTP_POOL_CONNECTIONS(self) -> int:
        """Размер пула базовых соединений адаптера (pool_connections). По умолчанию 10."""
        try:
            v = int(self.get("settings.http_pool_connections", 10))
            return max(1, v)
        except Exception:
            return 10

    @property
    def HTTP_POOL_MAXSIZE(self) -> int:
        """Максимум соединений в пуле (pool_maxsize). По умолчанию 20."""
        try:
            v = int(self.get("settings.http_pool_maxsize", 20))
            return max(1, v)
        except Exception:
            return 20

    # === FaviconCache параметры ===
    def get_favicon_cache_max_size(self) -> int:
        """Максимальный размер persistent-кэша фавиконок (кол-во записей). По умолчанию 5000."""
        try:
            v = int(self.get("settings.favicon_cache_max_size", 5000))
            return max(1, v)
        except Exception:
            return 5000

    def get_favicon_cache_cleanup_interval(self) -> float:
        """Интервал периодической очистки (сек). По умолчанию 300.0 (5 минут). Минимум 30 секунд."""
        try:
            v = float(self.get("settings.favicon_cache_cleanup_interval", 300.0))
            return max(30.0, v)
        except Exception:
            return 300.0

    @property
    def FAVICON_CACHE_PERSISTENT(self) -> bool:
        """Включить постоянное соединение с shelve (держать БД открытой). По умолчанию False."""
        try:
            return bool(self.get("settings.favicon_cache_persistent", False))
        except Exception:
            return False
