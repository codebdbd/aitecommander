"""
Универсальная система работы с профилями браузеров.

Основные компоненты:
- BrowserProfileManager: Центральный менеджер для всех браузеров
- UniversalProfileProcessor: Обработка профилей для создания ссылок
- BaseBrowserProfileFinder: Базовый интерфейс для поиска профилей
- Конкретные реализации для каждого браузера

Использование:
    from app.utils.browser.browser_profiles import get_profile_manager

    manager = get_profile_manager()
    all_profiles = manager.get_all_profiles()
    chrome_profiles = manager.get_browser_profiles('chrome')
"""

from .base_profile_finder import BaseBrowserProfileFinder
from .chromium_base_finder import (
    BraveProfileFinder,
    ChromeProfileFinder,
    ChromiumBaseBrowserFinder,
    EdgeProfileFinder,
    VivaldiProfileFinder,
)
from .firefox_profile_finder import FirefoxProfileFinder
from .profile_manager import BrowserProfileManager, get_profile_manager
from .universal_profile_processor import UniversalProfileProcessor

__all__ = [
    "BrowserProfileManager",
    "get_profile_manager",
    "UniversalProfileProcessor",
    "BaseBrowserProfileFinder",
    "ChromeProfileFinder",
    "FirefoxProfileFinder",
    "EdgeProfileFinder",
    "BraveProfileFinder",
    "VivaldiProfileFinder",
    "ChromiumBaseBrowserFinder",
    "BrowserProfileDevTools",
]
