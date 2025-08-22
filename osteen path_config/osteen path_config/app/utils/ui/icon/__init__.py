"""Модуль для работы с иконками (кеш, валидация, метрики)"""

# Импорт всех публичных функций и классов из модулей

# Управление кешем
from .cache_manager import (
    IconManager,
    ThreadSafeIconCache,
    clear_icon_cache,
    get_cached_category_icon,
    get_icon_cache_stats,
    log_icon_cache_stats,
    reset_icon_cache_stats,
)

# Разрешение путей категорий — из icon_resolver, чтобы избежать циклических импортов
from .icon_resolver import (
    resolve_category_icon_path,
)

# Централизованная система блокировок
from .lock_manager import (
    LockLevel,
    acquire_cache_lock,
    acquire_global_lock,
    acquire_lru_lock,
    acquire_metrics_lock,
    acquire_multiple_locks,
)

# LRU-политика
from .lru_policy import LRUPolicy

# Метрики кэша
from .metrics import CacheMetrics

# Централизованный сервис путей к иконкам
from .path_service import (
    IconPathService,
    get_current_theme,
    get_icon_path,
    get_qss_dir,
    get_themes_manifest_path,
    icon_path_service,
)

# Импорт is_valid_icon_file из локального валидатора
# Валидация и проверки
from .validation import (
    IconError,
    IconNotFoundError,
    InvalidIconError,
    Theme,
    is_cached_icon_valid,
    is_valid_icon_file,
    validate_config_for_icons,
    validate_theme,
)

# Операции с иконками (новая модульная структура)
# ВАЖНО: избегаем тяжёлых ре-экспортов из icon_operations, чтобы не провоцировать циклические импорты.
# Используйте явные импорты из подпакетов, например:
#   from app.utils.ui.icon.icon_operations.creators import themed_icon, create_icon_from_path

# Импорт функций конвертации напрямую из converters
# Конвертеры больше не ре-экспортируются из корневого пакета.
#   from app.utils.ui.icon.icon_operations.converters import copy_icon_smart, convert_icon_to_png_128, ...

# UI утилиты для работы с иконками
# UI-хелперы не ре-экспортируются.
#   from app.utils.ui.icon.ui_helpers import set_icon_to_button

# Кеш иконок меню
# (функциональность перемещена в icon_operations.py)

# Экспорт всех публичных функций и классов
__all__ = [
    # Валидация и проверки
    'Theme',
    'IconError',
    'IconNotFoundError',
    'InvalidIconError',
    'validate_theme',
    'is_valid_icon_file',
    'is_cached_icon_valid',
    'validate_config_for_icons',
    
    # Централизованный сервис путей
    'IconPathService',
    'icon_path_service',
    
    # Работа с путями
    'get_icon_path',
    'get_current_theme',
    'get_qss_dir',
    'get_themes_manifest_path',
    'resolve_category_icon_path',
    
    # Управление кешем
    'ThreadSafeIconCache',
    'IconManager',
    'clear_icon_cache',
    'get_icon_cache_stats',
    'reset_icon_cache_stats',
    'log_icon_cache_stats',
    'get_cached_category_icon',
    # Метрики кэша (только из metrics.py)
    'CacheMetrics',
    # LRU-политика
    'LRUPolicy',
    
    # Централизованная система блокировок
    'LockLevel',
    'acquire_global_lock',
    'acquire_cache_lock', 
    'acquire_metrics_lock',
    'acquire_lru_lock',
    'acquire_multiple_locks',
    
    # Обратите внимание: функции создания/конвертации иконок и UI-хелперы
    # доступны через явные подпакеты и не ре-экспортируются здесь, чтобы избежать циклов импорта.
]
