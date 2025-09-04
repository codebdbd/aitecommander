"""Модуль для загрузки профилей браузеров."""

import logging
from typing import Optional

from PyQt6.QtCore import Qt


class BrowserProfilesLoader:
    """Класс для управления загрузкой профилей браузеров."""
    
    def __init__(self, main_window):
        """
        Инициализирует BrowserProfilesLoader.
        
        Args:
            main_window: Главное окно приложения
        """
        self.main_window = main_window
    
    def setup_lazy_loading(self) -> None:
        """Настраивает ленивую загрузку профилей браузеров после показа окна."""
        try:
            self.main_window.shown.connect(self._on_window_shown)
        except Exception as e:
            logging.debug("Не удалось подключить ленивую загрузку профилей: %s", e)
    
    def _on_window_shown(self) -> None:
        """Обработчик показа окна для запуска загрузки профилей."""
        try:
            from app.utils.browser.browser_profiles import async_profile_manager as _apm
            from app.utils.browser.browser_profiles import persistent_cache as _pc
            from app.utils.browser.browser_profiles import profile_manager as _pm
            
            cache_path = _pc.get_cache_path()
            if not cache_path.exists():
                async_mgr = _apm.get_async_profile_manager()
                
                def _save_and_update(all_profiles: dict):
                    """Сохраняет и обновляет профили браузеров."""
                    try:
                        # Сохранить в персистентный кэш
                        cache = _pc.PersistentProfileCache(default_ttl=3600)
                        for key, profiles in (all_profiles or {}).items():
                            try:
                                cache.set(key, profiles)
                            except Exception:
                                pass
                        
                        # Обновить кеш через публичный API менеджера профилей
                        mgr = _pm.get_profile_manager()
                        try:
                            mgr.update_profiles_bulk(all_profiles or {})
                        except Exception:
                            pass
                    except Exception as e:
                        logging.warning("Ошибка сохранения/обновления кеша профилей: %s", e)
                    finally:
                        # Одноразовое подключение: после первого вызова отключаем слот
                        try:
                            async_mgr.all_profiles_ready.disconnect(_save_and_update)
                        except Exception:
                            pass
                
                async_mgr.all_profiles_ready.connect(
                    _save_and_update,
                    type=Qt.ConnectionType.UniqueConnection,
                )
                async_mgr.load_all_profiles_async(use_cache=False)
        except Exception as e:
            logging.debug("Ленивая загрузка профилей пропущена: %s", e)
