"""Compatibility wrapper for legacy topbar imports.

Re-exports symbols from `app.views.main_components.ui.topbar` so that
existing tests referring to `app.views.main_components.topbar.*` remain
functional after the package refactor.
"""

from app.views.main_components.ui.topbar.accessibility_manager import AccessibilityManager
from app.views.main_components.ui.topbar.panel_visibility_manager import PanelVisibilityManager
from app.views.main_components.ui.topbar.layout_context import LayoutContext
from app.views.main_components.ui.topbar.panel_state import PanelDefinition, PanelState
from app.views.main_components.ui.topbar.top_bar_layout_manager import TopBarLayoutManager
from app.views.main_components.ui.topbar.visibility_solver import VisibilitySolver
from app.views.main_components.ui.topbar.width_calculator import WidthCalculator

__all__ = [
    "AccessibilityManager",
    "PanelVisibilityManager",
    "LayoutContext",
    "PanelDefinition",
    "PanelState",
    "TopBarLayoutManager",
    "VisibilitySolver",
    "WidthCalculator",
]
