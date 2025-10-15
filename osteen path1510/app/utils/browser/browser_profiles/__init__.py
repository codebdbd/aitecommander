"""
Universal browser profile system.

Main components:
- BrowserProfileManager: Central manager for all browsers
- UniversalProfileProcessor: Profile processing for link creation
- BaseBrowserProfileFinder: Base interface for profile finding
- Concrete implementations for each browser

Usage:
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
from .persistent_cache import PersistentProfileCache
from .profile_manager import BrowserProfileManager, get_profile_manager
from .universal_profile_processor import UniversalProfileProcessor

__all__ = [
    "BrowserProfileManager",
    "get_profile_manager",
    "PersistentProfileCache",
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
