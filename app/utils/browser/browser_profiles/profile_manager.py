"""
Центральный менеджер для работы с профилями всех браузеров.
"""

import logging
from typing import Dict, List, Optional

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
from .runtime_cache import ProfileCache
from .utils import get_browser_display_name

logger = logging.getLogger(__name__)


class BrowserProfileManager:
    def get_profiles_by_browser(self, browser_key: str):
        """
        Возвращает список профилей для указанного браузера.
        """
        finder = self.finders.get(browser_key)
        if not finder:
            return []
        try:
            profiles = self._get_cached_profiles(browser_key)
            # Если вдруг вернулся не список, а словарь — берем значения
            if isinstance(profiles, dict):
                return list(profiles.values())
            return profiles or []
        except Exception:
            return []

    def get_supported_browsers(self):
        """Возвращает список поддерживаемых браузеров в формате [{'key': ..., 'name': ...}, ...]"""
        # Получаем список поддерживаемых браузеров из конфигурации
        try:
            from app.config_data import app_config

            supported_browsers = app_config.get_supported_browsers()
            return [
                {"key": key, "name": get_browser_display_name(finder, key)}
                for key, finder in self.finders.items()
                if key in supported_browsers
            ]
        except Exception:
            # fallback если конфигурация недоступна
            return [
                {"key": key, "name": get_browser_display_name(finder, key)}
                for key, finder in self.finders.items()
            ]

    """Универсальный менеджер для работы с профилями всех браузеров."""

    def __init__(self):
        """Инициализация менеджера с поддержкой всех браузеров."""
        self.finders: Dict[str, BaseBrowserProfileFinder] = {
            "chrome": ChromeProfileFinder(),
            "firefox": FirefoxProfileFinder(),
            "edge": EdgeProfileFinder(),
            "brave": BraveProfileFinder(),
            "vivaldi": VivaldiProfileFinder(),
            "opera": OperaProfileFinder(),
            "yandex": YandexProfileFinder(),
        }

        # Единый кэш профилей
        self.cache = ProfileCache(timeout_seconds=self._get_cache_timeout())

        logger.info(
            f"Инициализирован менеджер профилей для {len(self.finders)} браузеров"
        )

        # Попытка загрузить кэш профилей из пользовательского JSON при старте
        try:
            from . import profile_cache as _pc

            cached = _pc.load_profiles()
            self.cache.load_initial(cached)
            if cached:
                logger.debug(
                    "Инициализация кэша профилей из JSON: %d браузеров", len(cached)
                )
        except Exception as e:
            logger.debug("Не удалось загрузить кэш профилей при старте: %s", e)

    def _get_cache_timeout(self) -> int:
        """Получает таймаут кеша из конфигурации."""
        try:
            from app.config_data import app_config

            settings = app_config.get_browser_profile_settings()
            return settings.get("cache_timeout", 300)
        except ImportError:
            return 300  # 5 минут по умолчанию

    def get_all_profiles(self) -> Dict[str, List[Dict]]:
        """Получает профили всех браузеров."""

        all_profiles = {}

        for browser_key, finder in self.finders.items():
            logger.debug(f"get_all_profiles: processing browser_key={browser_key}")
            try:
                profiles = self._get_cached_profiles(browser_key)
                if profiles:
                    all_profiles[browser_key] = profiles
            except Exception as e:
                logger.error(f"Ошибка при поиске профилей {browser_key}: {e}")

        return all_profiles

    def get_browser_profiles(self, browser_key: str) -> List[Dict]:
        """Получает профили конкретного браузера."""
        if browser_key not in self.finders:
            return []
        return self._get_cached_profiles(browser_key)

    def _get_cached_profiles(self, browser_key: str) -> List[Dict]:
        """Получает профили с кешированием.

        Сначала пробует вернуть из кэша (без проверки свежести), если отсутствует —
        выполняет загрузку через finder и обновляет кэш.
        """
        logger.debug(f"_get_cached_profiles: browser_key={browser_key}")

        # Пытаемся получить из кэша
        cached = self.cache.get(browser_key)
        if cached is not None:
            return cached

        # Загрузка и обновление кэша
        finder = self.finders.get(browser_key)
        if finder:
            try:
                profiles = finder.find_profiles()
                self.cache.set(browser_key, profiles)
                return profiles
            except Exception as e:
                logger.error(f"Ошибка при получении профилей {browser_key}: {e}")

        return []

    def get_cached_profiles(self, browser_key: str) -> Optional[List[Dict]]:
        """Возвращает профили из кэша, только если они свежие; не блокирует загрузку."""
        return self.cache.get_if_fresh(browser_key)

    def get_available_browsers(self) -> List[Dict[str, str]]:
        """Получает список доступных браузеров с профилями."""
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
                logger.debug(f"Браузер {browser_key} недоступен: {e}")

        return available

    def detect_browser_from_args(self, args: str) -> Optional[str]:
        """Определяет браузер по аргументам командной строки."""
        logger.debug(f"detect_browser_from_args: args={args}")

        if not args:
            logger.debug("detect_browser_from_args: no args provided")
            return None

        for browser_key, finder in self.finders.items():
            logger.debug(f"detect_browser_from_args: trying browser_key={browser_key}")
            try:
                profile_data = finder.parse_profile_from_args(args)
                logger.debug(
                    f"detect_browser_from_args: profile_data for {browser_key}={profile_data}"
                )
                if profile_data:
                    logger.debug(
                        f"detect_browser_from_args: detected browser_key={browser_key}"
                    )
                    return browser_key
            except Exception as e:
                logger.debug(
                    f"Ошибка определения браузера {browser_key} из аргументов: {e}"
                )
                continue

        logger.debug("detect_browser_from_args: could not detect browser")
        return None

    def clear_cache(self):
        """Очищает кеш профилей."""
        self.cache.clear()
        logger.info("Кеш профилей очищен")


# Модульный синглтон для переиспользования одного экземпляра менеджера
_PROFILE_MANAGER: Optional[BrowserProfileManager] = None


def get_profile_manager() -> BrowserProfileManager:
    """
    Возвращает общий экземпляр BrowserProfileManager для всего приложения.
    Гарантирует единичную инициализацию на процесс.
    """
    global _PROFILE_MANAGER
    if _PROFILE_MANAGER is None:
        _PROFILE_MANAGER = BrowserProfileManager()
    return _PROFILE_MANAGER
