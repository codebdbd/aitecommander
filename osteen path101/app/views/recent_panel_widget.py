"""Recent links panel widget for top bar."""

import logging
from typing import Any, Dict, List

from PyQt6.QtWidgets import QToolButton

from app.utils.ui.icon.icon_resolver import get_default_icon_path
from app.views.base_panel_widgets import BaseTopPanelWidget

RECENT_LINKS_LIMIT = 10


class RecentPanelWidget(BaseTopPanelWidget):
    """Dedicated widget for recent links panel functionality."""

    def __init__(self, main_window=None):
        super().__init__(main_window)
        self._default_icon_path = get_default_icon_path()

        # Set object names for styling
        self.setObjectName("recentPanel")
        self.bg_frame.setObjectName("recentPanelBg")

    def set_data(self, items: List[Dict[str, Any]]) -> None:
        """Sets recent links data and populates the panel."""
        self._populate_panel(items, self._create_recent_button)

        # Set visibility based on whether we have items
        try:
            self.setVisible(bool(items))
        except Exception:
            logging.getLogger(__name__).debug(
                "RecentPanelWidget: setVisible failed", exc_info=True
            )

        # Sync top bar layout
        self._sync_topbar_layout()

    def set_recent_links(self, items: List[Any]) -> None:
        """Sets recent links data - required by RecentsPanelLike interface."""
        self.set_data(items)

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
