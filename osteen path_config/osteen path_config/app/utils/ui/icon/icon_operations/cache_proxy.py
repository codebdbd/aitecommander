# cache_proxy.py
"""Прокси-класс для кэширования иконок меню с async поддержкой."""

from __future__ import annotations

import asyncio
import logging

from PyQt6.QtGui import QIcon

from ..path_service import get_current_theme
from ..validation import validate_theme

logger = logging.getLogger(__name__)


class IconCache:
    """Кеш иконок для меню с LRU и async поддержкой."""

    def get_icon(self, name: str, theme: str | None = None, source: str = "menu") -> QIcon:
        """Получить иконку с кешированием через прокси к глобальному менеджеру."""
        if theme is None:
            theme = get_current_theme()
        theme = validate_theme(theme)

        # Добавляем расширение .svg если не указано
        icon_name = name if "." in name else f"{name}.svg"

        # Импортируем здесь чтобы избежать циклических импортов
        from .creators import themed_icon

        # themed_icon() сама проверит кэш, поэтому просто вызываем её напрямую
        # Это устраняет избыточную двойную проверку кэша
        return themed_icon(icon_name, theme, source)

    async def get_icon_async(self, name: str, theme: str | None = None, source: str = "menu") -> QIcon:
        """Асинхронно получить иконку с кешированием."""
        if theme is None:
            theme = get_current_theme()
        theme = validate_theme(theme)

        # Добавляем расширение .svg если не указано
        icon_name = name if "." in name else f"{name}.svg"

        # Импортируем здесь чтобы избежать циклических импортов
        from .creators import themed_icon_async
        
        return await themed_icon_async(icon_name, theme, source)

    def clear_cache(self) -> None:
        """Очистить кеш (при смене темы)."""
        logger.debug("Clearing icon cache")
        # Очищаем глобальный кеш и кэш путей
        # Ленивая загрузка, чтобы избежать циклических импортов на уровне модуля
        from ..cache_manager import clear_icon_cache
        clear_icon_cache()
        # Очищаем кэш путей через сервис
        from ..path_service import icon_path_service

        icon_path_service.clear_cache()
        logger.debug("Icon cache cleared successfully")

    async def clear_cache_async(self) -> None:
        """Асинхронно очистить кеш."""
        await asyncio.get_event_loop().run_in_executor(None, self.clear_cache)
        logger.debug("Icon cache cleared asynchronously")

    async def preload_icons_async(self, icon_names: list[str], theme: str | None = None) -> dict[str, QIcon]:
        """Предварительно загрузить множество иконок асинхронно."""
        if theme is None:
            theme = get_current_theme()
        theme = validate_theme(theme)
        
        # Импортируем здесь чтобы избежать циклических импортов
        from .creators import themed_icon_async

        # Ограничиваем конкурентную загрузку, чтобы не перегружать диск/CPU
        # Делаем лимит настраиваемым через app_config, с безопасным дефолтом
        try:
            from app.config_data import (
                app_config,  # локальный импорт, чтобы избежать циклов
            )
            concurrency = int(getattr(app_config, "icon_preload_concurrency", 6))
        except Exception:  # noqa: BLE001
            concurrency = 6  # fall back
        sem = asyncio.Semaphore(concurrency)

        async def _load(name: str):
            icon_name = name if "." in name else f"{name}.svg"
            async with sem:
                try:
                    return await themed_icon_async(icon_name, theme, "preload")
                except Exception as e:  # noqa: BLE001
                    return e

        tasks = [_load(name) for name in icon_names]
        icons = await asyncio.gather(*tasks, return_exceptions=False)
        
        result = {}
        for name, icon in zip(icon_names, icons):
            if isinstance(icon, Exception):
                logger.warning(f"Failed to preload icon {name}: {icon}")
                result[name] = QIcon()  # Пустая иконка при ошибке
            else:
                result[name] = icon
                
        logger.info(f"Preloaded {len(result)} icons for theme {theme}")
        return result


# Единственный глобальный экземпляр
icon_cache = IconCache()
