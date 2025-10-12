#!/usr/bin/env python3
"""
Asynchronous browser profile manager with background loading support.
"""

import logging
import time
from typing import Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from .profile_manager import BrowserProfileManager, get_profile_manager

logger = logging.getLogger(__name__)


class ProfileLoadWorkerSignals(QObject):
    """Signals for profile loading worker."""

    # Signals for one browser
    browser_profiles_loaded = pyqtSignal(str, list)  # browser_key, profiles
    browser_load_error = pyqtSignal(str, str)  # browser_key, error_message
    # Signals for all browsers
    all_profiles_loaded = pyqtSignal(dict)  # {browser_key: profiles}
    all_profiles_progress = pyqtSignal(str, int, int)  # current_browser, current, total
    all_profiles_error = pyqtSignal(str)  # error_message

    # Global instance for convenience
    available_browsers_loaded = pyqtSignal(list)  # available_browsers
    available_browsers_error = pyqtSignal(str)  # error_message


class SingleBrowserProfileWorker(QRunnable):
    """Worker for loading profiles of one browser through common manager."""

    def __init__(
        self,
        browser_key: str,
        sync_manager: BrowserProfileManager,
        use_cache: bool = True,
    ):
        super().__init__()
        self.browser_key = browser_key
        self._manager = sync_manager
        self.use_cache = use_cache
        self.signals = ProfileLoadWorkerSignals()

    def run(self):
        """Performs profile loading in background thread."""
        try:
            logger.debug("Loading profiles %s in background thread", self.browser_key)
            start_time = time.time()

            if self.use_cache:
                # Use synchronous manager (it will update cache if no entry exists)
                profiles = self._manager.get_browser_profiles(self.browser_key)
            else:
                # Forced loading, bypassing cache
                finder = self._manager.finders.get(self.browser_key)
                profiles = finder.find_profiles() if finder else []
                # Update common cache with new data
                self._manager.cache.set(self.browser_key, profiles)

            load_time = time.time() - start_time
            logger.debug(
                "Loaded profiles %s: %s in %.3fs (use_cache=%s)",
                self.browser_key,
                len(profiles),
                load_time,
                self.use_cache,
            )

            # Отправляем результат
            self.signals.browser_profiles_loaded.emit(self.browser_key, profiles)

        except Exception as e:
            error_msg = f"Error loading profiles {self.browser_key}: {e}"
            logger.error("Error loading profiles %s: %s", self.browser_key, e)
            self.signals.browser_load_error.emit(self.browser_key, error_msg)


class AllBrowsersProfileWorker(QRunnable):
    """Worker for loading profiles of all browsers through common manager."""

    def __init__(
        self,
        sync_manager: BrowserProfileManager,
        use_cache: bool = True,
    ):
        super().__init__()
        self._manager = sync_manager
        self.use_cache = use_cache
        self.signals = ProfileLoadWorkerSignals()

    def run(self):
        """Performs loading profiles of all browsers in background thread."""
        try:
            logger.debug("Loading profiles of all browsers in background thread")
            start_time = time.time()

            all_profiles = {}
            total_browsers = len(self._manager.finders)
            current_browser = 0

            for browser_key, finder in self._manager.finders.items():
                current_browser += 1

                # Send progress
                self.signals.all_profiles_progress.emit(
                    browser_key, current_browser, total_browsers
                )

                try:
                    if self.use_cache:
                        profiles = self._manager.get_browser_profiles(browser_key)
                    else:
                        profiles = finder.find_profiles()
                        self._manager.cache.set(browser_key, profiles)

                    if profiles:
                        all_profiles[browser_key] = profiles
                        logger.debug(
                            "Added profiles for %s: %s",
                            browser_key,
                            len(profiles),
                        )
                    else:
                        logger.debug("No profiles found for %s", browser_key)

                except Exception as e:
                    logger.error("Error loading profiles for %s: %s", browser_key, e)
                    continue

            load_time = time.time() - start_time
            total_profiles = sum(len(profiles) for profiles in all_profiles.values())
            logger.info(
                "Loaded profiles of all browsers: %s profiles from %s browsers in %.3fs",
                total_profiles,
                len(all_profiles),
                load_time,
            )

            # Отправляем результат
            self.signals.all_profiles_loaded.emit(all_profiles)

        except Exception as e:
            error_msg = f"Ошибка загрузки всех профилей: {e}"
            logger.error("Ошибка загрузки всех профилей: %s", e)
            self.signals.all_profiles_error.emit(error_msg)


