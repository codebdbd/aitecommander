# __init__.py
"""
Модуль операций с иконками - разделенный на логические компоненты с async поддержкой.

Структура:
- cache_proxy.py: Класс IconCache для кэширования иконок меню
- converters.py: Функции конвертации и копирования иконок
- creators.py: Функции создания QIcon с thread safety
"""

from __future__ import annotations

# Импорт из validation (для совместимости)
from ..validation import is_valid_icon_file

# Импорт из cache_proxy
from .cache_proxy import IconCache, icon_cache

# Импорт из converters
from .converters import (  # Синхронные функции копирования; Синхронные функции конвертации; Асинхронные функции копирования; Асинхронные функции конвертации; Пакетная конвертация
    batch_convert_icons_async,
    convert_icon_to_png_32,
    convert_icon_to_png_32_async,
    convert_icon_to_png_128,
    convert_icon_to_png_128_async,
    convert_raster_icon_to_png,
    convert_raster_icon_to_png_async,
    copy_icon,
    copy_icon_async,
    copy_icon_smart,
    copy_icon_to_path,
    copy_icon_to_path_async,
)

# Импорт из creators
from .creators import (  # Основные функции создания иконок; Создание иконок из абсолютных путей; Внутренние функции (для совместимости)
    _create_svg_icon,
    _ensure_gui_thread,
    create_icon_from_path,
    create_icon_from_path_async,
    themed_icon,
    themed_icon_async,
)

# Экспорт всех публичных функций и классов
__all__ = [
    # Кэш иконок
    "IconCache",
    "icon_cache",
    # Синхронные функции копирования
    "copy_icon",
    "copy_icon_smart",
    "copy_icon_to_path",
    # Синхронные функции конвертации
    "convert_icon_to_png_128",
    "convert_icon_to_png_32",
    "convert_raster_icon_to_png",
    # Асинхронные функции копирования
    "copy_icon_async",
    "copy_icon_to_path_async",
    # Асинхронные функции конвертации
    "convert_icon_to_png_128_async",
    "convert_icon_to_png_32_async",
    "convert_raster_icon_to_png_async",
    # Пакетная конвертация
    "batch_convert_icons_async",
    # Основные функции создания иконок
    "themed_icon",
    "themed_icon_async",
    # Создание иконок из абсолютных путей
    "create_icon_from_path",
    "create_icon_from_path_async",
    # Внутренние функции (для совместимости)
    "_create_svg_icon",
    "_ensure_gui_thread",
    # Функции валидации (для совместимости)
    "is_valid_icon_file",
]
