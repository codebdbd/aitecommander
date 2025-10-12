"""
Central manager for working with profiles of all browsers.
"""

import logging
from typing import Optional

from .base_profile_finder import BaseBrowserProfileFinder
from .chromium_base_finder import (
    BraveProfileFinder,
    ChromeProfileFinder,
    EdgeProfileFinder,
    OperaProfileFinder,
    VivaldiProfileFinder,
    YandexProfileFinder,
)
from .firefox_profile_finder import FirefoxProfileFinder
from .persistent_cache import PersistentProfileCache
from .utils import get_browser_display_name

logger = logging.getLogger(__name__)


class BrowserProfileManager:
    def get_profiles_by_browser(self, browser_key: str):
        """
        Returns list of profiles for specified browser.
        """
        finder = self.finders.get(browser_key)
        if not finder:
            return []
        try:
            profiles = self._get_cached_profiles(browser_key)
            # If somehow returned not a list but a dictionary — take values
            if isinstance(profiles, dict):
                return list(profiles.values())
            return profiles or []
        except Exception:
            return []

    def get_supported_browsers(self):
        """Returns list of supported browsers in format [{'key': ..., 'name': ...}, ...]"""
        # Get list of supported browsers from configuration
        try:
            from app.config_data import app_config

            supported_browsers = app_config.get_supported_browsers()
            return [
                {"key": key, "name": get_browser_display_name(finder, key)}
                for key, finder in self.finders.items()
                if key in supported_browsers
            ]
        except Exception:
            # fallback if configuration is unavailable
            return [
                {"key": key, "name": get_browser_display_name(finder, key)}
                for key, finder in self.finders.items()
            ]

    """Universal manager for working with profiles of all browsers."""

    def __init__(self):
        """Initialization of manager with support for all browsers."""
        self.finders: dict[str, BaseBrowserProfileFinder] = {
            "chrome": ChromeProfileFinder(),
            "firefox": FirefoxProfileFinder(),
            "edge": EdgeProfileFinder(),
            "brave": BraveProfileFinder(),
            "vivaldi": VivaldiProfileFinder(),
            "opera": OperaProfileFinder(),
            "yandex": YandexProfileFinder(),
        }

        # Unified profile cache: persistent JSON + TTL
        self.cache = PersistentProfileCache(default_ttl=self._get_cache_timeout())

        logger.info("Initialized profile manager for %s browsers", len(self.finders))

        # Persistent cache loads data from disk during initialization

    def _get_cache_timeout(self) -> int:
        """Gets cache timeout from configuration."""
        try:
            from app.config_data import app_config

            settings = app_config.get_browser_profile_settings()
            return settings.get("cache_timeout", 300)
        except ImportError:
            return 300  # 5 minutes by default

    def get_all_profiles(self) -> dict[str, list[dict]]:
        """Gets profiles of all browsers."""

        all_profiles = {}

        for browser_key, _finder in self.finders.items():
            try:
                profiles = self._get_cached_profiles(browser_key)
                if profiles:
                    all_profiles[browser_key] = profiles
            except Exception as e:
                logger.error("Error searching profiles for %s: %s", browser_key, e)

        return all_profiles

    def get_browser_profiles(self, browser_key: str) -> list[dict]:
        """Gets profiles of specific browser."""
        if browser_key not in self.finders:
            return []
        return self._get_cached_profiles(browser_key)

    def _get_cached_profiles(self, browser_key: str) -> list[dict]:
        """Gets profiles with caching.

        First tries to return from cache (without freshness check), if absent —
        performs loading via finder and updates cache.
        """
        logger.debug("_get_cached_profiles: browser_key=%s", browser_key)

        # Try to get from cache
        cached = self.cache.get(browser_key)
        if cached is not None:
            return cached

        # Loading and updating cache
        finder = self.finders.get(browser_key)
        if finder:
            try:
                profiles = finder.find_profiles()
                self.cache.set(browser_key, profiles)
                return profiles
            except Exception as e:
                logger.error("Error getting profiles for %s: %s", browser_key, e)

        return []

    def get_cached_profiles(self, browser_key: str) -> Optional[list[dict]]:
        """Returns profiles from cache only if they are fresh (TTL); doesn't block loading."""
        return self.cache.get(browser_key)

    def get_available_browsers(self) -> list[dict[str, str]]:
        """Gets list of available browsers with profiles."""
        available = []

        for browser_key, finder in self.finders.items():
            try:
                profiles = self._get_cached_profiles(browser_key)
                if profiles:
                    available.append(
                        {
                            "key": browser_key,
                            "name": get_browser_display_name(finder, browser_key),
                            "profile_count": len(profiles),
                        }
                    )
            except Exception as e:
                logger.debug("Browser %s unavailable: %s", browser_key, e)

        return available

    def detect_browser_from_args(self, args: str) -> Optional[str]:
        """Detects browser from command line arguments."""
        logger.debug("detect_browser_from_args: args=%s", args)

        if not args:
            logger.debug("detect_browser_from_args: no args provided")
            return None

        for browser_key, finder in self.finders.items():
            logger.debug("detect_browser_from_args: trying browser_key=%s", browser_key)
            try:
                profile_data = finder.parse_profile_from_args(args)
                logger.debug(
                    "detect_browser_from_args: profile_data for %s=%s",
                    browser_key,
                    profile_data,
                )
                if profile_data:
                    logger.debug(
                        "detect_browser_from_args: detected browser_key=%s",
                        browser_key,
                    )
                    return browser_key
            except Exception as e:
                logger.debug(
                    "Error detecting browser %s from arguments: %s",
                    browser_key,
                    e,
                )
                continue

        logger.debug("detect_browser_from_args: could not detect browser")
        return None

    def clear_cache(self):
        """Clears profile cache."""
        self.cache.clear()
        logger.info("Profile cache cleared")

    def update_profiles_bulk(self, data: dict[str, list[dict]]) -> None:
        """Bulk updates profile cache for multiple browsers.

        Argument `data` — dictionary of form {browser_key: [profiles...]}
        Data immediately goes to persistent cache via public API `PersistentProfileCache.set`.
        """
        if not isinstance(data, dict):
            return
        try:
            # Use context for guaranteed disk flush
            with self.cache:
                for key, profiles in data.items():
                    if not isinstance(key, str):
                        continue
                    try:
                        self.cache.set(key, profiles)
                    except Exception:
                        # Don't spoil general update due to one failed write
                        continue
        except Exception:
            # Safe fallback: do nothing
            pass


# Module singleton for reusing one manager instance
_PROFILE_MANAGER: Optional[BrowserProfileManager] = None


def get_profile_manager() -> BrowserProfileManager:
    """
    Returns common BrowserProfileManager instance for entire application.
    Guarantees single initialization per process.
    """
    global _PROFILE_MANAGER
    if _PROFILE_MANAGER is None:
        _PROFILE_MANAGER = BrowserProfileManager()
    return _PROFILE_MANAGER