class AvailableBrowsersWorker(QRunnable):
    """Worker for getting list of available browsers through common manager."""

    def __init__(self, sync_manager: BrowserProfileManager):
        super().__init__()
        self._manager = sync_manager
        self.signals = ProfileLoadWorkerSignals()

    def run(self):
        """Performs search for available browsers in background thread."""
        try:
            logger.debug("Searching for available browsers in background thread")
            start_time = time.time()

            available = self._manager.get_available_browsers()

            load_time = time.time() - start_time
            logger.info(
                "Found %s available browsers in %.3fs",
                len(available),
                load_time,
            )

            # Отправляем результат
            self.signals.available_browsers_loaded.emit(available)

        except Exception as e:
            error_msg = f"Ошибка поиска доступных браузеров: {e}"
            logger.error("Ошибка поиска доступных браузеров: %s", e)
            self.signals.available_browsers_error.emit(error_msg)


class AsyncBrowserProfileManager(QObject):
    """
    Asynchronous browser profile manager.

    Provides non-blocking interface for loading browser profiles
    using background QRunnable workers.
    """

    # UI signals
    browser_profiles_ready = pyqtSignal(str, list)  # browser_key, profiles
    all_profiles_ready = pyqtSignal(dict)  # {browser_key: profiles}
    available_browsers_ready = pyqtSignal(list)  # available_browsers

    loading_progress = pyqtSignal(str, int, int)  # current_operation, current, total
    loading_error = pyqtSignal(str, str)  # operation, error_message

    def __init__(self, parent=None):
        super().__init__(parent)

        # Create/get common synchronous manager for access to finders and cache
        self._sync_manager = get_profile_manager()

        # Settings
        self._cache_timeout = self._sync_manager.cache.timeout
        self._thread_pool = QThreadPool.globalInstance()

        # Statistics
        self._stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "background_loads": 0,
            "errors": 0,
        }

        logger.info(
            "Initialized asynchronous profile manager (cache: %ss)",
            self._cache_timeout,
        )

    def load_browser_profiles_async(
        self, browser_key: str, use_cache: bool = True
    ) -> bool:
        """
        Asynchronously loads profiles of specified browser.

        Args:
            browser_key: Browser key (chrome, firefox, etc.)
            use_cache: Use caching

        Returns:
            True if task started, False if browser not supported
        """
        if browser_key not in self._sync_manager.finders:
            logger.warning("Browser %s not supported", browser_key)
            return False

        # Создаем и запускаем воркер
        worker = SingleBrowserProfileWorker(browser_key, self._sync_manager, use_cache)

        # Подключаем сигналы
        worker.signals.browser_profiles_loaded.connect(self._on_browser_profiles_loaded)
        worker.signals.browser_load_error.connect(self._on_browser_load_error)

        # Запускаем в фоновом потоке
        self._thread_pool.start(worker)
        self._stats["total_requests"] += 1
        self._stats["background_loads"] += 1

        logger.debug("Started asynchronous profile loading %s", browser_key)
        return True

    def load_all_profiles_async(self, use_cache: bool = True) -> bool:
        """
        Asynchronously loads profiles of all browsers.

        Args:
            use_cache: Use caching

        Returns:
            True if task started
        """
        # Создаем и запускаем воркер
        worker = AllBrowsersProfileWorker(self._sync_manager, use_cache)

        # Подключаем сигналы
        worker.signals.all_profiles_loaded.connect(self._on_all_profiles_loaded)
        worker.signals.all_profiles_progress.connect(self._on_all_profiles_progress)
        worker.signals.all_profiles_error.connect(self._on_all_profiles_error)

        # Запускаем в фоновом потоке
        self._thread_pool.start(worker)
        self._stats["total_requests"] += 1
        self._stats["background_loads"] += 1

        logger.debug("Started asynchronous loading of all profiles")
        return True

    def load_available_browsers_async(self) -> bool:
        """
        Asynchronously gets list of available browsers.

        Returns:
            True if task started
        """
        # Создаем и запускаем воркер
        worker = AvailableBrowsersWorker(self._sync_manager)

        # Подключаем сигналы
        worker.signals.available_browsers_loaded.connect(
            self._on_available_browsers_loaded
        )
        worker.signals.available_browsers_error.connect(
            self._on_available_browsers_error
        )

        # Запускаем в фоновом потоке
        self._thread_pool.start(worker)
        self._stats["total_requests"] += 1
        self._stats["background_loads"] += 1

        logger.debug("Started asynchronous search for available browsers")
        return True

    def get_cached_profiles(self, browser_key: str) -> Optional[list[dict]]:
        """Gets profiles from unified cache of synchronous manager."""
        profiles = self._sync_manager.get_cached_profiles(browser_key)
        if profiles is not None:
            self._stats["cache_hits"] += 1
            logger.debug(
                "Returned profiles %s from cache: %s",
                browser_key,
                len(profiles),
            )
        return profiles

    def clear_cache(self):
        """Clears profile cache."""
        self._sync_manager.clear_cache()
        logger.info("Asynchronous profile manager cache cleared")

    def get_stats(self) -> dict[str, int]:
        """Returns usage statistics."""
        return self._stats.copy()

    def get_supported_browsers(self) -> list[dict[str, str]]:
        """Returns list of supported browsers (synchronously)."""
        return self._sync_manager.get_supported_browsers()

    def detect_browser_from_args(self, args: str) -> Optional[str]:
        """Detects browser from command line arguments (synchronously)."""
        return self._sync_manager.detect_browser_from_args(args)

    # Slots for processing worker results
    def _on_browser_profiles_loaded(self, browser_key: str, profiles: list[dict]):
        """Processing loaded browser profiles."""
        logger.debug("Received profiles %s: %s", browser_key, len(profiles))
        self.browser_profiles_ready.emit(browser_key, profiles)

    def _on_browser_load_error(self, browser_key: str, error_message: str):
        """Processing browser profile loading error."""
        logger.error("Error loading profiles %s: %s", browser_key, error_message)
        self._stats["errors"] += 1
        self.loading_error.emit(f"browser_{browser_key}", error_message)

    def _on_all_profiles_loaded(self, all_profiles: dict[str, list[dict]]):
        """Processing loaded profiles of all browsers."""
        total_profiles = sum(len(profiles) for profiles in all_profiles.values())
        logger.info(
            "Received profiles of all browsers: %s profiles from %s browsers",
            total_profiles,
            len(all_profiles),
        )
        self.all_profiles_ready.emit(all_profiles)

    def _on_all_profiles_progress(self, current_browser: str, current: int, total: int):
        """Processing progress of all profiles loading."""
        logger.debug("Loading progress: %s (%s/%s)", current_browser, current, total)
        self.loading_progress.emit(f"Loading {current_browser}", current, total)

    def _on_all_profiles_error(self, error_message: str):
        """Processing error of all profiles loading."""
        logger.error("Error loading all profiles: %s", error_message)
        self._stats["errors"] += 1
        self.loading_error.emit("all_profiles", error_message)

    def _on_available_browsers_loaded(self, available_browsers: list[dict]):
        """Processing found available browsers."""
        logger.info("Found available browsers: %s", len(available_browsers))
        self.available_browsers_ready.emit(available_browsers)

    def _on_available_browsers_error(self, error_message: str):
        """Processing error of available browsers search."""
        logger.error("Error searching for available browsers: %s", error_message)
        self._stats["errors"] += 1
        self.loading_error.emit("available_browsers", error_message)


# Global instance for convenience
_async_profile_manager = None


def get_async_profile_manager() -> AsyncBrowserProfileManager:
    """Returns global instance of asynchronous profile manager."""
    global _async_profile_manager

    if _async_profile_manager is None:
        _async_profile_manager = AsyncBrowserProfileManager()
        logger.info("Created global asynchronous profile manager")

    return _async_profile_manager
