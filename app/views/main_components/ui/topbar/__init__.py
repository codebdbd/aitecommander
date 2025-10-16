"""TopBar module - modular architecture with services, models, controllers.

Architecture:
- services/: Business logic (layout, config, search, separators)
- models/: Data structures (LayoutContext, PanelState, constants)
- controllers/: UI coordination (TopBarController)
- Root: Legacy compatibility layer (TopBarLayoutManager)
"""

# Legacy compatibility - re-export from new locations
from .models.layout_context import LayoutContext
from .models.panel_state import PanelDefinition, PanelState
from .models.topbar_constants import TOPBAR_CONSTANTS
from .services.config_service import TopBarConfigService, TopBarSettings
from .services.layout_service import LayoutComputationResult, TopBarLayoutService
from .top_bar_layout_manager import TopBarLayoutManager

__all__ = [
    "TopBarLayoutManager",
    "LayoutContext",
    "PanelDefinition",
    "PanelState",
    "TOPBAR_CONSTANTS",
    "TopBarConfigService",
    "TopBarSettings",
    "LayoutComputationResult",
    "TopBarLayoutService",
]
