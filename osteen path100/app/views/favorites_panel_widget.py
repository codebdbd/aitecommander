"""Favorites panel widget for top bar."""

import logging
from typing import Any, Dict, List

from PyQt6.QtWidgets import QToolButton

from app.utils.ui.icon.icon_resolver import get_default_icon_path
from app.views.base_panel_widgets import BaseTopPanelWidget


class FavoritesPanelWidget(BaseTopPanelWidget):
    """Dedicated widget for favorites panel functionality."""

    def __init__(self, main_window=None):
        super().__init__(main_window)
        self._default_icon_path = get_default_icon_path()

        # Set object names for styling
        self.setObjectName("favoritesPanel")
        self.bg_frame.setObjectName("favoritesPanelBg")

    def set_data(self, items: List[Dict[str, Any]]) -> None:
        """Sets favorites data and populates the panel."""
        self._populate_panel(items, self._create_favorite_button)

        # Set visibility based on whether we have items
        try:
            self.setVisible(bool(items))
        except Exception:
            logging.getLogger(__name__).debug(
                "FavoritesPanelWidget: setVisible failed", exc_info=True
            )

        # Sync top bar layout
        self._sync_topbar_layout()

    def set_favorites(self, items: List[Any]) -> None:
        """Sets favorites data - required by FavoritesPanelLike interface."""
        self.set_data(items)

    def clear_favorites(self) -> None:
        """Clears favorites - required by FavoritesPanelWithClear interface."""
        self.clearRequested.emit()

    def clear(self) -> None:
        """Initiates clearing of favorites."""
        self.clear_favorites()

    def _create_favorite_button(self, link_data: Dict[str, Any]) -> QToolButton:
        """Creates a favorite button with proper styling and click handling."""
        button = self._create_link_button(link_data)
        button.setObjectName("favoriteButton")
        button.clicked.connect(lambda: self._handle_favorite_click(link_data))
        return button

    def _handle_favorite_click(self, link_data: Dict[str, Any]) -> None:
        """Handles click on a favorite link."""
        # Emit unified action signal
        self._emit_action_safely({"type": "open_link", "link": link_data})
