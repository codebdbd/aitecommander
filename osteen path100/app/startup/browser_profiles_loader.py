"""Модуль для загрузки профилей браузеров."""

import logging
from typing import Any

from PyQt6.QtCore import Qt

# Модульный логгер
logger = logging.getLogger(__name__)


class BrowserProfilesLoader:
    """Класс для управления загрузкой профилей браузеров."""

    def __init__(self, main_window: Any):
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
        except (AttributeError, TypeError, RuntimeError) as e:
            # Узкоспециализированные исключения подключения сигнала Qt
            logger.debug(
                "Не удалось подключить ленивую загрузку профилей: %s", e, exc_info=True
            )

    def _on_window_shown(self) -> None:
        """Обработчик показа окна для запуска загрузки профилей."""
        try:
            from app.utils.browser.browser_profiles import async_profile_manager as _apm
            from app.utils.browser.browser_profiles import persistent_cache as _pc
            from app.utils.browser.browser_profiles import profile_manager as _pm
        except ImportError as e:
            # Критично для функциональности, но не должно ронять приложение
            logger.warning("Модули профилей браузеров недоступны: %s", e, exc_info=True)
            return

        # Обработчик должен быть одноразовым — отписываемся сразу
        try:
            self.main_window.shown.disconnect(self._on_window_shown)
        except Exception:
            pass

        try:
            cache_path = _pc.get_cache_path()
        except Exception as e:
            logger.debug(
                "Не удалось определить путь к кэшу профилей: %s", e, exc_info=True
            )
            return

        if not cache_path.exists():
            try:
                async_mgr = _apm.get_async_profile_manager()
            except Exception as e:
                logger.debug(
                    "Не удалось получить менеджер асинхронных профилей: %s",
                    e,
                    exc_info=True,
                )
                return

            def _save_and_update(all_profiles: dict):
                """Сохраняет и обновляет профили браузеров."""
                # Сохранить в персистентный кэш
                try:
                    cache = _pc.PersistentProfileCache(default_ttl=3600)
                    for key, profiles in (all_profiles or {}).items():
                        try:
                            cache.set(key, profiles)
                        except Exception as set_err:
                            logger.warning(
                                "Не удалось записать профили в кэш для ключа '%s': %s",
                                key,
                                set_err,
                                exc_info=True,
                            )
                except Exception as cache_err:
                    logger.warning(
                        "Ошибка инициализации/записи кэша профилей: %s",
                        cache_err,
                        exc_info=True,
                    )

                # Обновить кеш через публичный API менеджера профилей
                try:
                    mgr = _pm.get_profile_manager()
                    mgr.update_profiles_bulk(all_profiles or {})
                except Exception as upd_err:
                    logger.warning(
                        "Не удалось обновить менеджер профилей из кэша: %s",
                        upd_err,
                        exc_info=True,
                    )
                finally:
                    # Одноразовое подключение: после первого вызова отключаем слот
                    try:
                        async_mgr.all_profiles_ready.disconnect(_save_and_update)
                    except (TypeError, RuntimeError) as dis_err:
                        logger.debug(
                            "Ошибка при отключении слота all_profiles_ready: %s",
                            dis_err,
                            exc_info=True,
                        )

            try:
                async_mgr.all_profiles_ready.connect(
                    _save_and_update,
                    type=Qt.ConnectionType.UniqueConnection,
                )
            except (TypeError, RuntimeError) as conn_err:
                logger.debug(
                    "Не удалось подключить слот all_profiles_ready: %s",
                    conn_err,
                    exc_info=True,
                )
                return

            try:
                async_mgr.load_all_profiles_async(use_cache=False)
            except Exception as load_err:
                logger.debug(
                    "Не удалось запустить асинхронную загрузку профилей: %s",
                    load_err,
                    exc_info=True,
                )
        else:
            # Кэш существует — пробуем загрузить профили из кэша в менеджер
            try:
                cache = _pc.PersistentProfileCache(default_ttl=3600)
                mgr = _pm.get_profile_manager()

                # Попытка универсального API: перебрать ключи и обновить пакетно
                loaded_any = False
                profiles_by_key: dict[str, Any] = {}
                try:
                    keys = list(cache.keys())  # type: ignore[attr-defined]
                except Exception:
                    keys = []
                for key in keys:
                    try:
                        profiles = cache.get(key)  # type: ignore[call-arg]
                        if profiles is not None:
                            profiles_by_key[str(key)] = profiles
                            loaded_any = True
                    except Exception as get_err:
                        logger.debug(
                            "Не удалось прочитать профили из кэша для ключа '%s': %s",
                            key,
                            get_err,
                            exc_info=True,
                        )

                if loaded_any:
                    try:
                        mgr.update_profiles_bulk(profiles_by_key)
                    except Exception as upd_err:
                        logger.warning(
                            "Не удалось обновить менеджер профилей из существующего кэша: %s",
                            upd_err,
                            exc_info=True,
                        )
            except Exception as cache_err:
                logger.debug("Ошибка чтения существующего кэша профилей: %s", cache_err, exc_info=True)
