"""Favorites panel widget for top bar."""

from typing import Any, Optional

from PyQt6.QtWidgets import QToolButton

from app.utils.ui.icon.icon_resolver import get_default_icon_path
from app.views.widgets.base.base_panel_widgets import BaseTopPanelWidget
from app.views.widgets.protocols import WidgetConfigProtocol


class FavoritesPanelWidget(BaseTopPanelWidget):
    """Dedicated widget for favorites panel functionality."""

    def __init__(
        self,
        main_window=None,
        config: Optional[WidgetConfigProtocol] = None,
        batch_size: int = 0,
    ):
        """Initialize favorites panel.

        Args:
            main_window: Reference to main window
            config: Configuration provider (uses app_config if None)
            batch_size: Batch size for async population (0 = synchronous)
        """
        super().__init__(main_window, config=config, batch_size=batch_size)
        self._default_icon_path = get_default_icon_path()

        # Set object names for styling
        self.setObjectName("favoritesPanel")
        self.bg_frame.setObjectName("favoritesPanelBg")

    def set_data(self, items: list[dict[str, Any]]) -> None:
        """Sets favorites data and populates the panel (unified contract)."""
        self._populate_panel(items, self._create_favorite_button)

        # Visibility is managed by TopBarLayoutManager; just sync layout
        self._sync_topbar_layout()

    def clear_favorites(self) -> None:
        """Clears favorites - required by FavoritesPanelWithClear interface."""
        self.clearRequested.emit()

    def clear(self) -> None:
        """Initiates clearing of favorites."""
        self.clear_favorites()

    def _create_favorite_button(self, link_data: dict[str, Any]) -> QToolButton:
        """Creates a favorite button with proper styling and click handling."""
        button = self._create_link_button(link_data)
        button.setObjectName("favoriteButton")
        button.clicked.connect(lambda: self._handle_favorite_click(link_data))
        return button

    def _handle_favorite_click(self, link_data: dict[str, Any]) -> None:
        """Handles click on a favorite link."""
        # Emit unified action signal
        self._emit_action_safely({"type": "open_link", "link": link_data})
