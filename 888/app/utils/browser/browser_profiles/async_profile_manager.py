#!/usr/bin/env python3
"""
Асинхронный менеджер профилей браузеров с поддержкой фоновой загрузки.
"""

import logging
import time
from typing import Dict, List, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from .profile_manager import BrowserProfileManager, get_profile_manager

logger = logging.getLogger(__name__)


class ProfileLoadWorkerSignals(QObject):
    """Сигналы для воркера загрузки профилей."""

    # Сигналы для одного браузера
    browser_profiles_loaded = pyqtSignal(str, list)  # browser_key, profiles
    browser_load_error = pyqtSignal(str, str)  # browser_key, error_message

    # Сигналы для всех браузеров
    all_profiles_loaded = pyqtSignal(dict)  # {browser_key: profiles}
    all_profiles_progress = pyqtSignal(str, int, int)  # current_browser, current, total
    all_profiles_error = pyqtSignal(str)  # error_message

    # Сигналы для доступных браузеров
    available_browsers_loaded = pyqtSignal(list)  # available_browsers
    available_browsers_error = pyqtSignal(str)  # error_message


class SingleBrowserProfileWorker(QRunnable):
    """Воркер для загрузки профилей одного браузера через общий менеджер."""

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
        """Выполняет загрузку профилей в фоновом потоке."""
        try:
            logger.debug("Загрузка профилей %s в фоновом потоке", self.browser_key)
            start_time = time.time()

            if self.use_cache:
                # Используем синхронный менеджер (он сам обновит кэш при отсутствии записи)
                profiles = self._manager.get_browser_profiles(self.browser_key)
            else:
                # Принудительная загрузка, обходя кэш
                finder = self._manager.finders.get(self.browser_key)
                profiles = finder.find_profiles() if finder else []
                # Обновим общий кэш новыми данными
                self._manager.cache.set(self.browser_key, profiles)

            load_time = time.time() - start_time
            logger.debug(
                "Загружены профили %s: %s за %.3fs (use_cache=%s)",
                self.browser_key,
                len(profiles),
                load_time,
                self.use_cache,
            )

            # Отправляем результат
            self.signals.browser_profiles_loaded.emit(self.browser_key, profiles)

        except Exception as e:
            error_msg = f"Ошибка загрузки профилей {self.browser_key}: {e}"
            logger.error("Ошибка загрузки профилей %s: %s", self.browser_key, e)
            self.signals.browser_load_error.emit(self.browser_key, error_msg)


