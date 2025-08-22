#!/usr/bin/env python3
"""
Асинхронный менеджер профилей браузеров с поддержкой фоновой загрузки.
"""

import logging
import time
from typing import Dict, List, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from .base_profile_finder import BaseBrowserProfileFinder
from .profile_manager import get_profile_manager

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
    """Воркер для загрузки профилей одного браузера."""
    
    def __init__(self, browser_key: str, finder: BaseBrowserProfileFinder, 
                 use_cache: bool = True, cache_timeout: int = 300):
        super().__init__()
        self.browser_key = browser_key
        self.finder = finder
        self.use_cache = use_cache
        self.cache_timeout = cache_timeout
        self.signals = ProfileLoadWorkerSignals()
        
        # Статический кеш для всех воркеров
        if not hasattr(SingleBrowserProfileWorker, '_cache'):
            SingleBrowserProfileWorker._cache = {}
            SingleBrowserProfileWorker._last_update = {}
    
    def run(self):
        """Выполняет загрузку профилей в фоновом потоке."""
        try:
            logger.debug(f"Загрузка профилей {self.browser_key} в фоновом потоке")
            start_time = time.time()
            
            profiles = []
            
            # Проверяем кеш если разрешено
            if self.use_cache:
                current_time = time.time()
                if (self.browser_key in SingleBrowserProfileWorker._cache and 
                    self.browser_key in SingleBrowserProfileWorker._last_update and
                    current_time - SingleBrowserProfileWorker._last_update[self.browser_key] < self.cache_timeout):
                    
                    profiles = SingleBrowserProfileWorker._cache[self.browser_key]
                    logger.debug(f"Использован кеш для {self.browser_key}: {len(profiles)} профилей")
                else:
                    # Загружаем профили
                    profiles = self.finder.find_profiles()
                    
                    # Обновляем кеш
                    SingleBrowserProfileWorker._cache[self.browser_key] = profiles
                    SingleBrowserProfileWorker._last_update[self.browser_key] = current_time
                    
                    load_time = time.time() - start_time
                    logger.debug(f"Загружены профили {self.browser_key}: {len(profiles)} за {load_time:.3f}s")
            else:
                # Загружаем без кеша
                profiles = self.finder.find_profiles()
                load_time = time.time() - start_time
                logger.debug(f"Загружены профили {self.browser_key} без кеша: {len(profiles)} за {load_time:.3f}s")
            
            # Отправляем результат
            self.signals.browser_profiles_loaded.emit(self.browser_key, profiles)
            
        except Exception as e:
            error_msg = f"Ошибка загрузки профилей {self.browser_key}: {e}"
            logger.error(error_msg)
            self.signals.browser_load_error.emit(self.browser_key, error_msg)


class AllBrowsersProfileWorker(QRunnable):
    """Воркер для загрузки профилей всех браузеров."""
    
    def __init__(self, finders: Dict[str, BaseBrowserProfileFinder], 
                 use_cache: bool = True, cache_timeout: int = 300):
        super().__init__()
        self.finders = finders
        self.use_cache = use_cache
        self.cache_timeout = cache_timeout
        self.signals = ProfileLoadWorkerSignals()
    
    def run(self):
        """Выполняет загрузку профилей всех браузеров в фоновом потоке."""
        try:
            logger.debug("Загрузка профилей всех браузеров в фоновом потоке")
            start_time = time.time()
            
            all_profiles = {}
            total_browsers = len(self.finders)
            current_browser = 0
            
            for browser_key, finder in self.finders.items():
                current_browser += 1
                
                # Отправляем прогресс
                self.signals.all_profiles_progress.emit(browser_key, current_browser, total_browsers)
                
                try:
                    # Непосредственно вызываем finder.find_profiles() для каждого браузера
                    profiles = finder.find_profiles()
                    
                    if profiles:
                        all_profiles[browser_key] = profiles
                        logger.debug(f"Добавлены профили {browser_key}: {len(profiles)}")
                    else:
                        logger.debug(f"Не найдено профилей для {browser_key}")
                
                except Exception as e:
                    logger.error(f"Ошибка при загрузке профилей {browser_key}: {e}")
                    continue
            
            load_time = time.time() - start_time
            total_profiles = sum(len(profiles) for profiles in all_profiles.values())
            logger.info(f"Загружены профили всех браузеров: {total_profiles} профилей из {len(all_profiles)} браузеров за {load_time:.3f}s")
            
            # Отправляем результат
            self.signals.all_profiles_loaded.emit(all_profiles)
            
        except Exception as e:
            error_msg = f"Ошибка загрузки всех профилей: {e}"
            logger.error(error_msg)
            self.signals.all_profiles_error.emit(error_msg)


