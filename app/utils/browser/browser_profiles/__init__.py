"""
Универсальная система работы с профилями браузеров.

Основные компоненты:
- BrowserProfileManager: Центральный менеджер для всех браузеров
- UniversalProfileProcessor: Обработка профилей для создания ссылок
- BaseBrowserProfileFinder: Базовый интерфейс для поиска профилей
- Конкретные реализации для каждого браузера

Использование:
    from app.utils.browser.browser_profiles import BrowserProfileManager
    
    manager = BrowserProfileManager()
    all_profiles = manager.get_all_profiles()
    chrome_profiles = manager.get_browser_profiles('chrome')
"""

from typing import Dict, List

from .base_profile_finder import BaseBrowserProfileFinder
from .chromium_base_finder import (
    BraveProfileFinder,
    ChromeProfileFinder,
    ChromiumBaseBrowserFinder,
    EdgeProfileFinder,
    VivaldiProfileFinder,
)
from .firefox_profile_finder import FirefoxProfileFinder
from .migration_helper import ProfileMigrationHelper
from .profile_manager import BrowserProfileManager
from .universal_profile_processor import UniversalProfileProcessor
from .validator import BrowserProfileValidator

__all__ = [
    'BrowserProfileManager',
    'UniversalProfileProcessor', 
    'BaseBrowserProfileFinder',
    'ChromeProfileFinder',
    'FirefoxProfileFinder',
    'EdgeProfileFinder',
    'BraveProfileFinder',
    'VivaldiProfileFinder',
    'ProfileMigrationHelper',
    'BrowserProfileValidator',
    'BrowserProfileDevTools'
]
