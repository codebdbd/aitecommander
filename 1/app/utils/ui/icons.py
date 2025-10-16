"""Простая и быстрая система загрузки UI-иконок.

Архитектура:
- Прямая загрузка SVG через QIcon (Qt кэширует автоматически)
- Один словарь для кэша иконок в памяти
- Поддержка тем (light/dark) с автоматическим fallback
- Мгновенная загрузка (<1ms после первого обращения)
- Автоматическая очистка при смене темы
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QIcon, QPixmapCache

logger = logging.getLogger(__name__)

# Глобальный кэш иконок: (theme, name) -> QIcon
_ICON_CACHE: dict[tuple[str, str], QIcon] = {}

# Текущая активная тема
_CURRENT_THEME: str = "light"

# Базовый путь к иконкам (определяется при первом обращении)
_ICONS_BASE_PATH: Optional[Path] = None


def _get_icons_path() -> Path:
    """Получить базовый путь к каталогу ui_icons."""
    global _ICONS_BASE_PATH
    if _ICONS_BASE_PATH is None:
        # app/utils/ui/icons.py -> app/resources/ui_icons/
        current_file = Path(__file__)
        _ICONS_BASE_PATH = current_file.parent.parent.parent / "resources" / "ui_icons"
    return _ICONS_BASE_PATH


def set_theme(theme: str) -> None:
    """Установить текущую тему и очистить кэш иконок.
    
    Args:
        theme: Имя темы ("light" или "dark")
    """
    global _CURRENT_THEME
    
    if theme not in ("light", "dark"):
        logger.warning(f"Unknown theme '{theme}', using 'light'")
        theme = "light"
    
    if theme != _CURRENT_THEME:
        old_theme = _CURRENT_THEME
        _CURRENT_THEME = theme
        
        # Очистить только иконки старой темы из кэша
        keys_to_remove = [k for k in _ICON_CACHE if k[0] == old_theme]
        for key in keys_to_remove:
            del _ICON_CACHE[key]
        
        # Очистить Qt-кэш пикс-мапов
        QPixmapCache.clear()
        
        logger.info(f"Theme changed: {old_theme} -> {theme}, cleared {len(keys_to_remove)} cached icons")


def get_current_theme() -> str:
    """Получить текущую активную тему.
    
    Returns:
        Имя текущей темы ("light" или "dark")
    """
    return _CURRENT_THEME


def get_icon(name: str, theme: Optional[str] = None) -> QIcon:
    """Получить иконку по имени (МГНОВЕННО после первой загрузки).
    
    Порядок поиска:
    1. Проверка кэша
    2. Загрузка из <theme>/<name>
    3. Fallback на light/<name> (если тема не light)
    4. Возврат пустой иконки
    
    Args:
        name: Имя файла иконки (например, "delete.svg")
        theme: Тема ("light"/"dark"), если None — используется текущая
        
    Returns:
        QIcon object (может быть пустым, если иконка не найдена)
        
    Examples:
        >>> icon = get_icon("delete.svg")  # Текущая тема
        >>> icon = get_icon("add_link.svg", "dark")  # Конкретная тема
    """
    theme = theme or _CURRENT_THEME
    
    # Нормализация темы
    if theme not in ("light", "dark"):
        logger.warning(f"Invalid theme '{theme}', using 'light'")
        theme = "light"
    
    # Проверка кэша
    cache_key = (theme, name)
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]
    
    # Загрузка иконки
    icons_base = _get_icons_path()
    icon_path = icons_base / theme / name
    
    icon = QIcon()
    
    if icon_path.exists():
        # Основной путь существует
        icon = QIcon(str(icon_path))
    elif theme != "light":
        # Fallback на light тему
        light_path = icons_base / "light" / name
        if light_path.exists():
            icon = QIcon(str(light_path))
            logger.debug(f"Icon '{name}' not found in '{theme}' theme, using light fallback")
    
    if icon.isNull():
        logger.warning(f"Icon not found: {name} (theme: {theme})")
    
    # Кэшировать результат (даже если пустой)
    _ICON_CACHE[cache_key] = icon
    return icon


def clear_cache() -> None:
    """Полностью очистить кэш иконок и Qt pixmap cache.
    
    Используется при необходимости принудительной перезагрузки всех иконок.
    При обычной смене темы используйте set_theme(), которая очищает только
    иконки старой темы.
    """
    _ICON_CACHE.clear()
    QPixmapCache.clear()
    logger.info("Icon cache completely cleared")


def get_cache_stats() -> dict[str, int]:
    """Получить статистику кэша иконок.
    
    Returns:
        Словарь со статистикой:
        - total: Общее количество закэшированных иконок
        - light: Количество иконок светлой темы
        - dark: Количество иконок тёмной темы
    """
    light_count = sum(1 for theme, _ in _ICON_CACHE if theme == "light")
    dark_count = sum(1 for theme, _ in _ICON_CACHE if theme == "dark")
    
    return {
        "total": len(_ICON_CACHE),
        "light": light_count,
        "dark": dark_count,
        "current_theme": _CURRENT_THEME,
    }


def preload_icons(icon_names: list[str], theme: Optional[str] = None) -> int:
    """Предзагрузить список иконок в кэш.
    
    Полезно для прогрева кэша при старте приложения или перед
    отображением UI с большим количеством иконок.
    
    Args:
        icon_names: Список имён файлов иконок
        theme: Тема для предзагрузки (если None — текущая)
        
    Returns:
        Количество успешно загруженных иконок
    """
    theme = theme or _CURRENT_THEME
    loaded = 0
    
    for name in icon_names:
        icon = get_icon(name, theme)
        if not icon.isNull():
            loaded += 1
    
    logger.info(f"Preloaded {loaded}/{len(icon_names)} icons for theme '{theme}'")
    return loaded


# Список часто используемых иконок для предзагрузки
COMMON_ICONS = [
    "add_link.svg",
    "delete.svg",
    "edit.svg",
    "copy.svg",
    "paste.svg",
    "cut.svg",
    "undo.svg",
    "redo.svg",
    "search.svg",
    "settings.svg",
]
