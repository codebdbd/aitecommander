"""Recent panel widget for top bar."""

from typing import Any, Dict, List, Optional

from PyQt6.QtWidgets import QToolButton, QWidget

from app.utils.ui.icon.icon_resolver import get_default_icon_path
from app.views.widgets.base.base_panel_widgets import BaseTopPanelWidget
from app.views.widgets.protocols import WidgetConfigProtocol

RECENT_LINKS_LIMIT = 10


class RecentPanelWidget(BaseTopPanelWidget):
    """Dedicated widget for recent links panel functionality."""

    def __init__(
        self, 
        main_window: Optional[QWidget] = None, 
        config: Optional[WidgetConfigProtocol] = None,
        batch_size: int = 0
    ):
        """Initialize recent panel.
        
        Args:
            main_window: Reference to main window
            config: Configuration provider (uses app_config if None)
            batch_size: Batch size for async population (0 = synchronous)
        """
        super().__init__(main_window, config=config, batch_size=batch_size)
        self._default_icon_path = get_default_icon_path()

        # Set object names for styling
        self.setObjectName("recentPanel")
        self.bg_frame.setObjectName("recentPanelBg")
    def set_data(self, items: List[Dict[str, Any]]) -> None:
        """Sets recent links data and populates the panel (unified contract)."""
        self._populate_panel(items, self._create_recent_button)
        # Visibility is managed by TopBarLayoutManager; just sync layout
        self._sync_topbar_layout()

    def get_limit(self) -> int:
        """Optional contract (RecentsPanelWithLimit): desired number of items."""
        return RECENT_LINKS_LIMIT

    def _create_recent_button(self, link_data: Dict[str, Any]) -> QToolButton:
        """Creates a recent link button with proper styling and click handling."""
        button = self._create_link_button(link_data)
        button.setObjectName("recentButton")
        button.clicked.connect(lambda: self._handle_recent_click(link_data))
        return button

    def _handle_recent_click(self, link_data: Dict[str, Any]) -> None:
        """Handles click on a recent link: opens link and requests refresh."""
        # Emit unified action signal
        self._emit_action_safely({"type": "open_link", "link": link_data})

        # Request refresh after click
        self._emit_refresh_safely({"limit": RECENT_LINKS_LIMIT})
