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
            text = self.get("application.about_text", "Link Manager\nВерсия 1.0\n© MyCompany")
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
        return self.get("settings.supported_icon_formats", [
            ".ico", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".svg", ".svgz", ".webp"
        ])

    def get_valid_themes(self) -> list:
        """Получение списка допустимых тем оформления."""
        return self.get("settings.valid_themes", ["light", "dark"])
    
    # === Типы ссылок ===

    def get_link_types(self) -> list:
        """Получение справочника поддерживаемых типов ссылок."""
        return self.get("settings.link_types", [
            ["web", "Веб-ссылка"],
            ["file", "Файл"],
            ["program", "Программа"],
            ["script", "Скрипт"],
            ["chromeapp", "Chrome App"],
            ["folder", "Папка"]
        ])

    def get_default_icons(self) -> dict:
        """Получение иконок по умолчанию для различных типов элементов."""
        return self.get("settings.default_icons", {
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
            "personal": "personal_icon.png"
        })

    def get_quick_types(self) -> list:
        """Получение списка быстрых типов ссылок."""
        return self.get("settings.quick_types", [
            ["web", "web_icon.png", "Веб-ссылка"],
            ["file", "documents_icon.png", "Файл"],
            ["program", "program_icon.png", "Программа"],
            ["script", "script_icon.png", "Скрипт"],
            ["chromeapp", "chrome_icon.png", "Chrome App"]
        ])

    def get_quick_type_tooltips(self) -> dict:
        """Получение подсказок для быстрых типов ссылок."""
        return self.get("settings.quick_type_tooltips", {
            "web": "Веб-ссылка",
            "file": "Файл",
            "program": "Программа",
            "script": "Скрипт",
            "chromeapp": "Chrome App"
        })
    
    def get_default_browse_paths(self) -> dict:
        """Получение путей по умолчанию для диалогов выбора файлов/папок."""
        return self.get("settings.default_browse_paths", {
            "file": "%USERPROFILE%",
            "folder": "",
            "program": "%PROGRAMDATA%\\Microsoft\\Windows\\Start Menu\\Programs",
            "script": "",
            "chromeapp": "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Приложения Chrome"
        })
    
    # === Браузеры ===

    def get_browser_profile_settings(self) -> dict:
        """Получение настроек профилей браузеров."""
        return self.get("settings.browser_profile_settings", {
            "supported_browsers": [
                "chrome", "firefox", "edge", "brave", 
                "vivaldi", "opera", "yandex"
            ]
        })
    
    def get_supported_browsers(self) -> list:
        """Получение списка поддерживаемых браузеров."""
        return self.get("settings.browser_profile_settings.supported_browsers", [
            "chrome", "firefox", "edge", "brave", 
            "vivaldi", "opera", "yandex"
        ])
    
    def get_browser_config(self) -> dict:
        """Получение конфигурации браузеров для текущей ОС."""
        os_type = "windows" if platform.system() == "Windows" else "other"
        return self.get(f"settings.browser_config.{os_type}", {})
    
    # === MIME типы ===
    
    def get_mime_types(self) -> dict:
        """Получение MIME-типов приложения."""
        return self.get("settings.mime_types", {})
    
    def get_link_mime_type(self) -> str:
        """Получение MIME-типа для ссылок."""
        return self.get("settings.mime_types.link", "application/x-link-id")
    
    def get_category_mime_type(self) -> str:
        """Получение MIME-типа для категорий."""
        return self.get("settings.mime_types.category", "application/x-category-id")