class AllBrowsersProfileWorker(QRunnable):
    """Воркер для загрузки профилей всех браузеров через общий менеджер."""

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
        """Выполняет загрузку профилей всех браузеров в фоновом потоке."""
        try:
            logger.debug("Загрузка профилей всех браузеров в фоновом потоке")
            start_time = time.time()

            all_profiles = {}
            total_browsers = len(self._manager.finders)
            current_browser = 0

            for browser_key, finder in self._manager.finders.items():
                current_browser += 1

                # Отправляем прогресс
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
                            "Добавлены профили %s: %s",
                            browser_key,
                            len(profiles),
                        )
                    else:
                        logger.debug("Не найдено профилей для %s", browser_key)

                except Exception as e:
                    logger.error("Ошибка при загрузке профилей %s: %s", browser_key, e)
                    continue

            load_time = time.time() - start_time
            total_profiles = sum(len(profiles) for profiles in all_profiles.values())
            logger.info(
                "Загружены профили всех браузеров: %s профилей из %s браузеров за %.3fs",
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
    """Воркер для получения списка доступных браузеров через общий менеджер."""

    def __init__(self, sync_manager: BrowserProfileManager):
        super().__init__()
        self._manager = sync_manager
        self.signals = ProfileLoadWorkerSignals()

    def run(self):
        """Выполняет поиск доступных браузеров в фоновом потоке."""
        try:
            logger.debug("Поиск доступных браузеров в фоновом потоке")
            start_time = time.time()

            available = self._manager.get_available_browsers()

            load_time = time.time() - start_time
            logger.info(
                "Найдено %s доступных браузеров за %.3fs",
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
    Асинхронный менеджер профилей браузеров.

    Предоставляет неблокирующий интерфейс для загрузки профилей браузеров
    с использованием фоновых QRunnable воркеров.
    """

    # Сигналы для UI
    browser_profiles_ready = pyqtSignal(str, list)  # browser_key, profiles
    all_profiles_ready = pyqtSignal(dict)  # {browser_key: profiles}
    available_browsers_ready = pyqtSignal(list)  # available_browsers

    loading_progress = pyqtSignal(str, int, int)  # current_operation, current, total
    loading_error = pyqtSignal(str, str)  # operation, error_message

    def __init__(self, parent=None):
        super().__init__(parent)

        # Создаем/получаем общий синхронный менеджер для доступа к finder'ам и кэшу
        self._sync_manager = get_profile_manager()

        # Настройки
        self._cache_timeout = self._sync_manager.cache.timeout
        self._thread_pool = QThreadPool.globalInstance()

        # Статистика
        self._stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "background_loads": 0,
            "errors": 0,
        }

        logger.info(
            "Инициализирован асинхронный менеджер профилей (кеш: %ss)",
            self._cache_timeout,
        )

    def load_browser_profiles_async(
        self, browser_key: str, use_cache: bool = True
    ) -> bool:
        """
        Асинхронно загружает профили указанного браузера.

        Args:
            browser_key: Ключ браузера (chrome, firefox, etc.)
            use_cache: Использовать кеширование

        Returns:
            True если задача запущена, False если браузер не поддерживается
        """
        if browser_key not in self._sync_manager.finders:
            logger.warning("Браузер %s не поддерживается", browser_key)
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

        logger.debug("Запущена асинхронная загрузка профилей %s", browser_key)
        return True

    def load_all_profiles_async(self, use_cache: bool = True) -> bool:
        """
        Асинхронно загружает профили всех браузеров.

        Args:
            use_cache: Использовать кеширование

        Returns:
            True если задача запущена
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

        logger.debug("Запущена асинхронная загрузка всех профилей")
        return True

    def load_available_browsers_async(self) -> bool:
        """
        Асинхронно получает список доступных браузеров.

        Returns:
            True если задача запущена
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

        logger.debug("Запущен асинхронный поиск доступных браузеров")
        return True

    def get_cached_profiles(self, browser_key: str) -> Optional[List[Dict]]:
        """Получает профили из единого кэша синхронного менеджера."""
        profiles = self._sync_manager.get_cached_profiles(browser_key)
        if profiles is not None:
            self._stats["cache_hits"] += 1
            logger.debug(
                "Возвращены профили %s из кеша: %s",
                browser_key,
                len(profiles),
            )
        return profiles

    def clear_cache(self):
        """Очищает кеш профилей."""
        self._sync_manager.clear_cache()
        logger.info("Кеш асинхронного менеджера профилей очищен")

    def get_stats(self) -> Dict[str, int]:
        """Возвращает статистику использования."""
        return self._stats.copy()

    def get_supported_browsers(self) -> List[Dict[str, str]]:
        """Возвращает список поддерживаемых браузеров (синхронно)."""
        return self._sync_manager.get_supported_browsers()

    def detect_browser_from_args(self, args: str) -> Optional[str]:
        """Определяет браузер по аргументам командной строки (синхронно)."""
        return self._sync_manager.detect_browser_from_args(args)

    # Слоты для обработки результатов воркеров
    def _on_browser_profiles_loaded(self, browser_key: str, profiles: List[Dict]):
        """Обработка загруженных профилей браузера."""
        logger.debug("Получены профили %s: %s", browser_key, len(profiles))
        self.browser_profiles_ready.emit(browser_key, profiles)

    def _on_browser_load_error(self, browser_key: str, error_message: str):
        """Обработка ошибки загрузки профилей браузера."""
        logger.error("Ошибка загрузки профилей %s: %s", browser_key, error_message)
        self._stats["errors"] += 1
        self.loading_error.emit(f"browser_{browser_key}", error_message)

    def _on_all_profiles_loaded(self, all_profiles: Dict[str, List[Dict]]):
        """Обработка загруженных профилей всех браузеров."""
        total_profiles = sum(len(profiles) for profiles in all_profiles.values())
        logger.info(
            "Получены профили всех браузеров: %s профилей из %s браузеров",
            total_profiles,
            len(all_profiles),
        )
        self.all_profiles_ready.emit(all_profiles)

    def _on_all_profiles_progress(self, current_browser: str, current: int, total: int):
        """Обработка прогресса загрузки всех профилей."""
        logger.debug("Прогресс загрузки: %s (%s/%s)", current_browser, current, total)
        self.loading_progress.emit(f"Загрузка {current_browser}", current, total)

    def _on_all_profiles_error(self, error_message: str):
        """Обработка ошибки загрузки всех профилей."""
        logger.error("Ошибка загрузки всех профилей: %s", error_message)
        self._stats["errors"] += 1
        self.loading_error.emit("all_profiles", error_message)

    def _on_available_browsers_loaded(self, available_browsers: List[Dict]):
        """Обработка найденных доступных браузеров."""
        logger.info("Найдены доступные браузеры: %s", len(available_browsers))
        self.available_browsers_ready.emit(available_browsers)

    def _on_available_browsers_error(self, error_message: str):
        """Обработка ошибки поиска доступных браузеров."""
        logger.error("Ошибка поиска доступных браузеров: %s", error_message)
        self._stats["errors"] += 1
        self.loading_error.emit("available_browsers", error_message)


# Глобальный экземпляр для удобства использования
_async_profile_manager = None


def get_async_profile_manager() -> AsyncBrowserProfileManager:
    """Возвращает глобальный экземпляр асинхронного менеджера профилей."""
    global _async_profile_manager

    if _async_profile_manager is None:
        _async_profile_manager = AsyncBrowserProfileManager()
        logger.info("Создан глобальный асинхронный менеджер профилей")

    return _async_profile_manager
