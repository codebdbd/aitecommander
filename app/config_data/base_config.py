"""
Базовый класс для работы с конфигурацией.
"""

from typing import Any, Dict

from .utils import get_by_path


class BaseConfig:
    """Базовый класс для всех конфигурационных модулей."""

    def __init__(self, config_data: Dict[str, Any]):
        """Инициализация с данными конфигурации."""
        self._config = config_data

    def get(self, key_path: str, default: Any = None) -> Any:
        """Получение значения из конфигурации по пути к ключу."""
        return get_by_path(self._config, key_path, default)
