"""Улучшенный topbar модуль с устранением архитектурных проблем."""

from .cached_width_calculator import CachedWidthCalculator, OptimizedTotalWidthCalculator
from .constants import AdjustmentReason, SizeConstraint, SeparatorInfo, TopBarConstants
from .exceptions import LayoutCalculationError, PanelConfigurationError, SizeConstraintError, TopBarError
from .layout_context import LayoutContext
from .panel_size_manager import PanelSizeManager
from .panel_state import PanelDefinition, PanelState
from .panel_visibility_manager import PanelVisibilityManager
from .separator_manager import SeparatorManager
from .top_bar_layout_manager import TopBarLayoutManager
from .top_bar_setup import TopBarBuilder
from .visibility_solver import VisibilitySolver
from .width_calculator import WidthCalculator

__all__ = [
    # Основные классы
    "TopBarLayoutManager",
    "TopBarBuilder",
    
    # Модульные сервисы
    "PanelSizeManager",
    "PanelVisibilityManager", 
    "SeparatorManager",
    "VisibilitySolver",
    
    # Калькуляторы
    "WidthCalculator",
    "CachedWidthCalculator",
    "OptimizedTotalWidthCalculator",
    
    # Модели данных
    "LayoutContext",
    "PanelDefinition",
    "PanelState",
    
    # Константы и конфигурация
    "TopBarConstants",
    "AdjustmentReason",
    "SizeConstraint",
    "SeparatorInfo",
    
    # Исключения
    "TopBarError",
    "LayoutCalculationError",
    "PanelConfigurationError", 
    "SizeConstraintError",
]

# Версия улучшенного модуля
__version__ = "2.0.0"

# Информация об улучшениях
__improvements__ = {
    "architecture": [
        "Устранены циклические вызовы adjust()",
        "Единый источник истины для размеров панелей",
        "Батчинг всех изменений layout",
        "Декларативное управление размерами через QSizePolicy",
    ],
    "performance": [
        "Кэширование расчетов ширины",
        "Оптимизированные обращения к Qt API",
        "Throttling и debouncing событий",
        "Минимизация пересчетов layout",
    ],
    "reliability": [
        "Улучшенная обработка ошибок",
        "Безопасные операции с Qt объектами",
        "Защита от утечек памяти",
        "Graceful degradation при ошибках",
    ],
    "maintainability": [
        "Модульная архитектура",
        "Централизованные константы",
        "Типизированные PyQt6 сигналы",
        "Подробное логирование и мониторинг",
    ],
}
