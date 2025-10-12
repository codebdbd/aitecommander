"""Protocol для конфигурации TopBar компонентов.

ИСПРАВЛЕНИЕ: Добавлен Protocol для dependency injection, упрощающий тестирование
и устраняющий жесткую связь с app_config.
"""

from __future__ import annotations

from typing import Protocol, Any


class TopBarConfigProtocol(Protocol):
    """Protocol определяющий интерфейс конфигурации для TopBar.
    
    Используется для dependency injection, позволяя легко подменять
    конфигурацию в тестах и изолировать компоненты от глобального состояния.
    
    Example:
        >>> class MockConfig:
        ...     def get_button_size(self) -> int:
        ...         return 32
        >>> 
        >>> manager = TopBarLayoutManager(window, MockConfig())
    """
    
    def get_button_size(self) -> int:
        """Возвращает размер кнопок в пикселях.
        
        Returns:
            Размер кнопки (обычно 32 или 24)
        """
        ...
    
    def get_search_min_width(self) -> int:
        """Возвращает минимальную ширину поля поиска.
        
        Returns:
            Минимальная ширина в пикселях (обычно 148)
        """
        ...
    
    def get_search_height(self) -> int:
        """Возвращает высоту поля поиска.
        
        Returns:
            Высота в пикселях (обычно 32)
        """
        ...
    
    def get_top_bar_height(self) -> int:
        """Возвращает высоту верхней панели.
        
        Returns:
            Высота в пикселях (обычно 40)
        """
        ...
    
    def get_side_spacing(self) -> int:
        """Возвращает боковые отступы для виджетов.
        
        Returns:
            Отступ в пикселях (обычно 8)
        """
        ...
    
    def get_throttle_ms(self) -> int:
        """Возвращает интервал throttling для resize событий.
        
        Returns:
            Интервал в миллисекундах (обычно 32)
        """
        ...
    
    def get_log_info(self) -> bool:
        """Возвращает флаг логирования информационных сообщений.
        
        Returns:
            True если нужно логировать INFO сообщения
        """
        ...
    
    def get_min_visible(self, panel: str) -> int:
        """Возвращает минимальное количество видимых кнопок для панели.
        
        Args:
            panel: Имя панели ('recent', 'fav', 'quick')
            
        Returns:
            Минимальное количество видимых кнопок (обычно 0)
        """
        ...
    
    def get(self, key: str, default: Any = None) -> Any:
        """Универсальный метод получения конфигурации.
        
        Args:
            key: Ключ конфигурации (например, 'ui.topbar.throttle_ms')
            default: Значение по умолчанию
            
        Returns:
            Значение конфигурации или default
        """
        ...


class AppConfigAdapter:
    """Адаптер для app_config, реализующий TopBarConfigProtocol.
    
    ИСПРАВЛЕНИЕ: Обертка над глобальным app_config для соответствия Protocol.
    Позволяет использовать существующий app_config через единый интерфейс.
    
    Example:
        >>> from app.config_data import app_config
        >>> config = AppConfigAdapter(app_config)
        >>> manager = TopBarLayoutManager(window, config)
    """
    
    def __init__(self, app_config: Any):
        """Инициализирует адаптер.
        
        Args:
            app_config: Глобальный объект конфигурации приложения
        """
        self._config = app_config
    
    def get_button_size(self) -> int:
        """Возвращает размер кнопок из конфигурации."""
        try:
            return int(self._config.ui.get_top_panel_button_size())
        except (ValueError, TypeError, AttributeError):
            return 32
    
    def get_search_min_width(self) -> int:
        """Возвращает минимальную ширину поиска из конфигурации."""
        try:
            return int(self._config.ui.get_top_panel_search_min_width())
        except (ValueError, TypeError, AttributeError):
            return 148
    
    def get_search_height(self) -> int:
        """Возвращает высоту поиска из конфигурации."""
        try:
            return int(self._config.ui.get_top_panel_search_height())
        except (ValueError, TypeError, AttributeError):
            return 32
    
    def get_top_bar_height(self) -> int:
        """Возвращает высоту топбара из конфигурации."""
        try:
            return int(self._config.ui.get_top_bar_height())
        except (ValueError, TypeError, AttributeError):
            return 40
    
    def get_side_spacing(self) -> int:
        """Возвращает боковые отступы из конфигурации."""
        try:
            return int(self._config.ui.get_top_bar_widgets_side_spacing())
        except (ValueError, TypeError, AttributeError):
            return 8
    
    def get_throttle_ms(self) -> int:
        """Возвращает интервал throttling из конфигурации."""
        try:
            return int(self._config.get("ui.topbar.throttle_ms", 32))
        except (ValueError, TypeError, AttributeError):
            return 32
    
    def get_log_info(self) -> bool:
        """Возвращает флаг логирования из конфигурации."""
        try:
            return bool(self._config.get("ui.topbar.log_info", False))
        except (ValueError, TypeError, AttributeError):
            return False
    
    def get_min_visible(self, panel: str) -> int:
        """Возвращает минимальное количество видимых кнопок."""
        try:
            mv = self._config.get("topbar.min_visible", {}) or {}
            return int(mv.get(panel, 0))
        except (KeyError, ValueError, TypeError, AttributeError):
            return 0
    
    def get(self, key: str, default: Any = None) -> Any:
        """Универсальный метод получения конфигурации."""
        try:
            return self._config.get(key, default)
        except (KeyError, AttributeError):
            return default


class MockTopBarConfig:
    """Mock конфигурация для тестирования.
    
    ИСПРАВЛЕНИЕ: Простая реализация Protocol для unit-тестов без зависимостей.
    
    Example:
        >>> config = MockTopBarConfig(button_size=24, search_min_width=100)
        >>> manager = TopBarLayoutManager(window, config)
    """
    
    def __init__(
        self,
        button_size: int = 32,
        search_min_width: int = 148,
        search_height: int = 32,
        top_bar_height: int = 40,
        side_spacing: int = 8,
        throttle_ms: int = 32,
        log_info: bool = False,
        min_visible_recent: int = 0,
        min_visible_fav: int = 0,
        min_visible_quick: int = 0,
    ):
        """Инициализирует mock конфигурацию с заданными значениями."""
        self._button_size = button_size
        self._search_min_width = search_min_width
        self._search_height = search_height
        self._top_bar_height = top_bar_height
        self._side_spacing = side_spacing
        self._throttle_ms = throttle_ms
        self._log_info = log_info
        self._min_visible = {
            "recent": min_visible_recent,
            "fav": min_visible_fav,
            "quick": min_visible_quick,
        }
        self._custom_values = {}
    
    def get_button_size(self) -> int:
        return self._button_size
    
    def get_search_min_width(self) -> int:
        return self._search_min_width
    
    def get_search_height(self) -> int:
        return self._search_height
    
    def get_top_bar_height(self) -> int:
        return self._top_bar_height
    
    def get_side_spacing(self) -> int:
        return self._side_spacing
    
    def get_throttle_ms(self) -> int:
        return self._throttle_ms
    
    def get_log_info(self) -> bool:
        return self._log_info
    
    def get_min_visible(self, panel: str) -> int:
        return self._min_visible.get(panel, 0)
    
    def get(self, key: str, default: Any = None) -> Any:
        return self._custom_values.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Устанавливает кастомное значение (для тестов)."""
        self._custom_values[key] = value
