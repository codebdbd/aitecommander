"""Services layer for topbar - business logic and computations."""

from .accessibility_manager import AccessibilityManager
from .config_service import PanelBounds, TopBarConfigService, TopBarSettings
from .layout_service import LayoutComputationResult, TopBarLayoutService
from .panel_visibility_manager import PanelVisibilityManager
from .search_manager import SearchWidgetManager
from .separator_service import SeparatorVisibilityService
from .visibility_solver import VisibilitySolver
from .width_calculator import WidthCalculator

__all__ = [
    "AccessibilityManager",
    "PanelBounds",
    "TopBarConfigService",
    "TopBarSettings",
    "LayoutComputationResult",
    "TopBarLayoutService",
    "PanelVisibilityManager",
    "SearchWidgetManager",
    "SeparatorVisibilityService",
    "VisibilitySolver",
    "WidthCalculator",
]
