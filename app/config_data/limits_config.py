"""
Конфигурация лимитов и ограничений.
"""
from typing import Any, Dict

from .base_config import BaseConfig


class LimitsConfig(BaseConfig):
    """Конфигурация лимитов и ограничений приложения."""
    
    # === Лимиты размеров файлов ===
    
    def get_max_icon_size(self) -> int:
        """Получение максимального размера файлов иконок."""
        return self.get("limits.max_icon_size", 10 * 1024 * 1024)

    def get_max_web_icon_size(self) -> int:
        """Получение максимального размера веб-иконок."""
        return self.get("limits.max_web_icon_size", 2 * 1024 * 1024)
    
    # === Кэширование ===

    def get_icon_cache_size(self) -> int:
        """Получение размера кэша иконок."""
        return self.get("limits.icon_cache_size", 100)

    def get_icon_cache_ttl(self) -> int:
        """Получение времени жизни кэша иконок в секундах.
        
        По умолчанию 300 секунд (5 минут). Рекомендуемый диапазон: 300-600 секунд (5-10 минут)
        для автоматического обновления изменений файлов иконок.
        """
        return self.get("limits.icon_cache_ttl", 300)

    def get_negative_cache_ttl(self) -> int:
        """Получение времени жизни негативного кэша в секундах.
        
        По умолчанию 30 секунд. Используется для кэширования отсутствующих файлов,
        чтобы избежать частых проверок файловой системы.
        """
        return self.get("limits.negative_cache_ttl", 30)

    def get_abs_icon_cache_ttl(self) -> int:
        """Получение времени жизни кэша иконок по абсолютным путям в секундах.
        
        По умолчанию 30 секунд. Используется для кэширования иконок по абсолютным путям,
        чтобы избежать частых проверок файловой системы при динамическом появлении файлов.
        """
        return self.get("limits.abs_icon_cache_ttl", 30)