class AvailableBrowsersWorker(QRunnable):
    """Воркер для получения списка доступных браузеров."""
    
    def __init__(self, finders: Dict[str, BaseBrowserProfileFinder]):
        super().__init__()
        self.finders = finders
        self.signals = ProfileLoadWorkerSignals()
    
    def run(self):
        """Выполняет поиск доступных браузеров в фоновом потоке."""
        try:
            logger.debug("Поиск доступных браузеров в фоновом потоке")
            start_time = time.time()
            
            available = []
            
            for browser_key, finder in self.finders.items():
                try:
                    # Быстрая проверка доступности без полной загрузки профилей
                    profiles = finder.find_profiles()
                    if profiles:
                        available.append({
                            'key': browser_key,
                            'name': finder.get_browser_name(),
                            'profile_count': len(profiles)
                        })
                        logger.debug(f"Браузер {browser_key} доступен: {len(profiles)} профилей")
                
                except Exception as e:
                    logger.debug(f"Браузер {browser_key} недоступен: {e}")
                    continue
            
            load_time = time.time() - start_time
            logger.info(f"Найдено {len(available)} доступных браузеров за {load_time:.3f}s")
            
            # Отправляем результат
            self.signals.available_browsers_loaded.emit(available)
            
        except Exception as e:
            error_msg = f"Ошибка поиска доступных браузеров: {e}"
            logger.error(error_msg)
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
        
        # Создаем/получаем общий синхронный менеджер для доступа к finder'ам
        self._sync_manager = get_profile_manager()
        
        # Настройки
        self._cache_timeout = self._sync_manager._get_cache_timeout()
        self._thread_pool = QThreadPool.globalInstance()
        
        # Статистика
        self._stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'background_loads': 0,
            'errors': 0
        }
        
        logger.info(f"Инициализирован асинхронный менеджер профилей (кеш: {self._cache_timeout}s)")
    
    def load_browser_profiles_async(self, browser_key: str, use_cache: bool = True) -> bool:
        """
        Асинхронно загружает профили указанного браузера.
        
        Args:
            browser_key: Ключ браузера (chrome, firefox, etc.)
            use_cache: Использовать кеширование
            
        Returns:
            True если задача запущена, False если браузер не поддерживается
        """
        if browser_key not in self._sync_manager.finders:
            logger.warning(f"Браузер {browser_key} не поддерживается")
            return False
        
        finder = self._sync_manager.finders[browser_key]
        
        # Создаем и запускаем воркер
        worker = SingleBrowserProfileWorker(browser_key, finder, use_cache, self._cache_timeout)
        
        # Подключаем сигналы
        worker.signals.browser_profiles_loaded.connect(self._on_browser_profiles_loaded)
        worker.signals.browser_load_error.connect(self._on_browser_load_error)
        
        # Запускаем в фоновом потоке
        self._thread_pool.start(worker)
        self._stats['total_requests'] += 1
        self._stats['background_loads'] += 1
        
        logger.debug(f"Запущена асинхронная загрузка профилей {browser_key}")
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
        worker = AllBrowsersProfileWorker(self._sync_manager.finders, use_cache, self._cache_timeout)
        
        # Подключаем сигналы
        worker.signals.all_profiles_loaded.connect(self._on_all_profiles_loaded)
        worker.signals.all_profiles_progress.connect(self._on_all_profiles_progress)
        worker.signals.all_profiles_error.connect(self._on_all_profiles_error)
        
        # Запускаем в фоновом потоке
        self._thread_pool.start(worker)
        self._stats['total_requests'] += 1
        self._stats['background_loads'] += 1
        
        logger.debug("Запущена асинхронная загрузка всех профилей")
        return True
    
    def load_available_browsers_async(self) -> bool:
        """
        Асинхронно получает список доступных браузеров.
        
        Returns:
            True если задача запущена
        """
        # Создаем и запускаем воркер
        worker = AvailableBrowsersWorker(self._sync_manager.finders)
        
        # Подключаем сигналы
        worker.signals.available_browsers_loaded.connect(self._on_available_browsers_loaded)
        worker.signals.available_browsers_error.connect(self._on_available_browsers_error)
        
        # Запускаем в фоновом потоке
        self._thread_pool.start(worker)
        self._stats['total_requests'] += 1
        self._stats['background_loads'] += 1
        
        logger.debug("Запущен асинхронный поиск доступных браузеров")
        return True
    
    def get_cached_profiles(self, browser_key: str) -> Optional[List[Dict]]:
        """
        Получает профили из кеша (синхронно, без блокировки).
        
        Args:
            browser_key: Ключ браузера
            
        Returns:
            Список профилей из кеша или None если кеш пуст/устарел
        """
        if hasattr(SingleBrowserProfileWorker, '_cache'):
            current_time = time.time()
            
            if (browser_key in SingleBrowserProfileWorker._cache and 
                browser_key in SingleBrowserProfileWorker._last_update and
                current_time - SingleBrowserProfileWorker._last_update[browser_key] < self._cache_timeout):
                
                profiles = SingleBrowserProfileWorker._cache[browser_key]
                self._stats['cache_hits'] += 1
                logger.debug(f"Возвращены профили {browser_key} из кеша: {len(profiles)}")
                return profiles
        
        return None
    
    def clear_cache(self):
        """Очищает кеш профилей."""
        if hasattr(SingleBrowserProfileWorker, '_cache'):
            SingleBrowserProfileWorker._cache.clear()
            SingleBrowserProfileWorker._last_update.clear()
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
        logger.debug(f"Получены профили {browser_key}: {len(profiles)}")
        self.browser_profiles_ready.emit(browser_key, profiles)
    
    def _on_browser_load_error(self, browser_key: str, error_message: str):
        """Обработка ошибки загрузки профилей браузера."""
        logger.error(f"Ошибка загрузки профилей {browser_key}: {error_message}")
        self._stats['errors'] += 1
        self.loading_error.emit(f"browser_{browser_key}", error_message)
    
    def _on_all_profiles_loaded(self, all_profiles: Dict[str, List[Dict]]):
        """Обработка загруженных профилей всех браузеров."""
        total_profiles = sum(len(profiles) for profiles in all_profiles.values())
        logger.info(f"Получены профили всех браузеров: {total_profiles} профилей из {len(all_profiles)} браузеров")
        self.all_profiles_ready.emit(all_profiles)
    
    def _on_all_profiles_progress(self, current_browser: str, current: int, total: int):
        """Обработка прогресса загрузки всех профилей."""
        logger.debug(f"Прогресс загрузки: {current_browser} ({current}/{total})")
        self.loading_progress.emit(f"Загрузка {current_browser}", current, total)
    
    def _on_all_profiles_error(self, error_message: str):
        """Обработка ошибки загрузки всех профилей."""
        logger.error(f"Ошибка загрузки всех профилей: {error_message}")
        self._stats['errors'] += 1
        self.loading_error.emit("all_profiles", error_message)
    
    def _on_available_browsers_loaded(self, available_browsers: List[Dict]):
        """Обработка найденных доступных браузеров."""
        logger.info(f"Найдены доступные браузеры: {len(available_browsers)}")
        self.available_browsers_ready.emit(available_browsers)
    
    def _on_available_browsers_error(self, error_message: str):
        """Обработка ошибки поиска доступных браузеров."""
        logger.error(f"Ошибка поиска доступных браузеров: {error_message}")
        self._stats['errors'] += 1
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
